"""One authorised integration request. Credentials never enter persisted state."""
import hashlib
import http.client
import json
import re
import sqlite3
import ssl
import threading
from pathlib import Path
from agent_core import encode, validate, obj, arr, STR
from excel_static import stamp, identifier, sha_file, dump, ScanError

SCHEMA = obj(summary=STR, findings=arr(STR), limits=arr(STR), suggestions=arr(STR))
PROMPT_VERSION = 'EXCEL-ANON-SUMMARY-1.0'
INSTRUCTIONS = ('架空の標準テストExcelの匿名化した解析件数だけを読み、日本語で短く説明してください。'
                '事実は件数と状態に限り、静的解析を実行成功と混同しないでください。'
                'ファイル名、パス、コード、個人情報を推測しないでください。'
                'summaryは概要、findingsは確認事実、limitsは限界、suggestionsは確認案です。')


class OneShot:
    def __init__(self, root, analyzer, model):
        self.root=Path(root); self.analyzer=analyzer; self.model=model
        self.folder=self.root.parent/'検証/v07/AI連携'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.dbpath=self.folder/'one_shot.sqlite3'; self.key=''; self.lock=threading.Lock()
        with sqlite3.connect(self.dbpath) as db:
            db.execute('CREATE TABLE IF NOT EXISTS Slot(ID INTEGER PRIMARY KEY CHECK(ID=1), Body TEXT NOT NULL)')

    def read(self):
        with sqlite3.connect(self.dbpath) as db:
            row=db.execute('SELECT Body FROM Slot WHERE ID=1').fetchone()
        return json.loads(row[0]) if row else None

    def info(self):
        r=self.read()
        return {'record':r,'keyRegistered':bool(self.key),'requestLimit':1,
                'additionalApiRequests':r.get('apiRequests',0) if r else 0,
                'model':self.model,'accessStorage':'未接続','promptVersion':PROMPT_VERSION}

    def set_key(self, key):
        with self.lock:
            if self.read(): raise ScanError('SINGLE_REQUEST_ALREADY_RESERVED')
            if not isinstance(key,str) or not re.fullmatch(r'sk-[A-Za-z0-9_-]{16,250}',key):
                raise ScanError('KEY_FORMAT_INVALID')
            self.key=key
        return {'ok':True,'keyRegistered':True,'apiRequests':0}

    def prepare(self):
        manifest_path=self.root.parent/'検証/v07/標準Run.json'
        if not manifest_path.exists(): raise ScanError('STANDARD_TEST_NOT_READY')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        run=self.analyzer.detail(manifest['runId'])
        expected_path=self.root.parent/'標準テストExcel/v07/standard_features.xlsm'
        if (Path(run['sourcePath']).resolve()!=expected_path.resolve() or
            run['copySHA256']!=sha_file(expected_path) or not run['sourceUnchanged'] or run['status']!='SUCCESS'):
            raise ScanError('STANDARD_FIXTURE_NOT_VERIFIED')
        f=run['workbookFeatures']['counts']
        # Construct solely from numerical facts. No input free text is forwarded.
        summary={'dataset':'synthetic-standard-excel','analysisMode':'local-static',
                 'moduleCount':int(run['moduleCount']),'procedureCount':int(run['procedureCount']),
                 'relationCount':int(run['relationCount']),
                 'features':{k:int(f[k]) for k in ['formulas','conditionalFormats','validations','tables','definedNames','filters','charts','shapes','onActions']},
                 'originalUnchanged':True,'macrosExecuted':False,'accessDatabaseConnected':False}
        body={'model':self.model,'store':False,'reasoning':{'effort':'low'},'max_output_tokens':1800,
              'instructions':INSTRUCTIONS,'input':encode(summary),
              'text':{'format':{'type':'json_schema','name':'genesis_excel_summary','strict':True,'schema':SCHEMA}}}
        raw=encode(body).encode('utf-8')
        return run,summary,raw

    def execute(self):
        with self.lock:
            if self.read(): raise ScanError('SINGLE_REQUEST_ALREADY_RESERVED')
            if not self.key: raise ScanError('KEY_MISSING')
            testfile=self.root.parent/'検証/v07/自動試験結果.json'
            if not testfile.exists():raise ScanError('LOCAL_TESTS_NOT_READY')
            tests=json.loads(testfile.read_text(encoding='utf-8'))
            features=tests.get('featureTests',[])
            if tests.get('passed')!=40 or tests.get('failed') or tests.get('notRun') or len(features)!=9 or not all(x['status']=='PASS' for x in features):
                raise ScanError('LOCAL_TESTS_NOT_PASSED')
            run,summary,raw=self.prepare()
            record={'requestId':identifier('REQ-AI'),'runId':run['runId'],'model':self.model,
                    'promptVersion':PROMPT_VERSION,'apiRequests':0,'created':stamp(),'finished':None,
                    'status':'RESERVED','responseStatus':'NOT_RECEIVED','formatStatus':'NOT_TESTED',
                    'inputTokens':None,'outputTokens':None,'totalTokens':None,'actualCost':None,
                    'costStatus':'未確認','usageSource':'API応答のusage','httpStatus':None,
                    'sentContentSHA256':hashlib.sha256(raw).hexdigest(),'responseContentSHA256':None,
                    'diagnostic':'','responseArtifact':None,'providerRequestId':None}
            # A unique durable slot also blocks simultaneous processes and restarts.
            with sqlite3.connect(self.dbpath) as db:
                try: db.execute('INSERT INTO Slot VALUES(1,?)',(encode(record),))
                except sqlite3.IntegrityError: raise ScanError('SINGLE_REQUEST_ALREADY_RESERVED') from None
            (self.folder/'送信内容.json').write_bytes(raw)
            dump(self.folder/'匿名化概要.json',summary)
            key=self.key
            conn=http.client.HTTPSConnection('api.openai.com',timeout=55,context=ssl.create_default_context())
            try:
                # Persist the attempt before entering network I/O. No retry on uncertainty.
                record.update(apiRequests=1,status='RUNNING');self.save(record)
                conn.request('POST','/v1/responses',body=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
                res=conn.getresponse(); response=res.read(1000001)
                record.update(httpStatus=res.status,responseStatus='RECEIVED',providerRequestId=res.getheader('x-request-id'))
                (self.folder/'API応答.bin').write_bytes(response)
                record.update(responseContentSHA256=hashlib.sha256(response).hexdigest(),responseArtifact='API応答.bin')
                if len(response)>1000000: raise ScanError('RESPONSE_SIZE_LIMIT')
                parsed=json.loads(response)
                usage=parsed.get('usage') or {}
                for src,dst in [('input_tokens','inputTokens'),('output_tokens','outputTokens'),('total_tokens','totalTokens')]:
                    record[dst]=usage[src] if type(usage.get(src)) is int and usage[src]>=0 else None
                record['responseModel']=parsed.get('model')
                record['providerResponseStatus']=parsed.get('status')
                if res.status!=200: raise ScanError('HTTP_'+str(res.status))
                if parsed.get('status')!='completed': raise ScanError('RESPONSE_NOT_COMPLETED')
                texts=[c['text'] for item in parsed.get('output',[]) if item.get('type')=='message'
                       for c in item.get('content',[]) if c.get('type')=='output_text']
                value=json.loads(''.join(texts));validate(value,SCHEMA)
                dump(self.folder/'AI応答.json',value)
                record.update(status='PASS',formatStatus='PASS',responseStatus='COMPLETED')
            except Exception as ex:
                record.update(status='FAILED',formatStatus='FAILED',diagnostic=str(ex) if isinstance(ex,ScanError) else type(ex).__name__)
                if record['responseStatus']=='NOT_RECEIVED': record['responseStatus']='UNCONFIRMED'
            finally:
                conn.close();self.key='';key=''
                record['finished']=stamp();self.save(record)
            return record

    def save(self,record):
        with sqlite3.connect(self.dbpath) as db:db.execute('UPDATE Slot SET Body=? WHERE ID=1',(encode(record),))
        dump(self.folder/'AI連携記録.json',record)
