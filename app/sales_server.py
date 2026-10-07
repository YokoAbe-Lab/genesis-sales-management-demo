"""Genesis v07 extension: sales business pack, localhost only."""
import mimetypes
import json
import io
import threading
import pypdfium2 as pdfium
from urllib.parse import parse_qs, urlsplit, quote
import v07_server as genesis
from sales_bridge import SalesBridge, ROOT

class Handler(genesis.Handler):
    def do_GET(self):
        url=urlsplit(self.path)
        if not self.valid_host():
            return self.respond(403, {'error':'HOST_NOT_ALLOWED'})
        if url.path == '/api/health':
            return self.respond(200, {'application':'genesis-sales-web','version':'1.0','root':str(ROOT)})
        assets={'/sales':'sales.html','/sales.js':'sales.js','/sales.css':'sales.css'}
        if url.path in assets:
            p=ROOT/'app/static'/assets[url.path]
            return self.respond(200,p.read_bytes(),mimetypes.guess_type(p.name)[0]+'; charset=utf-8')
        if url.path=='/api/sales':
            q=parse_qs(url.query)
            try:
                data=self.server.sales.read(q.get('dataset',['work'])[0],q.get('refresh',['0'])[0]=='1').copy()
                result=ROOT/'検証/Web接続試験.json'
                data['webTests']=json.loads(result.read_text(encoding='utf-8')) if result.exists() else []
                return self.respond(200,data)
            except ValueError as exc:
                return self.respond(400,{'error':str(exc)})
        if url.path=='/api/sales/web-tests':
            p=ROOT/'検証/Web接続試験.csv'
            if not p.exists():return self.respond(404,{'error':'TESTS_UNAVAILABLE'})
            return self.respond(200,p.read_bytes(),'text/csv; charset=utf-8',extra={'Content-Disposition':'attachment; filename="genesis-sales-web-tests.csv"'})
        if url.path.startswith('/api/sales/preview/'):
            key=url.path.rsplit('/',1)[-1]
            p=self.server.sales.files.get(key)
            if not p or p.suffix.lower()!='.pdf' or not p.resolve().is_relative_to((ROOT/'components').resolve()):
                return self.respond(404,{'error':'PREVIEW_UNAVAILABLE'})
            try:
                page=int(parse_qs(url.query).get('page',['0'])[0])
                with self.server.preview_lock:
                    pdf=pdfium.PdfDocument(str(p))
                    try:
                        if page<0 or page>=len(pdf):raise ValueError()
                        bitmap=pdf[page].render(scale=1.5)
                        try:
                            buf=io.BytesIO();bitmap.to_pil().save(buf,format='PNG')
                            return self.respond(200,buf.getvalue(),'image/png',extra={'X-Page-Count':str(len(pdf))})
                        finally:bitmap.close()
                    finally:pdf.close()
            except Exception:return self.respond(400,{'error':'PREVIEW_FAILED'})
        if url.path.startswith('/api/sales/file/'):
            key=url.path.rsplit('/',1)[-1]
            p=self.server.sales.files.get(key)
            if not p or not p.is_file() or not p.resolve().is_relative_to((ROOT/'components').resolve()):
                return self.respond(404,{'error':'FILE_UNAVAILABLE'})
            raw=p.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',(mimetypes.guess_type(p.name)[0] or 'application/octet-stream')+(' ; charset=utf-8' if p.suffix=='.txt' else ''))
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Content-Disposition',"inline; filename*=UTF-8''"+quote(p.name))
            self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'self'")
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().do_GET()

def make_server(port=8773):
    server=genesis.make_server(port)
    server.RequestHandlerClass=Handler
    server.sales=SalesBridge()
    server.preview_lock=threading.Lock()
    return server

if __name__=='__main__':
    server=make_server()
    print('Genesis sales http://127.0.0.1:8773/sales',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
