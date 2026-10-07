"""Derivative Genesis host: existing workflows plus the local Excel component.
The API provider is deliberately disabled for this delivery. No key is read.
"""
import argparse
import json
import mimetypes
import re
import secrets
import threading
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote, quote

import server as existing
from agent_core import Agent
from analysis_store import Analysis
from excel_static import ExcelAnalyzer, ScanError, sha_file

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / 'excel_config.json').read_text(encoding='utf-8-sig'))


class DisabledAI:
    verified = False
    def available(self): return False
    def clear(self): pass
    def set_key(self, *_): raise ValueError('LOCAL_ONLY')
    def complete(self, *_args, **_kwargs): raise RuntimeError('EXTERNAL_API_DISABLED')


class LocalAgent(Agent):
    def secret(self, payload):
        self.fail('LOCAL_ONLY', 'この版ではAPIキー登録と追加API送信を停止しています。', 403)

    def action(self, payload, key):
        action = payload.get('action', '')
        if action in ('agent_classify', 'agent_design'):
            with self.db() as db:
                case = self.load(db, payload.get('caseId'))
            if case['mode'] == 'real':
                self.fail('LOCAL_ONLY', '追加API送信は停止しています。既存結果は保持します。', 403)
        return super().action(payload, key)

    def info(self):
        data = super().info()
        data['localOnly'] = True
        data['additionalApiRequests'] = 0
        for c in data['components']:
            if c['id'] == 'excel-static':
                c.update(status='ローカル部品へ接続', detail='ボタンから静的解析を実行できます。案件承認後の自動振分けとAccess内のテーブルへの書込みは未接続です。')
        return data


