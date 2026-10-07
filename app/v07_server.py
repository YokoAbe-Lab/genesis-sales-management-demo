"""Preserves v06 handlers; adds a single-use, summary-only AI test boundary."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import excel_server as base
from excel_static import ScanError, sha_file
from ai_once import OneShot

ROOT=Path(__file__).resolve().parent

class Handler(base.Handler):
    def respond(self,code,data,content_type='application/json; charset=utf-8',extra=None):
        if isinstance(data,dict) and urlsplit(self.path).path=='/api/excel':
            data['additionalApiRequests']=self.server.ai_once.info()['additionalApiRequests']
            data['aiTest']=self.server.ai_once.info()
            data['accessStorage']='未接続'
            for key,file in [('tests','自動試験結果.json'),('delivery','納品一覧.json')]:
                p=ROOT.parent/'検証/v07'/file
                if p.exists():data[key]=json.loads(p.read_text(encoding='utf-8'))
            data['samples']=list(dict.fromkeys(['v07/standard_features.xlsm']+data['samples']))
        return super().respond(code,data,content_type,extra)

    def do_GET(self):
        path=urlsplit(self.path).path
        if not self.valid_host():return self.respond(403,{'error':'HOST_NOT_ALLOWED'})
        if path=='/api/v07/ai':
            return self.respond(200,self.server.ai_once.info()|{'csrf':self.server.token})
        if path=='/api/v07/preview':
            try:
                run,summary,raw=self.server.ai_once.prepare()
                return self.respond(200,{'runId':run['runId'],'summary':summary,'model':self.server.ai_once.model})
            except ScanError as e:return self.respond(409,{'error':str(e)})
        if path in ['/integration','/integration.js']:
            f=ROOT/'static'/('integration.html' if path=='/integration' else 'integration.js')
            return self.respond(200,f.read_bytes(),'text/html; charset=utf-8' if path=='/integration' else 'text/javascript; charset=utf-8')
        if path=='/api/health':return self.respond(200,{'application':'genesis-excel-v07','version':'0.7.0','additionalApiRequests':self.server.ai_once.info()['additionalApiRequests']})
        if path.startswith('/api/v07/delivery/'):
            try:
                index=json.loads((ROOT.parent/'検証/v07/納品一覧.json').read_text(encoding='utf-8'))
                row=next(x for x in index if x['id']==path.rsplit('/',1)[-1]);file=ROOT.parent/row['path']
                if not file.resolve().is_relative_to(ROOT.parent.resolve()) or sha_file(file)!=row['sha256']:raise ValueError()
                return self.respond(200,file.read_bytes(),base.mimetypes.guess_type(file.name)[0] or 'application/octet-stream',extra={'Content-Disposition':"attachment; filename*=UTF-8''"+base.quote(file.name)})
            except Exception:return self.respond(404,{'error':'DELIVERY_UNAVAILABLE'})
        return super().do_GET()

    def do_POST(self):
        path=urlsplit(self.path).path
        if path not in ['/api/v07/key','/api/v07/ai-once']:return super().do_POST()
        origins=[f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}']
        if not self.valid_host() or self.headers.get('Origin') not in origins or self.headers.get('X-Genesis-Token')!=self.server.token:
            return self.respond(403,{'error':'REQUEST_NOT_ALLOWED'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=2000:raise ScanError('INPUT_INVALID')
            data=json.loads(self.rfile.read(size))
            result=self.server.ai_once.set_key(data.get('key')) if path.endswith('/key') else self.server.ai_once.execute()
            return self.respond(200,result)
        except ScanError as e:return self.respond(409,{'error':str(e)})
        except Exception:return self.respond(500,{'error':'LOCAL_REQUEST_FAILED'})

def make_server(port=8772):
    host=base.make_server(port);host.RequestHandlerClass=Handler
    host.ai_once=OneShot(ROOT,host.excel,base.existing.CONFIG['agentModel'])
    return host

if __name__=='__main__':
    server=make_server()
    print('Genesis v07 http://127.0.0.1:8772/excel',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
