"""Offline release checks; creates only local synthetic analysis records."""
import hashlib
import json
import sys
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from sales_server import make_server
from analysis_core import analyze

results=[]
def check(name, expected, actual):
    results.append(dict(name=name,expected=expected,actual=actual,passed=expected==actual))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

server=make_server(18773)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path,payload=None,token=True):
    headers={}
    body=None
    if payload is not None:
        body=json.dumps(payload).encode()
        headers={'Content-Type':'application/json','Origin':base,'Idempotency-Key':str(uuid.uuid4())}
        if token:headers['X-Genesis-Token']=server.token
    try:
        with opener.open(urllib.request.Request(base+path,data=body,headers=headers),timeout=60) as r:
            raw=r.read();return r.status,json.loads(raw) if 'application/json' in r.headers.get('Content-Type','') else raw
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())

try:
    for path in ['/','/sales','/sales.js','/sales.css','/agent.js','/agent.css','/excel','/excel.js','/integration','/api/state','/api/agent','/api/analysis']:
        code,_=request(path);check('GET '+path,200,code)
    for dataset in ['work','test']:
        p=ROOT/'components'/dataset/'販売システム管理2.accdb';before=sha(p)
        code,d=request('/api/sales?dataset='+dataset+'&refresh=1')
        check(dataset+' Access connection',True,d['connected'])
        check(dataset+' SQL errors',0,len(d['errors']))
        check(dataset+' outstanding amount',6000,d['metrics']['請求残高'])
        check(dataset+' source database preserved',before,sha(p))
        for table in ['quotes','orders','deliveries','sales','invoices','payments','allocations','trace']:
            check(dataset+' '+table+' fixture rows',1,len(d['tables'][table]))
    check('Invalid dataset rejected',400,request('/api/sales?dataset=../work')[0])
    check('Unknown artifact rejected',404,request('/api/sales/file/not-present')[0])
    check('Missing CSRF token rejected',403,request('/api/excel/run',{'sample':'standard.xlsx'},False)[0])
    for sample in ['standard.xlsx','standard.xlsm','standard.xlam','standard.xls','standard.xlsb','v07/standard_features.xlsm','external.xlsm']:
        p=ROOT/'標準テストExcel'/sample;before=sha(p)
        code,d=request('/api/excel/run',{'sample':sample})
        check('Excel '+sample+' accepted',True,code==200 and d.get('ok',False))
        check('Excel '+sample+' original preserved',before,sha(p))
        if sample=='v07/standard_features.xlsm' and d.get('ok'):
            code,export=request('/api/excel/export',{'runId':d['runId']})
            check('Static analysis export',True,code==200 and export.get('ok',False))
    code,d=request('/api/excel/run',{'sample':'corrupt.xlsm'})
    check('Corrupt workbook rejected',False,d.get('ok',False))
    analysis=analyze({'dataset':'sales','chart':'bar'})
    check('Synthetic analysis available',True,bool(analysis))
    check('Live AI calls',0,server.ai_once.info()['additionalApiRequests'])
finally:
    server.shutdown();server.server_close();thread.join(timeout=5)
out=ROOT/'docs/test-results.json';out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({'scope':'Offline release checks with fictional fixtures; no real AI request or desktop registration test success claimed.',
                           'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'checks':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'failures':[r for r in results if not r['passed']]},ensure_ascii=False))
sys.exit(any(not r['passed'] for r in results))