class Handler(existing.Handler):
    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'HOST_NOT_ALLOWED'})
        path = urlsplit(self.path).path
        static = {'/excel': 'excel.html', '/excel.js': 'excel.js', '/excel.css': 'excel.css'}
        if path in static:
            file = ROOT / 'static' / static[path]
            return self.respond(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or 'text/plain') + '; charset=utf-8')
        if path == '/api/health':
            return self.respond(200, {'application': 'genesis-excel-static', 'version': CFG['version'], 'mode': 'local-only', 'additionalApiRequests': 0})
        if path == '/api/excel':
            rid = parse_qs(urlsplit(self.path).query).get('run', [''])[0]
            try:
                detail = self.server.excel.detail(rid) if rid else None
                test_file = ROOT.parent / '検証' / '自動試験結果.json'
                tests = json.loads(test_file.read_text(encoding='utf-8')) if test_file.exists() else None
                delivery_file = ROOT.parent / '資料' / '納品一覧.json'
                delivery = json.loads(delivery_file.read_text(encoding='utf-8')) if delivery_file.exists() else []
                return self.respond(200, {'runs': self.server.excel.list_runs(), 'detail': detail, 'tests': tests, 'delivery': delivery,
                    'csrf': self.server.token, 'additionalApiRequests': 0, 'aiConnected': False, 'storage': str(self.server.excel.db_path),
                    'samples': ['v07/standard_features.xlsm', 'standard.xlsm', 'standard.xlsx', 'standard.xlam', 'standard.xls', 'standard.xlsb', 'external.xlsm', 'corrupt.xlsm', 'encrypted.xls']})
            except ScanError:
                return self.respond(404, {'error': 'RUN_NOT_FOUND'})
        if path.startswith('/api/excel/download/'):
            parts = [unquote(x) for x in path.split('/')]
            if len(parts) != 7:
                return self.respond(404, {'error': 'NOT_FOUND'})
            try:
                file = self.server.excel.downloadable(parts[4], parts[5], parts[6])
                return self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream',
                    extra={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(file.name)})
            except (ScanError, OSError):
                return self.respond(409, {'error': 'ARTIFACT_UNAVAILABLE'})
        if path.startswith('/api/excel/delivery/'):
            aid = path.rsplit('/', 1)[-1]
            try:
                index = json.loads((ROOT.parent / '資料' / '納品一覧.json').read_text(encoding='utf-8'))
                row = next(x for x in index if x['id'] == aid)
                file = ROOT.parent / row['path']
                if not file.resolve().is_relative_to(ROOT.parent.resolve()) or sha_file(file) != row['sha256']:
                    raise ValueError()
                return self.respond(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream',
                    extra={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(file.name)})
            except (OSError, ValueError, StopIteration):
                return self.respond(404, {'error': 'DELIVERY_UNAVAILABLE'})
        return super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/excel/run', '/api/excel/export'):
            return super().do_POST()
        origins = [f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}']
        if not self.valid_host() or self.headers.get('Origin') not in origins or self.headers.get('X-Genesis-Token') != self.server.token:
            return self.respond(403, {'error': 'REQUEST_NOT_ALLOWED'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            key = self.headers.get('Idempotency-Key', '')
            if not (0 < size <= 8000) or not re.fullmatch('[A-Za-z0-9-]{16,64}', key):
                raise ScanError('INPUT_INVALID')
            data = json.loads(self.rfile.read(size))
            payload_hash = existing.sha({'path': path, 'data': data})
            # Serialization plus persistent receipts prevents duplicate clicks
            # from silently making another run/export. Interrupted receipts are
            # held; they are never automatically retried after restart.
            with self.server.excel_dispatch:
                with self.server.excel.db() as db:
                    old = db.execute('SELECT * FROM Requests WHERE Key=?', (key,)).fetchone()
                    if old:
                        if old['Hash'] != payload_hash:
                            raise ScanError('REQUEST_KEY_CONFLICT')
                        return self.respond(200 if old['Body'] else 409, json.loads(old['Body']) if old['Body'] else {'ok': False, 'error': 'PRIOR_RESULT_UNCONFIRMED'})
                    db.execute('INSERT INTO Requests VALUES(?,?,NULL)', (key, payload_hash))
                if path.endswith('/run'):
                    if data.get('sample'):
                        sample = str(data['sample'])
                        if sample not in ['v07/standard_features.xlsm', 'standard.xlsm', 'standard.xlsx', 'standard.xlam', 'standard.xls', 'standard.xlsb', 'external.xlsm', 'corrupt.xlsm', 'encrypted.xls']:
                            raise ScanError('SAMPLE_NOT_ALLOWED')
                        source = ROOT.parent / '標準テストExcel' / sample
                    else:
                        if data.get('localOnlyConsent') is not True:
                            raise ScanError('LOCAL_SOURCE_CONFIRMATION_REQUIRED')
                        source = data.get('path', '')
                    run = self.server.excel.run(source)
                    response = {'ok': run['status'] in ('SUCCESS', 'PARTIAL', 'NO_VBA'), 'runId': run['runId'], 'status': run['status']}
                else:
                    export = self.server.excel.export(data.get('runId', ''))
                    response = {'ok': export['status'] == 'SUCCESS', 'runId': export['runId'], 'exportId': export['exportId'], 'status': export['status']}
                with self.server.excel.db() as db:
                    db.execute('UPDATE Requests SET Body=? WHERE Key=?', (json.dumps(response), key))
                return self.respond(200, response)
        except ScanError as ex:
            return self.respond(400, {'ok': False, 'error': str(ex)})
        except Exception:
            return self.respond(500, {'ok': False, 'error': 'LOCAL_REQUEST_FAILED'})


def make_server(port=None):
    host = existing.ThreadingHTTPServer(('127.0.0.1', port or CFG['port']), Handler)
    host.store = existing.Store(ROOT / 'data', ROOT / 'exports')
    host.analysis = Analysis(host.store, existing.Rejected)
    host.agent = LocalAgent(ROOT / 'data', existing.CONFIG, existing.Rejected, existing.Store.reject_sensitive, provider=DisabledAI())
    host.excel = ExcelAnalyzer(ROOT)
    with host.excel.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS Requests(Key TEXT PRIMARY KEY, Hash TEXT NOT NULL, Body TEXT)')
    host.excel_dispatch = threading.Lock()
    host.token = secrets.token_urlsafe(32)
    return host


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=CFG['port'])
    server = make_server(parser.parse_args().port)
    print(f'Genesis local Excel component: http://127.0.0.1:{server.server_port}/excel', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
