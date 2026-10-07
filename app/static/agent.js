'use strict';
let data, csrf, selected='', busy=false, editQuestion=null;
const $=s=>document.querySelector(s);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const routes=[['request','依頼受付'],['questions','質問と回答'],['design','要件・詳細設計'],['evidence','進捗・根拠・成果物'],['components','呼び出す部品'],['connection','AI接続']];
const pill=(s,t='')=>`<span class="pill ${t}">${esc(s)}</span>`;
const note=(s,t='')=>`<div class="notice ${t}">${s}</div>`;
const caseNow=()=>data.cases.find(c=>c.id===selected);
const table=(heads,rows)=>`<div class="table-wrap"><table><thead><tr>${heads.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
function tell(message){$('#notice').textContent=message;setTimeout(()=>{$('#notice').textContent='';},8500);}
async function refresh(){const r=await fetch('/api/agent');if(!r.ok)throw Error('保存データを取得できません。');data=await r.json();csrf=data.csrf;if(!selected&&data.cases.length)selected=data.cases[0].id;render();}
async function action(action,fields={}){
 if(busy)return; busy=true; const c=caseNow(); const key=crypto.randomUUID();
 document.querySelectorAll('button').forEach(b=>b.disabled=true); $('#notice').textContent='処理中です。画面を閉じずにお待ちください。';
 try {const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Genesis-Token':csrf,'Idempotency-Key':key},body:JSON.stringify({action:'agent_'+action,caseId:c?.id,revision:c?.revision,...fields})});const result=await r.json();if(result.caseId)selected=result.caseId;busy=false;await refresh();tell(result.message||'結果を確認してください。');return result;}
 catch(e){busy=false; await refresh().catch(()=>{});tell('応答を確認できません。自動再送はしません。進捗・根拠で状態を確認してください。');}
}
function title(c){return c?`${c.mode==='rehearsal'?'手順確認用':'実AI案件'} · ${c.request}`:'新しい依頼';}
function render(){
 const c=caseNow(), route=location.hash.slice(1)||'request';const conn=data.connection;
 const status=conn.verifiedThisSession?'実AI応答を確認済み':conn.keyRegistered?'キー登録済み・接続未確認':'未接続・キー未登録';
 $('#agent').innerHTML=`<header><div><strong>Genesis <span>AIエージェント · 業務設計室</span></strong></div><div class="small"><a href="#connection">接続と送信回数を確認</a></div></header><div class="layout"><aside><nav aria-label="工程"><a href="/sales">販売管理 業務パック</a>${routes.map(([r,n],i)=>`<a href="#${r}" class="${route===r?'active':''}">${String(i+1).padStart(2,'0')}　${n}</a>`).join('')}</nav><div class="brand-note small">まず、依頼を整理します。<br>一つずつ質問に答え、設計を確認してから承認します。<br><br>確認版 v0.6.0<br>実ファイルの改修は未接続です。</div></aside><main id="main"><div class="topline"><div><div class="progress-label">依頼から、判断できる設計へ</div><h1>${esc(routes.find(([r])=>r===route)?.[1]||'依頼受付')}</h1></div><div><label for="caseSelect" class="small">表示する案件</label><select id="caseSelect"><option value="">新しい依頼</option>${data.cases.map(x=>`<option value="${x.id}" ${selected===x.id?'selected':''}>${esc(title(x))}</option>`).join('')}</select></div></div>
 <div class="status-grid"><div class="status"><span>実AIの状態</span><b>${esc(status)}</b></div><div class="status"><span>過去のAPI送信履歴（今回追加0回）</span><b>${data.usage.attempts} 回</b><span>成功 ${data.usage.success} · 応答確認 ${data.usage.responses} · 結果未確認 ${data.usage.uncertain}</span></div><div class="status"><span>保存先</span><b>この端末に保存</b><span>案件・回答・設計・判断履歴</span></div><div class="status"><span>現在の状態</span><b>${esc(c?.stage||'依頼を入力')}</b><span>${c?esc(c.id):'原本の操作なし'}</span></div></div>
 ${c&&c.mode==='rehearsal'?note('<strong>手順確認用の案件です。</strong> 固定の模擬応答で保存と承認停止を確認します。実AIの結果ではありません。','warn'):''}
 ${c?.pending?note('処理中の記録があります。自動再送は行いません。画面更新で完了を確認してください。','warn'):''}
 ${c?.lastError?note(`停止した処理：${esc(c.lastError)}。入力と保存済みの結果を保持しています。`,'error'):''}
 ${c?`<ol class="steps">${c.steps.slice(0,7).map((s,i)=>`<li class="${s.status==='完了'?'done':s.status.includes('待ち')||s.status==='進行中'?'current':''}">${i+1}. ${esc(s.name)} · ${esc(s.status)}</li>`).join('')}</ol>`:''}
 ${{request:requestView,questions:questionsView,design:designView,evidence:evidenceView,components:componentsView,connection:connectionView}[route]?.(c)||requestView(c)}
 <footer>Genesis v0.6.0 ｜ Excel静的解析部品を追加。実AI・解析・試験の確認状態を分けて記録します。</footer></main></div>`;
 bind();
}
function requestView(c){
 if(c)return `<section class="panel focus"><h2>${esc(c.request)}</h2><p>${esc(c.classification?.purpose||'次は、依頼の分野と目的を整理し、不足する条件を質問します。')}</p><div class="row">${pill(c.mode==='real'?'実AIを使用する案件':'手順確認用・模擬応答',c.mode==='real'?'':'warn')}${c.classification?pill(c.classification.domain):''}</div>
 ${c.classification?'<div class="buttons"><a class="link-button" href="#questions">質問と回答へ進む</a><a class="link-button" href="#design">要件・詳細設計を見る</a></div>':callControls(c,'classify')}
 </section><button id="newCase">別の依頼を入力</button>`;
 return `<section class="panel focus"><h2>何を実現したいですか？</h2><p>まだ決まっていないことがあっても、そのまま入力してください。</p><form id="requestForm"><label for="requestText">依頼内容</label><textarea id="requestText" maxlength="3000" required>Accessのフォームに印刷機能を追加したい</textarea><label for="mode">進め方</label><select id="mode"><option value="real">実AIで整理する（APIキーが必要）</option><option value="rehearsal">印刷デモの手順を確認する（API送信なし）</option></select><label><input id="fictional" type="checkbox" required>架空の依頼です。実データ・個人情報・生VBAを含みません。</label><p class="small">ここでは依頼だけを端末に保存します。AIへの送信は次の画面で確認します。</p><button class="primary" type="submit">依頼を保存して始める</button></form></section>`;
}
function callControls(c,phase){
 if(c.mode==='rehearsal')return `<div class="buttons"><button class="primary" data-call="${phase}">${phase==='classify'?'模擬応答で質問へ進む':'模擬応答で要件・詳細設計を作成'}</button></div>`;
 const text={request:c.request};if(phase==='design'){text.domain=c.classification.domain;text.purpose=c.classification.purpose;text.answers=c.questions.map((q,i)=>({number:i+1,question:q.text,answer:c.answers[q.id]}));}
 return `<div class="notice"><strong>次の操作ではOpenAIへ1回送信します。</strong><p class="small">${esc(data.connection.model)} · 自動再送なし · この案件は最大2回。API利用料が発生します。現在の残高・請求額は未確認です。</p><details><summary>送信する依頼・回答を確認</summary><pre>${esc(JSON.stringify(text,null,2))}</pre><p class="small">この内容と、分類・設計用の共通指示・回答形式だけを送信します。ローカルのファイルや履歴全体は送りません。</p></details>${data.connection.keyRegistered?`<label><input id="sendConsent" type="checkbox">上記が架空の内容であることを確認し、この1回の送信を認めます。</label><button class="primary" data-call="${phase}">この内容をAIへ送信（1回）</button>`:'<a class="link-button" href="#connection">先にAI接続を設定する</a>'}</div>`;
}
function questionsView(c){
 if(!c?.classification)return `<section class="panel"><h2>質問はまだ作成されていません</h2><p>依頼受付で、分野と目的の整理へ進んでください。</p><a href="#request">依頼受付へ戻る</a></section>`;
 const q=c.questions.find(x=>x.id===editQuestion)||c.questions.find(x=>!c.answers[x.id]);
 return `<section class="panel focus"><p class="progress-label">${esc(c.classification.domain)} ｜ ${Object.keys(c.answers).length} / ${c.questions.length} 問を保存済み</p><h2>${q?esc(q.text):'回答がそろいました'}</h2>${q?`<p>${esc(q.reason)}</p><form id="answerForm" data-qid="${q.id}"><div class="examples row">${q.options.map(s=>`<button type="button" data-example="${esc(s)}">${esc(s)}</button>`).join('')}</div><label for="answer">回答（自由に変更できます）</label><textarea id="answer" maxlength="1500" required>${esc(c.answers[q.id]||'')}</textarea><p class="small">分からない部分は「未確認」と回答できます。推測で決める必要はありません。</p><button class="primary" type="submit">回答を保存して次へ</button></form>`:`<p>保存した回答を根拠に、要件と詳細設計をまとめます。</p>${c.design?'<a class="link-button" href="#design">詳細設計を見る</a>':callControls(c,'design')}`}</section>
 <details class="panel"><summary>これまでの回答を確認・修正</summary>${c.questions.map(x=>`<div class="item"><strong>${esc(x.text)}</strong><p class="answer-text">${esc(c.answers[x.id]||'未回答')}</p><button data-edit="${x.id}">この回答を修正</button><p class="meta">${x.id}</p></div>`).join('')}</details>`;
}
function designView(c){
 if(!c?.design)return `<section class="panel"><h2>詳細設計はまだありません</h2><p>不足事項への回答がそろってから作成します。</p><a href="#questions">質問と回答へ</a></section>`;
 const d=c.design, b=d.content;
 return `${note(`<strong>${c.approval?'設計承認を記録済み。実行は保留しています。':'詳細設計を保存し、承認待ちで停止しています。'}</strong><br>対象ファイルの確認・解析・改修は実行していません。`,'warn')}
 <section class="panel focus"><h2>設計案の概要</h2><p>${esc(b.summary)}</p><div class="row">${pill(d.origin,c.mode==='real'?'':'warn')}${pill('版 '+d.version)}${pill('試験：未実施')}</div><p class="meta">AgentRunID：${d.runId}<br>設計SHA-256：${d.hash}</p></section>
 <section class="panel"><h2>要件一覧</h2>${c.requirements.map((r,i)=>`<div class="item"><strong>${i+1}. ${esc(r.title)}</strong><p>${esc(r.description)}</p><details><summary>回答の根拠</summary>${r.questionIds.map(id=>`<p>${esc(c.questions.find(q=>q.id===id)?.text)}<br>→ ${esc(c.answers[id])}</p>`).join('')}<p class="meta">${r.id}</p></details></div>`).join('')}</section>
 <section class="panel"><h2>詳細設計</h2>${b.sections.map((s,i)=>`<div class="item"><h3>${i+1}. ${esc(s.title)}</h3><p>${esc(s.body)}</p><details><summary>対応する要件</summary>${s.requirementIds.map(id=>`<p>${esc(c.requirements.find(r=>r.id===id)?.title)} <span class="meta">${id}</span></p>`).join('')}</details></div>`).join('')}</section>
 <div class="two"><section class="panel"><h2>変更する候補</h2>${b.changes.map(x=>`<div class="item"><strong>${esc(x.component)}</strong><p>${esc(x.proposal)}</p><p class="small">理由：${esc(x.reason)}</p></div>`).join('')}</section><section class="panel"><h2>未確認・保留事項</h2>${b.unknowns.map(x=>note(esc(x),'warn')).join('')}${b.risks.map(x=>`<p>${esc(x)}</p>`).join('')}</section></div>
 <details class="panel"><summary>試験項目案・操作説明書案</summary><h3>試験項目（まだ実行していません）</h3>${table(['試験項目','期待する結果','状態'],b.tests.map(t=>[esc(t.title)+`<p class="meta">${t.id}</p>`,esc(t.expected),esc(t.status)]))}<h3>操作説明書案</h3><ol>${b.manual.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></details>
 <section class="panel"><h2>この設計を確認する</h2><p>対象の解析部品は未接続です。設計を承認しても、Accessの生成・改修・データ登録は開始されません。</p>${c.approval?note(`ApprovalID：${c.approval.id}<br>承認対象ハッシュ：${c.approval.designHash}`,'ok'):`<form id="approvalForm"><label for="approvalText">承認する場合だけ「この設計を承認します」と入力してください</label><input id="approvalText" autocomplete="off" required><button type="submit">設計の承認を記録する</button></form>`}<div class="buttons"><a class="link-button" href="#questions">回答を修正する</a><a class="link-button" href="/api/agent/artifact/${c.artifacts[0].id}" download>保存した設計と根拠を取得（JSON）</a></div></section>`;
}
function evidenceView(c){
 if(!c)return '<section class="panel"><p>案件を選んでください。</p></section>';
 const events=data.events.filter(e=>e.caseId===c.id),ops=data.operations.filter(o=>o.caseId===c.id);
 return `<section class="panel"><h2>工程と実行状態</h2>${table(['工程','状態'],c.steps.map(s=>[esc(s.name),esc(s.status)]))}</section><section class="panel"><h2>保存された成果物</h2>${c.artifacts.length?c.artifacts.map(a=>`<p><a href="/api/agent/artifact/${a.id}" download>${esc(a.name)}（${a.type}）</a></p><p class="meta">ArtifactID：${a.id} / 版 ${a.version}</p>`).join(''):'<p>詳細設計の作成後に表示されます。</p>'}<details><summary>保存先・記録版</summary><p class="path small">${esc(data.storage)}</p>${table(['版','保存日時','SHA-256'],data.versions.filter(v=>v.case_id===c.id).map(v=>[v.revision,esc(v.created),`<span class="meta">${v.hash}</span>`]))}</details></section>
 <section class="panel"><h2>実行記録</h2>${table(['工程','使用方式','結果','API応答'],ops.map(o=>[esc(o.phase),esc(o.model||'ローカル保存'),esc(o.status)+(o.diagnostic?`<p>${esc(o.diagnostic)}</p>`:''),o.mode==='real'?(o.responseReceived?'受信確認':'未確認'):'送信なし']))}</section><details class="panel"><summary>監査ログ・判断履歴</summary>${events.map(e=>`<div class="item"><strong>${esc(e.event)}</strong><span class="small">${esc(e.created)} / 記録版 ${e.revision}</span><p class="meta">${e.id}<br>記録SHA-256：${e.hash}</p></div>`).join('')}</details>`;
}
function componentsView(){return `<section class="panel focus"><h2>Genesisが工程を管理し、部品を呼び出す構成</h2><p>依頼受付 → 質問 → 回答保存 → 要件 → 詳細設計 → <strong>人の承認</strong> → 対象の解析部品 → 改修案・試験・説明書</p>${note('Excel静的解析をローカル部品として接続しました。案件の承認後に自動で振り分ける部分は未接続です。','warn')}</section>${data.components.map(c=>`<section class="panel"><h2>${esc(c.name)} ${pill(c.status,c.status==='未接続'?'warn':'')}</h2><p>${esc(c.detail)}</p>${c.id==='excel-static'?'<a class="link-button" href="/excel">Excelを静的解析する</a>':''}${c.id==='analysis'?'<a class="link-button" href="/workspace.html#analysis">分析・読み解き資料作成を開く</a>':''}</section>`).join('')}`;}
function connectionView(){if(data.localOnly)return `<section class="panel"><h2>ローカル実行専用</h2><p>この版ではAPIキーの入力と追加API送信を停止しています。既存の接続設定は変更していません。</p><p>この追加作業のAPI送信：0回。コピーに含まれる過去の送信履歴：${data.usage.attempts}回。過去の受信後検証エラーは未解決として保持します。</p></section>`;const c=data.connection;return `<section class="panel focus"><h2>実AIの接続設定</h2><p>モデル：<strong>${esc(c.model)}</strong></p><p>APIキーはこの画面で一時登録します。通常の会話には貼り付けないでください。</p>${note('登録するだけではAPIを呼びません。依頼または回答の送信ボタンを押すと、1回分のAPI利用料が発生します。','warn')}<form id="secretForm"><label for="secret">APIキー（表示しません）</label><input id="secret" type="password" autocomplete="off" spellcheck="false" maxlength="255" required placeholder="この端末の起動中だけ使用"><div class="buttons"><button class="primary" type="submit">この起動中だけ登録</button><button type="button" id="clearSecret">登録を解除</button></div></form>
 <details><summary>保存場所・暗号化・削除方法</summary><p>キーはサーバープロセスのメモリだけで保持し、DB・設定・HTML・ログ・ブラウザー保存領域には書き込みません。キーをサーバーへ渡す通信はこの端末内の127.0.0.1に限定します。</p><p>メモリ上のキーは暗号化保管ではありません。Windowsのプロセス保護に依存します。OpenAIへの送信はHTTPSです。登録解除またはサーバー終了で参照を解放します。OSメモリの完全消去は保証しません。Platform上のキーの失効は別途必要です。</p><p>環境変数から登録した場合も使用できます。登録解除はこの起動中の保持だけを解除し、元の環境変数は変更しません。</p></details>
 <details><summary>送信する情報と外部サービス</summary><p>送信するのは、利用者が確認した架空の依頼・質問回答と、分類・設計用の共通指示・回答形式です。対象ファイル・生VBA・個人情報の送信機能はありません。store:falseを指定しますが、外部サービスの保存・利用条件をこの設定だけで保証するものではありません。</p><p><a href="https://developers.openai.com/api/docs/guides/structured-outputs" target="_blank" rel="noopener noreferrer">OpenAI公式：構造化出力</a> / <a href="https://developers.openai.com/api/docs/models/gpt-6-luna" target="_blank" rel="noopener noreferrer">モデル仕様</a></p></details></section>
 <section class="panel"><h2>API送信と未確認事項</h2>${table(['項目','状態'],[['キー登録',c.keyRegistered?'登録済み（値は非表示）':'未登録'],['この起動中の実AI応答',c.verifiedThisSession?'確認済み':'未確認'],['この本体の送信試行',data.usage.attempts+'回'],['応答を受信した回数',data.usage.responses+'回'],['成功',data.usage.success+'回'],['結果未確認',data.usage.uncertain+'回'],['受信した使用トークン',data.usage.tokens],['Platform使用量・残高・請求額','未確認（自動取得しません）'],['過去の接続テスト','今回の回数には含めません'],['送信上限','案件あたり2回・自動再送なし']])}</section>`;}
function bind(){
 $('#caseSelect').onchange=e=>{selected=e.target.value;editQuestion=null;render();};
 $('#newCase')?.addEventListener('click',()=>{selected='';render();});
 $('#requestForm')?.addEventListener('submit',async e=>{e.preventDefault();await action('create',{request:$('#requestText').value,mode:$('#mode').value,fictional:$('#fictional').checked});});
 document.querySelectorAll('[data-call]').forEach(b=>b.onclick=async()=>{if(caseNow().mode==='real'&&!$('#sendConsent')?.checked){tell('送信する内容を確認してください。');return;}const r=await action(b.dataset.call,{transmitApproved:!!$('#sendConsent')?.checked});if(r?.ok)location.hash=b.dataset.call==='classify'?'questions':'design';});
 document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{$('#answer').value=b.dataset.example;$('#answer').focus();});
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{editQuestion=b.dataset.edit;render();$('#answer')?.focus();});
 $('#answerForm')?.addEventListener('submit',async e=>{e.preventDefault();const qid=e.target.dataset.qid,answer=$('#answer').value;editQuestion=null;await action('answer',{questionId:qid,answer});});
 $('#approvalForm')?.addEventListener('submit',async e=>{e.preventDefault();await action('approve',{confirmation:$('#approvalText').value,designHash:caseNow().design.hash});});
 $('#secretForm')?.addEventListener('submit',async e=>{e.preventDefault();const input=$('#secret');let key=input.value;input.value='';try{const r=await fetch('/api/agent/secret',{method:'POST',headers:{'Content-Type':'application/json','X-Genesis-Token':csrf},body:JSON.stringify({action:'set',key})});const result=await r.json();key='';await refresh();tell(result.message);}catch{key='';tell('登録の結果を確認できません。値は表示しません。');}});
 $('#clearSecret')?.addEventListener('click',async()=>{const r=await fetch('/api/agent/secret',{method:'POST',headers:{'Content-Type':'application/json','X-Genesis-Token':csrf},body:JSON.stringify({action:'clear'})});const result=await r.json();await refresh();tell(result.message);});
}
window.addEventListener('hashchange',()=>{editQuestion=null;if(data)render();});
refresh().catch(()=>{$('#agent').innerHTML='<main><h1>Genesisに接続できません</h1><p>「画面を開く.cmd」で起動し、再読み込みしてください。</p></main>';});
