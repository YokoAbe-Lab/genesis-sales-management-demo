'use strict';
const AnalysisUI=(()=>{
 let a=null,info=null,run=null,edits={},dirty=false,pending=false,loading=false,failed=false;
 const goals={compare:'違いを比べる',time:'時間の変化を見る',share:'割合を見る',relation:'数値の関係を見る'};
 const charts={kpi:'KPIカード',bar:'棒グラフ',horizontal:'横棒グラフ',line:'折れ線グラフ',stack:'積み上げ棒グラフ',share:'構成比グラフ',scatter:'散布図',heat:'ヒートマップ',table:'集計表',pivot:'ピボット形式の表'};
 const approval=()=>run&&info?.approvals.find(x=>x.runId===run.runId&&x.hash===run.hash);
 const opt=(list,value)=>Object.entries(list).map(([k,v])=>'<option value="'+esc(k)+'" '+(k===value?'selected':'')+'>'+esc(v)+'</option>').join('');
 const select=(name,label,list,value)=>'<label class="an-field"><span>'+label+'</span><select name="'+name+'">'+opt(list,value)+'</select></label>';
 const cfg=()=>{const f=document.querySelector('#analysis-settings');if(!f)return a?.config||{};return {...Object.fromEntries(new FormData(f)),includeOutliers:f.elements.includeOutliers.checked};};
 async function api(action,data){const res=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Genesis-Token':state.csrf,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({action,data,synthetic:true})});const out=await res.json();if(!res.ok)throw Error(out.message||'処理を完了できませんでした。');return out;}
 async function infoLoad(){const res=await fetch('/api/analysis');if(!res.ok)throw Error('分析履歴を取得できません。');info=await res.json();}
 function redraw(){if(route==='analysis')render(false);}
 function setStatus(text){const s=document.querySelector('#an-live');if(s)s.textContent=text;}
 async function preview(config,confirmEdits=false){
  if(loading)return;if(confirmEdits&&Object.keys(edits).length&&!confirm('文章の修正を反映する前に条件を変えます。未保存の文章を置き換えてよいですか？'))return;
  loading=true;setStatus('データ点検と集計をしています…');
  try{const result=await api('analysis_preview',{config});a=result.analysis;run=null;edits={};dirty=true;pending=false;failed=false;await infoLoad();redraw();}
  catch(e){failed=true;setStatus(e.message);toast(e.message,true);}
  finally{loading=false;}
 }
 function page(){
  if(!a)return head('分析画面 0.4 ・ データから伝わる資料へ','分析・読み解き資料作成','最初に架空サンプルで、使い方を確認します。')+'<section class="panel"><p id="an-live">サンプルを準備しています…</p><button class="button primary" id="an-retry">サンプルを読み込む</button></section>';
  const c=a.config,approved=approval(),source=a.source;
  return head('分析画面 0.4 ・ データから伝わる資料へ','分析・読み解き資料作成','比べたいことを選び、図表と説明を確認して資料にまとめます。',badge(approved&&!dirty&&!pending?'この分析を確認済み':'内容の確認待ち',!approved||dirty||pending))+
  '<div class="an-stage"><span class="active">1 データと目的</span><b>→</b><span class="active">2 グラフと説明</span><b>→</b><span class="'+(approved?'active':'')+'">3 確認して資料にする</span><span class="an-local">ローカル推薦・AI未接続</span></div>'+
  '<div class="an-overview"><div><small>案件</small><strong>'+esc(state.request.name)+'</strong></div><div><small>データ</small><strong>'+esc(source.name)+'</strong></div><div><small>対象期間</small><strong>'+esc(a.period)+'</strong></div><div><small>対象／元データ</small><strong>'+a.summary.count+' / '+a.evidence.length+' 行</strong></div><button id="an-checks" class="an-check '+(a.qualityRows?'warning':'good')+'">点検 '+(a.qualityRows?'注意 '+a.qualityRows+'行':'問題なし')+'　根拠を見る ↗</button></div>'+
  '<div class="an-layout"><aside class="an-controls"><form id="analysis-settings"><h2>何を知りたいですか</h2>'+select('goal','知りたいこと',goals,c.goal)+
  select('dataset','内蔵サンプル',Object.fromEntries(info.datasets.map(d=>[d.id,d.name])),c.dataset)+
  '<details class="an-connect"><summary>実ファイルとの接続予定</summary><p>画面確認後に、Excel → CSV → Access結果の順で接続します。今は内蔵サンプルのみです。</p><button type="button" disabled>Excel・CSV・Access結果を接続</button></details>'+
  select('measure','集計する数値',{'':'数値なし・件数',...Object.fromEntries(source.fields.filter(f=>['金額','数量'].includes(f)).map(f=>[f,f]))},c.measure)+
  select('group','何で分類しますか',Object.fromEntries(source.fields.filter(f=>['地区','商品','状態'].includes(f)).map(f=>[f,f])),c.group)+
  select('aggregate','集計方法',{sum:'合計',mean:'平均',count:'件数'},c.aggregate)+
  '<details class="an-advanced"><summary>期間・絞り込み・詳しい設定</summary>'+
  select('dateField','日付項目',{'':'日付なし',...('日付' in Object.fromEntries(source.fields.map(f=>[f,1]))?{'日付':'日付'}:{})},c.dateField)+
  '<label class="an-field"><span>開始日</span><input type="date" name="from" value="'+esc(c.from)+'"></label><label class="an-field"><span>終了日</span><input type="date" name="to" value="'+esc(c.to)+'"></label>'+
  select('region','地区で絞り込み',{'全て':'全て','A地区':'A地区','B地区':'B地区','C地区':'C地区'},c.region)+
  select('secondary','色分け・表の列',{地区:'地区',商品:'商品',状態:'状態'},c.secondary)+
  '<label class="check-line"><input type="checkbox" name="includeOutliers" '+(c.includeOutliers?'checked':'')+'>外れ値候補も含める</label><p class="micro">空欄・型エラー・ID重複の行は除外します。外れ値候補は初期設定では保留します。</p></details>'+
  '<details class="an-advanced"><summary>説明する相手と判断の目的</summary><label class="an-field"><span>誰に説明しますか</span><input name="audience" maxlength="180" value="'+esc(c.audience)+'"></label><label class="an-field"><span>何を判断したいですか</span><textarea name="decision" rows="3" maxlength="180">'+esc(c.decision)+'</textarea></label></details>'+
  '<input type="hidden" name="chart" value="'+esc(c.chart)+'"><button type="submit" class="button primary an-apply">条件を反映する</button><p class="micro">条件を変えても元データは変わりません。</p></form></aside>'+
  '<section class="an-center"><div class="an-kpis">'+a.cards.map(x=>'<button class="an-kpi" data-an-evidence><span>'+esc(x.label)+'</span><strong>'+esc(x.value)+'</strong><small>'+esc(x.unit)+'</small></button>').join('')+'</div>'+
  '<section class="an-feature"><div><span class="an-kind fact">事実</span><strong>このグラフの最大の特徴</strong></div><p>'+esc(a.feature)+'</p><button class="text-button" id="an-feature-evidence">数値と条件の根拠を見る ↗</button></section>'+
  '<section class="an-chart-panel"><div class="an-chart-heading"><h2>グラフ</h2><button class="text-button" id="an-zoom">拡大する ⤢</button></div>'+
  '<div class="an-chart-types" role="group" aria-label="グラフの種類">'+Object.entries(charts).map(([k,v])=>'<button data-chart="'+k+'" class="'+(c.chart===k?'selected':'')+'" aria-pressed="'+(c.chart===k)+'">'+v+'</button>').join('')+'</div>'+
  '<div class="an-recommend"><p><strong>おすすめ</strong> '+esc(a.recommendation.reason)+'</p><button id="an-recommend" class="text-button">このグラフを選ぶ →</button></div>'+
  '<button class="an-chart-image" id="an-chart-evidence" aria-label="グラフの元データを表示"><img src="'+a.chartImage+'" alt="'+esc(charts[c.chart])+' '+esc(a.feature)+'"></button>'+
  '<p class="an-caption">グラフや数値をクリックすると、元の行・除外理由を確認できます。'+(c.chart==='scatter'?'横軸は数量、縦軸は金額です。因果関係は未確認です。':'上の最大・最小・平均は対象行の値です。折れ線は月別集計の値です。')+'</p>'+
  '<div class="an-warning '+(a.qualityRows?'has-warning':'')+'">'+(a.qualityRows?'注意がある行を保持しています。除外条件は「点検」で確認してください。':'点検した必須項目・数値・日付に問題は見つかりませんでした。')+'</div></section>'+
  '<details class="panel an-history"><summary>保存した分析と前回との差分</summary><label class="an-field"><span>保存済みの分析</span><select id="an-history-select"><option value="">選んでください</option>'+info.runs.map(r=>'<option value="'+r.id+'" '+(run?.runId===r.id?'selected':'')+'>'+r.id+' / '+esc(r.name)+' / '+esc(charts[r.chart])+'</option>').join('')+'</select></label>'+
  '<button class="button secondary" id="an-rerun">同じ条件で再分析する</button><p class="micro">保存済みの表示・出力は再分析しません。このボタンだけが元サンプルを読み直します。</p>'+
  '<p>前回データとの比較：'+esc(a.priorData.status)+(a.priorData.changed!==null?'／変更 '+a.priorData.changed+'行、追加 '+a.priorData.added+'行、削除 '+a.priorData.removed+'行':'')+'</p>'+
  (run?'<p>前回の保存：'+esc(run.diff.previousRunId||'なし')+'<br>設定差分：'+esc((run.diff.changedSettings||[]).join('、')||'なし')+'／行数差 '+(run.diff.rowCountDelta??0)+'</p><details class="an-trace"><summary>判断と成果物をつなぐID</summary>'+table(['種類','ID'],[['RequestID',esc(run.requestId)],['QuestionID',esc(run.questionAnswers.map(q=>q.questionId).join(' / '))],['ApprovalID',esc(approved?.id||'承認待ち')],['AgentRunID',esc(run.agentRunId)+' LocalRule（AI未接続）'],['TestCaseID',esc(run.testCaseIds.join(' / '))],['ArtifactID',esc(info.exports.filter(x=>x.runId===run.runId).flatMap(x=>x.files.map(f=>f.id)).join(' / ')||'未出力')]])+'</details>':'<p>今回の分析は未保存です。</p>')+'</details></section>'+
  '<aside class="an-reading"><h2>読み解き資料</h2><p class="an-reading-intro">文章は修正できます。原因の断定はしていません。</p><div class="an-legend"><span class="an-kind fact">事実</span><span class="an-kind read">読み解き</span><span class="an-kind guess">推測</span><span class="an-kind suggest">提案</span></div>'+
  a.sections.map(([k,kind,title],i)=>'<details class="an-section" '+(i===0||k==='action'?'open':'')+'><summary><span class="an-kind '+({事実:'fact',読み解き:'read',推測:'guess',提案:'suggest'}[kind])+'">'+kind+'</span>'+title+'</summary><p class="an-section-text" data-an-evidence role="button" tabindex="0" aria-label="この説明の根拠を確認">'+esc(edits[k]??a.finalText?.[k]??a.generated[k])+'</p><details class="an-edit"><summary>文章を修正する</summary><textarea data-edit="'+k+'" rows="5" maxlength="1200">'+esc(edits[k]??a.finalText?.[k]??a.generated[k])+'</textarea></details><button class="text-button" data-an-evidence>根拠を確認 ↗</button></details>').join('')+
  '<p class="micro">AI生成文は未作成です。定型処理の原文と利用者の修正文を別に保存します。</p></aside></div>'+
  '<div class="an-bottom"><div class="an-save"><button id="an-save" class="button primary">分析結果を保存</button><button id="an-approve" class="button secondary" '+(!run||dirty||pending?'disabled':'')+'>内容を確認・承認</button><span id="an-state-label">'+(run&&!dirty&&!pending?esc(run.runId):'未保存または条件変更あり')+'</span></div><div class="an-exports"><span>承認後に出力</span>'+[['docx','Word'],['pdf','PDF'],['html','HTML'],['xlsx','Excel'],['png','グラフ画像'],['json','条件・根拠']].map(([f,label])=>'<button class="button secondary" data-export="'+f+'" '+(!approved||dirty||pending?'disabled':'')+'>'+label+'</button>').join('')+'</div><p id="an-live" role="status" aria-live="polite">'+(approved&&!dirty?'このRunは承認済みです。保存時点の内容を出力します。':'架空データの確認版です。図表と文章を保存してから承認してください。')+'</p></div>'+
  '<section class="panel an-output"><h2>作成した資料</h2>'+outputs()+'</section>';
 }
 function outputs(){const files=info.exports.flatMap(e=>e.files.map(f=>({...f,exportId:e.id})));return files.length?table(['資料','状態','対象の分析','取得'],files.slice().reverse().map(f=>[esc(f.name)+' '+esc(f.type),esc(f.status),esc(f.runId),f.status==='作成済み'?'<a class="button secondary" href="/api/artifact/'+f.id+'" download>ダウンロード</a>':'出力だけ再試行できます'])):'<p>まだ出力していません。Word・PDF・HTMLなど、必要な形式を選んでください。</p>';}
 function dialog(title,body,wide=false){
  const d=$('#feedback');d.classList.toggle('an-wide',wide);d.innerHTML='<div class="section-heading"><h2>'+title+'</h2><button type="button" class="close" data-an-close aria-label="閉じる">×</button></div>'+body;
  d.querySelector('[data-an-close]').onclick=()=>{d.close();d.classList.remove('an-wide');};d.showModal();return d;
 }
 function evidence(featureOnly=false){
  const f=a.featureEvidence;
  const intro=featureOnly?'<p>'+esc(a.feature)+'</p>'+table(['対象項目','該当値','全体値','構成比'],[[esc(f.item),esc(f.value??'なし'),esc(f.total??'計算対象外'),f.share===null?'計算対象外':f.share.toFixed(1)+'%']]):'';
  dialog('根拠となるデータ',intro+'<p>'+esc(a.source.fileName)+' / '+esc(a.source.table)+'</p><details><summary>パス・ハッシュ・条件</summary><p class="hash">'+esc(a.source.path)+'</p><p class="hash">'+esc(a.source.sha256)+'</p><p>'+esc(a.conditions)+'</p></details><p class="micro">元CSVの行番号です。見出しは1行目。赤字の候補は自動で修正していません。</p>'+table(['行','ID','地区','日付','値','扱い・理由'],a.evidence.filter(e=>!featureOnly||f.lines.includes(e.line)).map(e=>[e.line,esc(e.values.ID),esc(e.values.地区),esc(e.values.日付||'日付なし'),esc(e.number??'数値なし'),e.included?'対象'+(e.warnings.length?'／'+esc(e.warnings.join('、')):''):'対象外／'+esc(e.reasons.join('、'))])),true);
 }
 function dirtyMark(){dirty=true;$('#an-state-label').textContent='修正あり・保存して再承認してください';$('#an-approve').disabled=true;document.querySelectorAll('[data-export]').forEach(b=>b.disabled=true);}
 async function doSave(){if(pending){toast('先に「条件を反映する」を押してください。',true);return;}if(loading)return;loading=true;try{const result=await api('analysis_save',{config:a.config,previewHash:a.previewHash||await previewHash(),edits:{...a.finalText,...edits}});run=result.run;dirty=false;await infoLoad();await refresh();redraw();toast(result.message);}catch(e){toast(e.message,true);}finally{loading=false;}}
 async function previewHash(){const p=await api('analysis_preview',{config:a.config});if(p.analysis.source.sha256!==a.source.sha256)throw Error('元サンプルが変更されています。再分析してください。');return p.analysis.previewHash;}
 function bind(){
  if(!a){$('#an-retry').onclick=()=>preview({dataset:'sales'});if(!loading&&!failed)preview({dataset:'sales'});return;}
  const form=$('#analysis-settings');
  form.onchange=e=>{pending=true;dirtyMark();setStatus('条件が変わっています。「条件を反映する」で図表を更新してください。');if(e.target.name==='dataset'){const cat=e.target.value==='categories';form.elements.measure.value=cat?'':'金額';form.elements.aggregate.value=cat?'count':'sum';form.elements.dateField.value=cat?'':'日付';}}
  form.oninput=()=>{pending=true;dirtyMark();};
  form.onsubmit=e=>{e.preventDefault();const conf=cfg();if(conf.dataset!==a.source.dataset){conf.measure=conf.dataset==='categories'?'':'金額';conf.aggregate=conf.dataset==='categories'?'count':'sum';conf.dateField=conf.dataset==='categories'?'':'日付';conf.from='';conf.to='';conf.chart='bar';}preview(conf,true);};
  document.querySelectorAll('[data-chart]').forEach(b=>b.onclick=()=>preview({...cfg(),chart:b.dataset.chart},true));
  $('#an-recommend').onclick=()=>preview({...cfg(),chart:a.recommendation.chart},true);
  $('#an-checks').onclick=()=>evidence();$('#an-chart-evidence').onclick=()=>evidence();$('#an-feature-evidence').onclick=()=>evidence(true);
  document.querySelectorAll('[data-an-evidence]').forEach(b=>{b.onclick=()=>evidence();b.onkeydown=e=>{if(e.key==='Enter')evidence();};});
  $('#an-zoom').onclick=()=>dialog('グラフの拡大','<img class="an-zoom-image" src="'+a.chartImage+'" alt="選択したグラフの拡大"><p>'+esc(a.feature)+'</p>',true);
  document.querySelectorAll('[data-edit]').forEach(t=>t.oninput=()=>{edits[t.dataset.edit]=t.value;t.closest('.an-section').querySelector('.an-section-text').textContent=t.value;dirtyMark();});
  $('#an-save').onclick=doSave;
  $('#an-approve').onclick=()=>{const d=dialog('分析資料の内容確認','<p>'+esc(run.runId)+' の図表と文章を承認します。Access改修や外部送信の許可ではありません。</p><p>対象 '+a.summary.count+'行／除外 '+a.summary.excluded+'行。修正文と原因の未確認表示も確認してください。</p><label class="check-line"><input type="checkbox" id="an-ack">図表・文章・除外理由を確認しました。</label><button class="button primary" id="an-approve-confirm">この分析資料を承認</button>');
   d.querySelector('#an-approve-confirm').onclick=async()=>{if(!d.querySelector('#an-ack').checked){toast('内容の確認にチェックしてください。',true);return;}try{const result=await api('analysis_approve',{runId:run.runId,hash:run.hash,ack:true});d.close();await infoLoad();await refresh();redraw();toast(result.message);}catch(e){toast(e.message,true);}};};
  document.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{if(loading)return;loading=true;setStatus('保存済みRunから '+b.textContent+' を作成しています…');document.querySelectorAll('[data-export]').forEach(x=>x.disabled=true);try{const result=await api('analysis_export',{runId:run.runId,format:b.dataset.export});await infoLoad();await refresh();redraw();toast(result.export.status==='成功'?'資料を作成しました。下の「ダウンロード」から開けます。':'出力に失敗した形式があります。記録を確認してください。',result.export.status!=='成功');}catch(e){toast(e.message,true);}finally{loading=false;redraw();}});
  $('#an-rerun').onclick=()=>preview({...a.config},true);
  $('#an-history-select').onchange=async e=>{if(!e.target.value)return;if(dirty&&Object.keys(edits).length&&!confirm('未保存の文章を置き換えて、保存済みの分析を開きますか？'))return;try{const result=await api('analysis_load',{runId:e.target.value});run=result.run;a=result.analysis;edits={};dirty=false;pending=false;await infoLoad();redraw();}catch(ex){toast(ex.message,true);}};
 }
 return {page,bind};
})();
