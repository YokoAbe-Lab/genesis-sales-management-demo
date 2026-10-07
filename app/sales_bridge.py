"""Read-only sales adapter. All paths resolve inside this independent copy."""
import csv
import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent

class SalesBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}
        self.files = {}

    def register(self, path, kind, dataset):
        path = path.resolve()
        base = (ROOT / 'components' / dataset).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return None
        key = hashlib.sha256(str(path.relative_to(ROOT)).encode()).hexdigest()[:24]
        self.files[key] = path
        pages=0
        if path.suffix.lower()=='.pdf':
            try:pages=len(PdfReader(path).pages)
            except Exception:pass
        return {'id': key, 'name': path.name, 'kind': kind, 'pages':pages,'path': str(path.relative_to(base)), 'url': '/api/sales/file/' + key}

    def read(self, dataset, refresh=False):
        if dataset not in ('work', 'test'):
            raise ValueError('不明なデータ種別です。')
        with self.lock:
            if not refresh and dataset in self.cache:
                return self.cache[dataset]
            base = ROOT / 'components' / dataset
            exe = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            try:
                p = subprocess.run([str(exe), '-NoProfile', '-File', str(ROOT/'app/sales_read.ps1'), '-Database', str(base/'販売システム管理2.accdb')], capture_output=True, timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                data = json.loads(p.stdout.decode('utf-8-sig'))
            except Exception as exc:
                data = {'connected': False, 'tables': {}, 'errors': [{'section': 'Access', 'error': str(exc)}], 'checkedAt': datetime.now().astimezone().isoformat()}
            data.update(dataset=dataset, readOnly=True, artifacts=[], tests=[])
            for path in sorted((base/'実行履歴').rglob('*')):
                if path.suffix.lower() in ('.pdf', '.xlsx'):
                    artifact = self.register(path, 'PDF' if path.suffix.lower()=='.pdf' else 'Excel', dataset)
                    if artifact:
                        data['artifacts'].append(artifact)
            testfile = ROOT/'components/test/テスト結果一覧.csv'
            if testfile.exists():
                for row in csv.DictReader(testfile.open(encoding='utf-8-sig')):
                    raw = row.get('証跡ファイル', '').replace('\\', '/')
                    tail = raw.split('/試験_20261006_192701/', 1)[-1]
                    proof = self.register(ROOT/'components/test'/tail, '試験証跡', 'test') if tail != raw else None
                    row['evidence'] = proof
                    row['証跡ファイル'] = tail if proof else '未接続：証跡ファイルなし'
                    data['tests'].append(row)
            data['connections'] = [
                {'name':'Access 販売管理','status':'接続済（読取専用）' if data['connected'] else '未接続','detail':'このWeb専用コピーをDAOで読み込み'},
                {'name':'Excel 帳票','status':'保存済み出力に接続' if data['artifacts'] else '未接続（出力なし）','detail':'PDF・Excelの閲覧に対応。Webからの帳票生成・印刷実行は未接続'},
                {'name':'登録・更新','status':'未接続','detail':'今回のWeb入口は確認用。登録操作は有効表示しません'},
                {'name':'AI・RPA・外部送信','status':'未接続','detail':'販売管理から外部送信は行いません'}]
            self.cache[dataset] = data
            log = ROOT/'検証/web_connection.jsonl'
            log.parent.mkdir(exist_ok=True)
            with log.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'at':data['checkedAt'],'dataset':dataset,'access':data['connected'],'queryErrors':data['errors'],'artifacts':len(data['artifacts'])},ensure_ascii=False)+'\n')
            return data
