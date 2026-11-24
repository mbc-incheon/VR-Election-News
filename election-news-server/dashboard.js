const $=x=>document.getElementById(x);
let snap={},current=null,selectionKey='',searchRequest=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const showValue=(v,suffix='')=>v===null||v===undefined?'미제공':esc(v)+suffix;
const statuses={DRAFT:'초안',PENDING_HUMAN:'승인 대기',REVIEW_REQUIRED:'검토 필요',APPROVED:'승인 완료'};
function timeText(value,clockOnly=false){if(!value)return '미제공';const d=new Date(value);if(Number.isNaN(d.getTime()))return String(value);return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',...(clockOnly?{}:{year:'numeric',month:'2-digit',day:'2-digit'}),hour:'2-digit',minute:'2-digit',hour12:false}).format(d)}
function safeSource(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):null}catch{return null}}
async function api(url,body){const r=await fetch(url,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+$('token').value},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail||v));return v}
function table(){
 const selected=$('candidate').value,region=$('region').value,rows=(snap.rows||[]).filter(r=>r.region_name===region);
 $('rows').innerHTML=rows.length?rows.map((r,i)=>{const share=Number(r.vote_share),url=safeSource(r.source_url);return `<tr><td class="candidate-name"><span class="candidate-mark ${i%2?'alternate':''}"></span>${esc(r.candidate_name)}</td><td>${showValue(r.votes==null?null:Number(r.votes).toLocaleString('ko-KR'),'표')}</td><td><div class="vote-share"><span class="share-value">${showValue(r.vote_share==null?null:share.toFixed(2),'%')}</span><div class="bar" aria-hidden="true"><span style="width:${Number.isFinite(share)?Math.max(0,Math.min(100,share)):0}%"></span></div></div></td><td>${showValue(r.count_rate,'%')}</td><td class="table-time" title="${esc(r.baseline_at||'미제공')}">${esc(timeText(r.baseline_at,true))}</td><td class="table-source">${r.is_demo?'시뮬레이션':url?`<a href="${url}" target="_blank" rel="noopener noreferrer">공식 원문</a>`:'출처 미제공'}</td></tr>`}).join(''):'<tr><td colspan="6" class="empty">선택한 지역의 자료가 없습니다.</td></tr>';
 $('candidate').innerHTML=rows.map(r=>`<option value="${esc(r.candidate_id)}">${esc(r.candidate_name)}</option>`).join('');if(rows.some(r=>r.candidate_id===selected))$('candidate').value=selected;
 const key=region+'|'+$('candidate').value+'|'+snap.mode;if(key!==selectionKey){selectionKey=key;void loadEvidence().catch(e=>{$('evidence').textContent=e.message})}
}
function update(v){
 snap=v;const state=v.connection?.state,demo=v.mode==='demo';$('mode').textContent=demo?'▤ 시뮬레이션 데이터':v.mode==='unavailable'?'자료 없음':'2024년 공식 자료';$('modeNote').textContent=demo?'가상 후보·가상 수치 · 과거 선거 재현':'과거 선거 자료 · 현재 속보 아님';
 $('connection').className='pill '+(state==='CONNECTED'?'good':state==='DISCONNECTED'?'bad':'');$('connection').innerHTML='<span class="dot"></span>'+({CONNECTED:'연결됨',DISCONNECTED:'연결 끊김',CONNECTING:'연결 중'}[state]||'연결 대기');$('error').textContent=v.connection?.error||'';
 $('baseline').textContent=timeText(v.rows?.[0]?.baseline_at);$('collected').textContent=timeText(v.collected_at);$('updated').textContent=new Date().toLocaleTimeString('ko-KR',{hour12:false,timeZone:'Asia/Seoul'});
 const regions=[...new Set((v.rows||[]).map(r=>r.region_name))],selected=$('region').value;if(regions.join()!==[...$('region').options].map(o=>o.value).join()){$('region').innerHTML=regions.map(r=>`<option value="${esc(r)}">${esc(r)}</option>`).join('');if(regions.includes(selected))$('region').value=selected}table();
}
function connect(){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onmessage=e=>{try{update(JSON.parse(e.data))}catch{$('error').textContent='수신 자료를 표시하지 못했습니다. 연결 상태를 확인해 주세요.'}};ws.onclose=()=>{$('connection').className='pill bad';$('connection').innerHTML='<span class="dot"></span>재연결 중';setTimeout(connect,2000)}}
function show(a){
 if(current?.id!==a.id){$('checked').checked=false;$('aiAck').checked=false;$('reason').value=''}current=a;
 $('selectedTitle').textContent=a.title;$('selectedAuthor').textContent='작성자 '+a.author;$('selectedStatus').textContent=statuses[a.status]||a.status;$('selectedStatus').className='pill '+(a.status==='APPROVED'?'good':a.status==='REVIEW_REQUIRED'?'warn':'draft-pill');
 $('articleStatus').textContent=`${a.title} · ${a.status} · ${a.mode==='demo'?'시뮬레이션':'과거 자료'} · 작성자 ${a.author}`;
 $('article').innerHTML=a.sentences.map(s=>`<p>${esc(s.text)}<span class="evidence-tag">근거 ID: ${esc((s.row_ids||s.evidence_ids||[]).join(', '))}</span></p>`).join('');
 const v=a.validation;$('checks').textContent=JSON.stringify(v||{status:'검증 전',ai:a.ai_review},null,2);$('ruleBadge').textContent=v?(v.rule==='PASS'?'규칙 검증 통과':'검토 필요'):'검증 전';$('ruleBadge').className='pill '+(v?(v.rule==='PASS'?'good':'bad'):'');
 $('aiBadge').textContent=v?.disagreement?'규칙·AI 판정 불일치':a.ai_review?.verdict==='UNAVAILABLE'?'AI 보조 검토 미연결':'AI 판정: '+(a.ai_review?.verdict||'미확인');$('aiBadge').className='pill '+(v?.disagreement?'bad':'warn');$('checkErrors').textContent=(v?.errors||[]).join(' / ');$('checkErrors').hidden=!v?.errors?.length;
 $('validate').disabled=false;syncApproval();$('export').disabled=a.status!=='APPROVED';
}
function syncApproval(){const v=current?.validation;$('approve').disabled=!(current?.status==='PENDING_HUMAN'&&v?.rule==='PASS'&&!v?.disagreement&&$('checked').checked&&$('aiAck').checked&&$('reason').value.trim().length>=5)}
['checked','aiAck','reason'].forEach(id=>$(id).addEventListener('input',syncApproval));$('token').addEventListener('input',()=>{$('checked').checked=false;$('aiAck').checked=false;syncApproval()});
const action=f=>async()=>{try{await f();$('message').className='message';$('message').textContent='처리했습니다.'}catch(e){$('message').className='message is-error';$('message').textContent=e.message}};
async function loadEvidence(){
 const request=++searchRequest,q=$('query').value.trim(),region=$('region').value,candidate=$('candidate').value;if(!region||!candidate)return;if(!q){$('evidence').textContent='검색어를 입력해 주세요.';return}
 const hits=await api('/api/search?'+new URLSearchParams({q,region,candidate}));if(request!==searchRequest)return;
 $('evidence').innerHTML=hits.length?hits.map(c=>{const url=safeSource(c.url);return `<div class="evidence-card">${!c.is_demo&&url?`<a class="evidence-link" href="${url}" target="_blank" rel="noopener noreferrer">원문 확인 ↗</a>`:''}<h3>▤ ${esc(c.title)}</h3><p>${esc(c.text)}</p><div class="evidence-meta">근거 ID <b>${esc(c.id)}</b>　|　발행기관 ${esc(c.publisher)}　|　게시일 ${esc(c.published_at)}　|　원문 위치 ${esc(c.location)}</div>${c.is_demo?'<div class="evidence-disclosure">시뮬레이션 문서 · 실제 후보 공약이 아닙니다</div>':''}</div>`}).join(''):'<p class="empty">해당 후보·지역의 근거를 찾지 못했습니다.</p>';
}
$('region').onchange=table;$('candidate').onchange=action(loadEvidence);$('search').onclick=action(loadEvidence);$('query').addEventListener('keydown',e=>{if(e.key==='Enter')$('search').click()});
$('official').onclick=action(async()=>{if(!$('officialRows').hidden){$('officialRows').hidden=true;$('official').setAttribute('aria-expanded','false');return}const v=await api('/api/official-results');$('officialRows').innerHTML='<p>'+esc(v.label)+'</p><div class="scroll"><table><thead><tr><th>지역구</th><th>후보</th><th>정당</th><th>집계 득표수</th><th>계산 득표율</th></tr></thead><tbody>'+v.rows.map(r=>`<tr><td>${esc(r.region_name)}</td><td>${esc(r.candidate_name)}</td><td>${esc(r.party)}</td><td>${Number(r.votes).toLocaleString('ko-KR')}</td><td>${Number(r.vote_share).toFixed(2)}%</td></tr>`).join('')+'</tbody></table></div>';$('officialRows').hidden=false;$('official').setAttribute('aria-expanded','true')});
$('productionToggle').onclick=()=>{const open=$('productionInfo').hidden;$('productionInfo').hidden=!open;$('productionToggle').setAttribute('aria-expanded',String(open))};
$('draft').onclick=action(async()=>{if(!$('region').value)throw Error('지역을 먼저 선택해 주세요.');show(await api('/api/articles',{region:$('region').value}))});
$('list').onclick=action(async()=>{const articles=await api('/api/articles');$('articles').innerHTML='';if(!articles.length){$('articles').textContent='작성된 기사가 없습니다.';return}articles.forEach(a=>{const button=document.createElement('button');button.className='secondary';button.textContent=a.title+' · '+(statuses[a.status]||a.status);button.onclick=action(async()=>show(await api('/api/articles/'+a.id)));$('articles').appendChild(button)})});
$('validate').onclick=action(async()=>show(await api(`/api/articles/${current.id}/validate`,{})));
$('approve').onclick=action(async()=>show(await api(`/api/articles/${current.id}/approve`,{reason:$('reason').value,evidence_checked:$('checked').checked,ai_unavailable_ack:$('aiAck').checked})));
$('export').onclick=action(async()=>{const v=await api(`/api/articles/${current.id}/export`),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(v,null,2)],{type:'application/json'}));a.download=current.id+'.json';a.click();URL.revokeObjectURL(a.href)});
connect();
