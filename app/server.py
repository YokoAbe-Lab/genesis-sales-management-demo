"""Genesis local agent and preserved analysis UI. Access execution stays disabled."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
SCREENS = {'overview': '案件の状況', 'request': '依頼入力', 'questions': '質問と選択', 'design': '詳細設計', 'review': '画面レビュー', 'diff': '差分確認', 'approval': '承認', 'tests': '試験結果', 'artifacts': '成果物', 'audit': '監査ログ', 'assets': '部品・未確認事項'}
SCREENS['analysis'] = '分析・読み解き資料作成'
SCREEN_IDS = {k: f'SCR-20261005-{i:04}' for i, k in enumerate(SCREENS, 1)}
STAGES = ['依頼受付', '解析と根拠', '質問と選択', '詳細設計', '画面レビュー', '承認', 'コピーと保全', '生成と改修', '試験', 'Word納品']

def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')

def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def sha(value):
    return hashlib.sha256(packed(value).encode('utf-8')).hexdigest()

def plan_hash(state):
    return sha({k: state[k] for k in ['request', 'answers', 'option', 'issues', 'screenVersion']})

def seed():
    state = {
        'projectId': 'PRJ-20261005-0001', 'projectUuid': str(uuid.uuid4()),
        'requestId': 'REQ-20261005-0001', 'questionSetId': 'QSET-20261005-0001',
        'revision': 1, 'designVersion': '0.3', 'screenVersion': '0.3-ui.1',
        'request': {'name': '改修依頼台帳の追加', 'text': 'Accessに改修依頼の受付・対応状況・期限を確認する台帳を追加したい。',
                    'target': 'Access改修', 'entry': 'analysis', 'purpose': '入力後に対応状況を検索し、未完了の依頼と期限を確認する。',
                    'constraints': '原本は変更しない。架空データを使い、作業用コピーで検証する。', 'privacy': 'synthetic', 'inputCount': 0, 'inputTypes': []},
        'answers': {}, 'option': None, 'issues': [], 'approvals': [], 'artifacts': [], 'mockRuns': [],
        'diffReviewedHash': None, 'diffId': 'DIF-20261005-0001', 'updatedAt': now(),
        'questions': [
            {'id': 'QST-20261005-0001', 'title': '誰がこの台帳を使いますか？', 'reason': '入力と確認の担当を決めるためです。', 'choices': ['まず自分1人', '複数の担当者', 'まだ決まっていない'], 'impact': '複数人で使う場合の権限・同時更新は別の設計が必要です。'},
            {'id': 'QST-20261005-0002', 'title': '最初に必要な出力はどれですか？', 'reason': '画面だけで足りるか、印刷も必要かを確認します。', 'choices': ['一覧と詳細・印刷', '一覧と詳細のみ', 'Word報告書も必要'], 'impact': '印刷の向きと項目は画面レビューで確認します。'},
            {'id': 'QST-20261005-0003', 'title': '問題のある入力行はどう扱いますか？', 'reason': '重複や型エラーを誤って登録しないためです。', 'choices': ['別に保存して人が確認', '全件を止めて確認', 'まだ決まっていない'], 'impact': '未回答の場合は、データ登録を開始しません。'}],
    }
    state['planHash'] = plan_hash(state)
    return state

class Rejected(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

class Store:
    def __init__(self, data: Path, exports: Path):
        self.data, self.exports = data, exports
        data.mkdir(parents=True, exist_ok=True)
        exports.mkdir(parents=True, exist_ok=True)
        self.path = data / 'evidence.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(revision INTEGER PRIMARY KEY,body TEXT NOT NULL,hash TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,uuid TEXT UNIQUE,created TEXT,event TEXT,result TEXT,project_id TEXT,summary TEXT,previous_hash TEXT,hash TEXT);
            CREATE TABLE IF NOT EXISTS receipts(key TEXT PRIMARY KEY,request_hash TEXT NOT NULL,response TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS counters(prefix TEXT PRIMARY KEY,value INTEGER NOT NULL);''')
            if not db.execute('SELECT 1 FROM state').fetchone():
                s = seed()
                db.execute('INSERT INTO state VALUES(1,?)', (packed(s),))
                db.execute('INSERT INTO versions VALUES(?,?,?,?)', (1, packed(s), sha(s), now()))
                self.audit(db, '画面確認案件の準備', '保存', '架空の確認用案件。AI・Accessアダプターは未接続。')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def next_id(self, db, prefix):
        row = db.execute('SELECT value FROM counters WHERE prefix=?', (prefix,)).fetchone()
        value = (row[0] if row else 0) + 1
        db.execute('INSERT INTO counters VALUES(?,?) ON CONFLICT(prefix) DO UPDATE SET value=excluded.value', (prefix, value))
        return f'{prefix}-{datetime.now():%Y%m%d}-{value:04}'

    def audit(self, db, event, result, summary):
        prev = db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        rec = {'id': self.next_id(db, 'LOG'), 'uuid': str(uuid.uuid4()), 'created': now(), 'event': event,
               'result': result, 'project_id': 'PRJ-20261005-0001', 'summary': summary, 'previous_hash': prev[0] if prev else ''}
        rec['hash'] = sha(rec)
        db.execute('INSERT INTO audit(id,uuid,created,event,result,project_id,summary,previous_hash,hash) VALUES(:id,:uuid,:created,:event,:result,:project_id,:summary,:previous_hash,:hash)', rec)

    def state(self):
        with self.connect() as db:
            s = json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            s['audit'] = [dict(x) for x in db.execute('SELECT * FROM audit ORDER BY seq DESC')]
        s.update({'screens': SCREENS, 'screenIds': SCREEN_IDS, 'stages': STAGES,
                  'assets': json.loads((ROOT / 'assets.json').read_text(encoding='utf-8')),
                  'capabilities': {'externalApi': False, 'accessExecution': False, 'fileUpload': False, 'wordOutput': False},
                  'uiTestSummary': json.loads((ROOT / 'ui-tests.json').read_text(encoding='utf-8')) if (ROOT / 'ui-tests.json').exists() else {'status': '未実施', 'checks': []}})
        return s

    def action(self, payload, key):
        action = payload.get('action')
        if not isinstance(action, str):
            raise Rejected('AB-INPUT-001', '操作を指定してください。')
        if action in ['execute', 'access', 'bridge', 'upload', 'word']:
            with self.connect() as db:
                self.audit(db, '実行要求を停止', '停止', '未接続の機能を実行しません。外部送信・Access操作は0回。')
            raise Rejected('AB-EXEC-BLOCKED', 'この画面確認版では実行できません。外部接続・Access改修は停止中です。', 409)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            reqhash = sha(payload)
            receipt = db.execute('SELECT * FROM receipts WHERE key=?', (key,)).fetchone()
            if receipt:
                if receipt['request_hash'] != reqhash:
                    raise Rejected('AB-IDEMPOTENCY-001', '操作IDが重複しています。再読み込みしてください。', 409)
                return json.loads(receipt['response'])
            s = json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            if payload.get('revision') != s['revision']:
                raise Rejected('AB-VERSION-001', '別の画面で更新されています。再読み込みして確認してください。', 409)
            if payload.get('synthetic') is not True:
                raise Rejected('AB-PRIVACY-001', '架空の内容・画面への意見であることを確認してください。')
            data = payload.get('data', {})
            if not isinstance(data, dict):
                raise Rejected('AB-INPUT-002', '入力形式を確認してください。')
            self.reject_sensitive(data)
            message, event = '', ''
            if action == 'request':
                text = self.text(data, 'text', 1200)
                name = self.text(data, 'name', 80)
                target = self.choice(data, 'target', ['Access改修', '新規Access', 'Web', 'Excel・CSV', 'Java補助ツール'])
                entry = self.choice(data, 'entry', ['access', 'analysis'])
                count = data.get('inputCount', 0)
                types = data.get('inputTypes', [])
                if type(count) is not int or not 0 <= count <= 20 or not isinstance(types, list) or any(x not in ['accdb', 'mdb', 'csv', 'tsv', 'json', 'pdf', 'html', 'txt', 'xlsx'] for x in types):
                    raise Rejected('AB-INPUT-003', 'ファイルの種類と件数を確認してください。')
                s['request'] = {'name': name, 'text': text, 'target': target, 'entry': entry,
                                'purpose': self.text(data, 'purpose', 800, False), 'constraints': self.text(data, 'constraints', 800, False),
                                'privacy': 'synthetic', 'inputCount': count, 'inputTypes': types}
                mock = {'id': self.next_id(db, 'MOCK'), 'uuid': str(uuid.uuid4()), 'created': now(), 'kind': 'Classify', 'status': 'Mock',
                        'model': None, 'apiRequests': 0, 'inputHash': sha(s['request']), 'result': target}
                s['mockRuns'].append(mock)
                message, event = '依頼をローカル保存しました。質問案はモックです。', '依頼の版を保存'
            elif action == 'answer':
                qid = self.text(data, 'questionId', 40)
                if qid not in {q['id'] for q in s['questions']}:
                    raise Rejected('AB-QUESTION-001', '質問が見つかりません。')
                value = self.text(data, 'answer', 600, False)
                s['answers'][qid] = {'value': value, 'status': '回答済み' if value else '保留', 'id': self.next_id(db, 'ANS'), 'created': now()}
                message, event = ('回答を保存しました。' if value else '未回答のまま保留しました。'), '質問回答を保存'
            elif action == 'option':
                s['option'] = {'value': self.choice(data, 'value', ['A', 'B', 'C']), 'id': self.next_id(db, 'DEC'), 'created': now()}
                message, event = '案の選択を保存しました。実装承認とは別の記録です。', '案の選択を保存'
            elif action == 'issue':
                screen = self.choice(data, 'screen', list(SCREENS))
                issue = {'id': self.next_id(db, 'ISS'), 'uuid': str(uuid.uuid4()), 'screen': screen, 'screenId': SCREEN_IDS[screen],
                         'screenVersion': s['screenVersion'], 'designVersion': s['designVersion'],
                         'location': self.text(data, 'location', 100, False), 'text': self.text(data, 'text', 800),
                         'expected': self.text(data, 'expected', 400, False), 'priority': self.choice(data, 'priority', ['低', '中', '高']),
                         'state': '未対応', 'created': now()}
                s['issues'].append(issue)
                message, event = f"ご意見を保存しました：{issue['id']}", '画面への意見を保存'
            elif action == 'diff_review':
                if data.get('planHash') != s['planHash']:
                    raise Rejected('AB-HASH-001', '比較対象の版が変わっています。差分を再確認してください。', 409)
                s['diffReviewedHash'] = s['planHash']
                message, event = 'この版の差分確認を記録しました。', '差分の確認'
            elif action == 'approval':
                decision = self.choice(data, 'decision', ['確認済み', '差戻し', '保留', '却下'])
                if decision == '確認済み' and (s['diffReviewedHash'] != s['planHash'] or data.get('ack') is not True):
                    raise Rejected('AB-APPROVAL-001', '先に差分を確認し、画面構成だけの承認であることを確認してください。', 409)
                comment = self.text(data, 'comment', 600, decision != '確認済み')
                rec = {'id': self.next_id(db, 'APR'), 'uuid': str(uuid.uuid4()), 'decision': decision, 'scope': 'Web画面構成のみ',
                       'designVersion': s['designVersion'], 'screenVersion': s['screenVersion'], 'planHash': s['planHash'], 'diffId': s['diffId'],
                       'reviewer': 'ローカル利用者（本人確認機能は未実装）', 'created': now(), 'comment': comment, 'permitsExecution': False}
                s['approvals'].append(rec)
                message, event = f'{decision}を記録しました。Access改修や外部通信は開始しません。', '画面構成の判断を保存'
            elif action == 'export':
                aid = self.next_id(db, 'ART')
                report = {'kind': '画面レビュー記録', 'projectId': s['projectId'], 'screenVersion': s['screenVersion'],
                          'designVersion': s['designVersion'], 'issues': s['issues'], 'approvals': s['approvals'],
                          'requestId': s['requestId'], 'planHash': s['planHash'], 'exportedAt': now(),
                          'externalRequests': 0, 'accessExecuted': False, 'wordDocumentsCreated': False}
                content = json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8')
                file = self.exports / f'{aid}_レビュー記録.json'
                with file.open('xb') as output:
                    output.write(content)
                s['artifacts'].append({'id': aid, 'uuid': str(uuid.uuid4()), 'name': '画面レビュー記録', 'filename': file.name,
                                       'type': 'JSON', 'created': now(), 'sha256': hashlib.sha256(content).hexdigest(), 'state': '作成済み'})
                message, event = '今回のレビュー記録を書き出しました。', 'レビュー記録の出力'
            else:
                raise Rejected('AB-ACTION-001', 'この操作には対応していません。', 404)
            if action in ['request', 'answer', 'option', 'issue']:
                s['planHash'] = plan_hash(s)
                s['diffReviewedHash'] = None
            s['revision'] += 1
            s['updatedAt'] = now()
            db.execute('UPDATE state SET body=? WHERE id=1', (packed(s),))
            db.execute('INSERT INTO versions VALUES(?,?,?,?)', (s['revision'], packed(s), sha(s), now()))
            self.audit(db, event, '保存', f"画面版 {s['screenVersion']} / 記録版 {s['revision']} / 外部API・Access操作なし")
            response = {'ok': True, 'message': message, 'revision': s['revision']}
            db.execute('INSERT INTO receipts VALUES(?,?,?)', (key, reqhash, packed(response)))
            return response

    @staticmethod
    def text(data, key, limit, required=True):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise Rejected('AB-INPUT-004', f'入力欄を確認してください（最大{limit}文字）。')
        return value.strip()

    @staticmethod
    def choice(data, key, choices):
        value = data.get(key)
        if value not in choices:
            raise Rejected('AB-INPUT-005', '選択欄を確認してください。')
        return value

    @staticmethod
    def reject_sensitive(data):
        text = packed(data)
        patterns = [r'\bsk-[A-Za-z0-9_-]{12,}', r'-----BEGIN .*PRIVATE KEY', r'(?i)\b(?:private|public)\s+(?:sub|function)\b',
                    r'(?i)attribute\s+vb_name', r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', r'(?<!\d)0\d{1,3}[- ]\d{2,4}[- ]\d{3,4}(?!\d)']
        if any(re.search(p, text) for p in patterns):
            raise Rejected('AB-PRIVACY-002', '秘密情報・個人情報・ソースの候補を検出しました。保存せず停止しました。内容を伏せてください。')

class Handler(BaseHTTPRequestHandler):
    server_version = 'GenesisLocal/0.3'

    def log_message(self, *_):
        pass  # Never log request bodies or arbitrary URL text.

    def valid_host(self):
        return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}']

    def respond(self, code, data, content_type='application/json; charset=utf-8', extra=None):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8') if not isinstance(data, bytes) else data
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {'error': 'HOST_NOT_ALLOWED'})
        path = urlsplit(self.path).path
        if path == '/api/agent':
            state = self.server.agent.info()
            state['csrf'] = self.server.token
            return self.respond(200, state)
        if path.startswith('/api/agent/artifact/'):
            aid = path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'ART-[A-F0-9]{12}', aid):
                return self.respond(404, {'error': 'NOT_FOUND'})
            raw = self.server.agent.artifact(aid)
            if raw is None:
                return self.respond(404, {'error': 'NOT_FOUND'})
            return self.respond(200, raw, 'application/json; charset=utf-8',
                                {'Content-Disposition': f'attachment; filename="{aid}.json"'})
        if path == '/api/health':
            return self.respond(200, {'application': 'genesis-review', 'version': CONFIG['applicationVersion'], 'mode': 'local-preview', 'instance': sha(str(ROOT))})
        if path == '/api/state':
            state = self.server.store.state()
            state['artifacts'] += self.server.analysis.artifact_list()
            state['csrf'] = self.server.token
            return self.respond(200, state)
        if path == '/api/analysis':
            return self.respond(200, self.server.analysis.info())
        if path.startswith('/api/artifact/'):
            aid = path.rsplit('/', 1)[-1]
            artifact = next((x for x in self.server.store.state()['artifacts'] + self.server.analysis.artifact_list() if x['id'] == aid), None)
            if not artifact:
                return self.respond(404, {'error': 'NOT_FOUND'})
            file = self.server.store.exports / artifact['filename']
            try:
                data = file.read_bytes()
            except OSError:
                return self.respond(409, {'error': 'ARTIFACT_UNAVAILABLE'})
            if hashlib.sha256(data).hexdigest() != artifact['sha256']:
                return self.respond(409, {'error': 'ARTIFACT_HASH_MISMATCH'})
            return self.respond(200, data, mimetypes.guess_type(file.name)[0] or 'application/octet-stream', extra={'Content-Disposition': f'attachment; filename="{aid}{file.suffix}"'})
        allowed = {'/': 'agent.html', '/index.html': 'agent.html', '/workspace.html': 'index.html', '/styles.css': 'styles.css', '/app.js': 'app.js', '/favicon.svg': 'favicon.svg'}
        allowed.update({'/agent.css':'agent.css','/agent.js':'agent.js'})
        allowed.update({'/analysis.js':'analysis.js','/analysis.css':'analysis.css'})
        if path not in allowed:
            return self.respond(404, {'error': 'NOT_FOUND'})
        file = ROOT / 'static' / allowed[path]
        return self.respond(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or 'text/plain') + '; charset=utf-8')

    def do_POST(self):
        origin = self.headers.get('Origin')
        allowed_origins = [f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}']
        if not self.valid_host() or origin not in allowed_origins or self.headers.get('X-Genesis-Token') != self.server.token:
            return self.respond(403, {'error': 'REQUEST_NOT_ALLOWED', 'message': 'この端末の画面から操作してください。'})
        if urlsplit(self.path).path == '/api/shutdown':
            self.respond(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if urlsplit(self.path).path not in ['/api/action', '/api/agent/secret']:
            return self.respond(404, {'error': 'NOT_FOUND'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > CONFIG['maxRequestBytes']:
                raise Rejected('AB-SIZE-001', '入力が長すぎます。', 413)
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                raise Rejected('AB-FORMAT-001', 'JSON形式が必要です。', 415)
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(payload, dict):
                raise Rejected('AB-INPUT-002', '入力形式を確認してください。')
            if urlsplit(self.path).path == '/api/agent/secret':
                # Keys deliberately bypass all persistence, receipts and audit payloads.
                return self.respond(200, self.server.agent.secret(payload))
            key = self.headers.get('Idempotency-Key', '')
            if not re.fullmatch(r'[A-Za-z0-9-]{16,64}', key):
                raise Rejected('AB-ID-001', '操作IDを確認してください。')
            if str(payload.get('action','')).startswith('agent_'):
                result = self.server.agent.action(payload, key)
            elif str(payload.get('action','')).startswith('analysis_'):
                result = self.server.analysis.action(payload, key)
            else:
                result = self.server.store.action(payload, key)
            return self.respond(200, result)
        except Rejected as ex:
            return self.respond(ex.status, {'ok': False, 'code': ex.code, 'message': ex.message})
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {'ok': False, 'code': 'AB-JSON-001', 'message': '入力形式を確認してください。'})
        except Exception:
            return self.respond(500, {'ok': False, 'code': 'AB-SAVE-001', 'message': '保存できませんでした。入力を控え、保存場所を確認してください。'})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=CONFIG['port'])
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--exports-dir', type=Path, default=ROOT / 'exports')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.store = Store(args.data_dir, args.exports_dir)
    from analysis_store import Analysis
    server.analysis = Analysis(server.store, Rejected)
    from agent_core import Agent
    server.agent = Agent(args.data_dir, CONFIG, Rejected, Store.reject_sensitive)
    server.token = secrets.token_urlsafe(32)
    print(f'Genesis local review ready http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
