'use strict';
let token='',busy=false;
const status=document.querySelector('#status');
async function refresh(){const r=await fetch('/api/v07/ai');const d=await r.json();token=d.csrf;document.querySelector('#record').textContent=JSON.stringify(d.record||{status:'未実施',model:d.model,apiRequests:d.additionalApiRequests},null,2);document.querySelector('#once').disabled=!!d.record||!d.keyRegistered||busy;document.querySelector('#register').disabled=!!d.record||busy;status.textContent=d.keyRegistered?'キー登録済み。送信はまだ行っていません。':(d.record?'試験の記録を保存しました。再送は行いません。':'キーは未登録です。');const p=await fetch('/api/v07/preview');document.querySelector('#preview').textContent=JSON.stringify(await p.json(),null,2);}
async function send(path,payload){if(busy)return;busy=true;try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Genesis-Token':token},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.error);await refresh();}catch(e){status.textContent='処理を確認できません：'+e.message+'。自動再送しません。';}finally{busy=false;document.querySelector('#secret').value='';await refresh();}}
document.querySelector('#register').onclick=()=>{const v=document.querySelector('#secret').value;document.querySelector('#secret').value='';return send('/api/v07/key',{key:v});};
document.querySelector('#once').onclick=()=>send('/api/v07/ai-once',{});
refresh();
