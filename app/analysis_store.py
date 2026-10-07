"""Analysis records link to the existing project, ID allocator, and audit log."""
import hashlib
import json
import uuid
from pathlib import Path
import analysis_core as core

class Analysis:
    def __init__(self, store, rejected):
        self.store,self.Rejected=store,rejected
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS analysis_runs(id TEXT PRIMARY KEY,body TEXT NOT NULL,hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS analysis_approvals(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS analysis_exports(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,body TEXT NOT NULL);''')

    def info(self):
        with self.store.connect() as db:
            runs=[json.loads(r[0]) for r in db.execute('SELECT body FROM analysis_runs ORDER BY rowid DESC')]
            exports=[json.loads(r[0]) for r in db.execute('SELECT body FROM analysis_exports ORDER BY rowid DESC')]
            approvals=[json.loads(r[0]) for r in db.execute('SELECT body FROM analysis_approvals ORDER BY rowid DESC')]
        return {'datasets':[{'id':k,'name':v[1]} for k,v in core.DATASETS.items()],
            'runs':[{'id':r['runId'],'created':r['created'],'chart':r['analysis']['config']['chart'],'name':r['analysis']['source']['name'],'hash':r['hash'],'requestId':r['requestId']} for r in runs],
            'approvals':approvals,'exports':exports,'charts':core.CHARTS}

    def get_run(self,db,rid):
        row=db.execute('SELECT * FROM analysis_runs WHERE id=?',(rid,)).fetchone()
        if not row: raise self.Rejected('AN-RUN-404','保存済みの分析が見つかりません。',404)
        r=json.loads(row['body'])
        if r['hash']!=row['hash'] or core.digest({k:v for k,v in r.items() if k!='hash'})!=r['hash']:
            raise self.Rejected('AN-HASH-409','保存記録のハッシュが一致しないため停止しました。',409)
        return r

    def artifact_list(self):
        return [f for x in self.info()['exports'] for f in x['files'] if f['status']=='作成済み']

    def action(self,payload,key):
        data=payload.get('data',{})
        if not isinstance(data,dict): raise self.Rejected('AN-INPUT','入力形式が不正です。')
        action=payload.get('action')
        self.store.reject_sensitive(data)
        if payload.get('synthetic') is not True: raise self.Rejected('AN-PRIVACY','サンプルと画面確認の内容だけを扱います。')
        try:
            if action=='analysis_preview':
                a=core.analyze(data.get('config',{}));a['previewHash']=core.digest({'config':a['config'],'source':a['source']['sha256']})
                return {'ok':True,'analysis':core.for_browser(a)}
            if action=='analysis_load':
                with self.store.connect() as db:r=self.get_run(db,data.get('runId'))
                return {'ok':True,'run':r,'analysis':core.for_browser(r['analysis'])}
            with self.store.lock,self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                reqhash=core.digest(payload)
                receipt=db.execute('SELECT * FROM receipts WHERE key=?',(key,)).fetchone()
                if receipt:
                    if receipt['request_hash']!=reqhash: raise self.Rejected('AN-IDEMPOTENCY','同じ操作IDの内容が異なります。',409)
                    return json.loads(receipt['response'])
                if action=='analysis_save':
                    a=core.analyze(data.get('config',{}))
                    expected=core.digest({'config':a['config'],'source':a['source']['sha256']})
                    if data.get('previewHash')!=expected: raise self.Rejected('AN-SOURCE-CHANGED','条件または元サンプルが変わりました。表示を更新して確認してください。',409)
                    if not a['config']['audience'].strip() or not a['config']['decision'].strip(): raise self.Rejected('AN-QUESTION','説明する相手と判断したいことを入力してください。')
                    edits=data.get('edits',{})
                    if not isinstance(edits,dict) or set(edits)-set(a['generated']): raise self.Rejected('AN-EDIT','文章の編集項目を確認してください。')
                    a['finalText']={k:self.store.text(edits,k,1200,False) if k in edits else v for k,v in a['generated'].items()}
                    if any(not t for t in a['finalText'].values()): raise self.Rejected('AN-EDIT','資料の説明欄を空欄にできません。')
                    s=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
                    rid=self.store.next_id(db,'RUN-AN')
                    prev=db.execute('SELECT body FROM analysis_runs ORDER BY rowid DESC LIMIT 1').fetchone()
                    previous=json.loads(prev[0]) if prev else None
                    diff={'previousRunId':previous['runId'] if previous else None,'status':'初回保存'}
                    if previous:
                        pa=previous['analysis']
                        diff.update(status='前回保存との差分',sourceChanged=pa['source']['sha256']!=a['source']['sha256'],changedSettings=[k for k,v in a['config'].items() if pa['config'].get(k)!=v],rowCountDelta=a['summary']['count']-pa['summary']['count'],editedSections=[k for k in a['finalText'] if pa.get('finalText',pa['generated']).get(k)!=a['finalText'][k]])
                    r={'runId':rid,'uuid':str(uuid.uuid4()),'requestId':s['requestId'],'projectId':s['projectId'],'projectName':s['request']['name'],'requestRevision':s['revision'],'created':core.stamp(),
                      'questionAnswers':[{'questionId':self.store.next_id(db,'QST-AN'),'item':k,'answer':a['config'][k]} for k in ['goal','audience','decision']],
                      'agentRunId':self.store.next_id(db,'AGR-AN'),'agentStatus':'LocalRule','model':None,'externalRequests':0,
                      'analysis':a,'diff':diff,'testCaseIds':a['testCaseIds'],'generatorVersion':'0.4-analysis.1','approvalScope':'この分析Runの図表と修正文を資料出力する'}
                    r['hash']=core.digest(r)
                    db.execute('INSERT INTO analysis_runs VALUES(?,?,?)',(rid,core.canonical(r),r['hash']))
                    response={'ok':True,'message':'分析と文章を新しいRunIDで保存しました。','run':r}
                    self.store.audit(db,'分析Runを保存','保存',f'{rid} / {s["requestId"]} / 架空データ / 外部送信0')
                elif action=='analysis_approve':
                    r=self.get_run(db,data.get('runId'))
                    if data.get('hash')!=r['hash'] or data.get('ack') is not True: raise self.Rejected('AN-APPROVAL','図表・文章・除外行を確認し、対象版を一致させてください。',409)
                    old=db.execute('SELECT body FROM analysis_approvals WHERE run_id=?',(r['runId'],)).fetchone()
                    if old: approval=json.loads(old[0])
                    else:
                        approval={'id':self.store.next_id(db,'APR'),'runId':r['runId'],'hash':r['hash'],'created':core.stamp(),'scope':r['approvalScope'],'decision':'確認済み','permitsAccessOrApi':False,'reviewer':'ローカル利用者（本人認証なし）'}
                        db.execute('INSERT INTO analysis_approvals VALUES(?,?,?)',(approval['id'],r['runId'],core.canonical(approval)))
                        self.store.audit(db,'分析資料の承認','確認済み',f'{r["runId"]} / {approval["id"]} / Access・APIの実行権限なし')
                    response={'ok':True,'message':'この分析Runの資料出力を承認しました。','approval':approval}
                elif action=='analysis_export':
                    r=self.get_run(db,data.get('runId'))
                    row=db.execute('SELECT body FROM analysis_approvals WHERE run_id=? ORDER BY rowid DESC LIMIT 1',(r['runId'],)).fetchone()
                    if not row or json.loads(row[0])['hash']!=r['hash']: raise self.Rejected('AN-NOT-APPROVED','保存した図表と文章を承認してから出力してください。',409)
                    format=data.get('format')
                    if format not in ['docx','pdf','html','xlsx','png','json','all']: raise self.Rejected('AN-FORMAT','出力形式を確認してください。')
                    from analysis_export import export_files
                    exportId=self.store.next_id(db,'EXP-AN');folder=self.store.exports/exportId
                    folder.mkdir(exist_ok=False)
                    record={'id':exportId,'runId':r['runId'],'approvalId':json.loads(row[0])['id'],'created':core.stamp(),'folder':str(folder),'files':[],'analysisReexecuted':False}
                    formats=['docx','pdf','html','xlsx','png','json'] if format=='all' else [format]
                    for ext in formats:
                        aid=self.store.next_id(db,'ART')
                        rec={'id':aid,'name':'分析報告書' if ext in ['docx','pdf','html'] else '集計結果' if ext=='xlsx' else 'グラフ画像' if ext=='png' else '分析条件と根拠','type':ext.upper(),'filename':f'{exportId}/{aid}.{ext}','runId':r['runId'],'approvalId':record['approvalId'],'created':core.stamp()}
                        try:
                            file=folder/f'{aid}.{ext}'
                            export_files(r,json.loads(row[0]),file)
                            rec.update(status='作成済み',state='作成済み',sha256=hashlib.sha256(file.read_bytes()).hexdigest())
                        except Exception as ex:
                            rec.update(status='失敗',state='失敗',errorCode=type(ex).__name__,sha256=None)
                        record['files'].append(rec)
                    record['status']='成功' if all(f['status']=='作成済み' for f in record['files']) else '一部または全件失敗'
                    db.execute('INSERT INTO analysis_exports VALUES(?,?,?)',(exportId,r['runId'],core.canonical(record)))
                    self.store.audit(db,'分析資料の出力',record['status'],f'{exportId} / {r["runId"]} / 保存済みRunのみ使用・再分析なし')
                    response={'ok':True,'message':'出力結果を保存しました。','export':record}
                else: raise self.Rejected('AN-ACTION','未対応の分析操作です。')
                db.execute('INSERT INTO receipts VALUES(?,?,?)',(key,reqhash,core.canonical(response)))
                return response
        except ValueError as ex:
            raise self.Rejected('AN-INPUT',str(ex))
