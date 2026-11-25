const $=x=>document.getElementById(x);
let snap={},current=null,selectionKey='',searchRequest=0,liveSocket,reconnectTimer;
const selectedMode=()=> $('dataMode')?.value||'demo';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const showValue=(v,suffix='')=>v===null||v===undefined?'미제공':esc(v)+suffix;
const statuses={DRAFT:'초안',PENDING_HUMAN:'승인 대기',REVIEW_REQUIRED:'검토 필요',APPROVED:'승인 완료'};
function timeText(value,clockOnly=false){if(!value)return '미제공';const d=new Date(value);if(Number.isNaN(d.getTime()))return String(value);return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',...(clockOnly?{}:{year:'numeric',month:'2-digit',day:'2-digit'}),hour:'2-digit',minute:'2-digit',hour12:false}).format(d)}
function safeSource(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):null}catch{return null}}
async function api(url,body){const r=await fetch(url,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok){const error=Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail||v));error.status=r.status;throw error}return v}
function resetReviewConfirmation(){$('checked').checked=false;$('aiAck').checked=false;$('reason').value='';syncApproval()}
async function ensureArticleSession(){
 let user;
 try{user=await api('/api/me')}catch(error){if(error.status!==401)throw error}
 if(!user){
  const capabilities=await api('/api/capabilities');
  if(!capabilities.local_writer_available)throw Error('상단의 담당자 로그인에서 작업 계정으로 로그인해 주세요.');
  await api('/api/session/local-writer',{});user=await api('/api/me');
 }
 if(typeof wbIdentity==='function')await wbIdentity();
 return user;
}
let articleBusy=false;
function publishNewsroom(patch){
 if(typeof window==='undefined')return;
 window.newsroomView={...(window.newsroomView||{}),...patch};
 window.dispatchEvent(new CustomEvent('newsroom:view',{detail:window.newsroomView}));
}
function renderArticleButtons(articles){
 publishNewsroom({articles});
 if(typeof window!=='undefined'&&window.newsroomReactLists)return;
 $('articles').innerHTML='';
 articles.forEach(a=>{const item=document.createElement('button');item.className='secondary';item.textContent=a.title+' · '+(statuses[a.status]||a.status);item.onclick=action(async()=>show(await api('/api/articles/'+a.id)));$('articles').appendChild(item)});
}

function displayArchive(snapshot){return snapshot.mode==='official'&&snapshot.stage==='FINAL_FILE_AGGREGATION'}
function table(){
 const selected=$('candidate').value,region=$('region').value,rows=(snap.rows||[]).filter(r=>r.region_name===region);
 $('rows').innerHTML=rows.length?rows.map((r,i)=>{const share=Number(r.vote_share),url=safeSource(r.source_url);return `<tr><td class="candidate-name"><span class="candidate-mark ${i%2?'alternate':''}"></span>${esc(r.candidate_name)}</td><td>${showValue(r.votes==null?null:Number(r.votes).toLocaleString('ko-KR'),'표')}</td><td><div class="vote-share"><span class="share-value">${showValue(r.vote_share==null?null:share.toFixed(2),'%')}</span><div class="bar" aria-hidden="true"><span style="width:${Number.isFinite(share)?Math.max(0,Math.min(100,share)):0}%"></span></div></div></td><td>${displayArchive(snap)?'100% (표시값)':showValue(r.count_rate,'%')}</td><td class="table-time" title="${esc(displayArchive(snap)?'임의 기준시각: 2024.04.11 06:00 (한국시간)':r.baseline_at||'미제공')}">${displayArchive(snap)?'06:00 (임의)':esc(timeText(r.baseline_at,true))}</td><td class="table-source">${r.is_demo?'시뮬레이션':url?`<a href="${url}" target="_blank" rel="noopener noreferrer">공식 원문</a>`:'출처 미제공'}</td></tr>`}).join(''):'<tr><td colspan="6" class="empty">선택한 지역의 자료가 없습니다.</td></tr>';
 $('candidate').innerHTML=rows.map(r=>`<option value="${esc(r.candidate_id)}">${esc(r.candidate_name)}</option>`).join('');if(rows.some(r=>r.candidate_id===selected))$('candidate').value=selected;
 publishNewsroom({snapshot:snap,region,candidate:$('candidate').value});
 const key=region+'|'+$('candidate').value+'|'+snap.mode;if(key!==selectionKey){selectionKey=key;void loadEvidence().catch(e=>{$('evidence').textContent=e.message})}
}
function update(v){
 snap=v;publishNewsroom({connection:v.connection});const state=v.connection?.state,demo=v.mode==='demo';$('mode').textContent=demo?'▤ 시뮬레이션 데이터':v.mode==='unavailable'?'자료 없음':'2024년 공식 자료';$('modeNote').textContent=demo?'가상 후보·가상 수치 · 과거 선거 재현':'과거 선거 자료 · 현재 속보 아님';
 $('connection').className='pill '+(state==='CONNECTED'||state==='ARCHIVE'?'good':state==='DISCONNECTED'?'bad':'');$('connection').innerHTML='<span class="dot"></span>'+({CONNECTED:'연결됨',ARCHIVE:'공식 보관 자료',DISCONNECTED:'연결 끊김',CONNECTING:'연결 중'}[state]||'연결 대기');$('error').textContent=v.connection?.error||'';
 if($('dataReviewBadge')){$('dataReviewBadge').textContent=demo?'가상 자료 · 실제 보도와 분리':v.review?.status==='APPROVED'?'공식 집계 · 독립 검수 완료':'공식 집계 · 독립 검수 필요';$('dataReviewBadge').className='pill '+(demo?'draft-pill':v.review?.status==='APPROVED'?'good':'warn')}
 $('baseline').textContent=displayArchive(v)?'2024.04.11 06:00 (임의)':timeText(v.rows?.[0]?.baseline_at);$('collected').textContent=timeText(v.collected_at);$('updated').textContent=new Date().toLocaleTimeString('ko-KR',{hour12:false,timeZone:'Asia/Seoul'});
 const regions=[...new Set((v.rows||[]).map(r=>r.region_name))],selected=$('region').value;if(regions.join()!==[...$('region').options].map(o=>o.value).join()){$('region').innerHTML=regions.map(r=>`<option value="${esc(r)}">${esc(r)}</option>`).join('');if(regions.includes(selected))$('region').value=selected}table();
}
function connect(){if(typeof clearTimeout!=='undefined')clearTimeout(reconnectTimer);publishNewsroom({connection:{state:'CONNECTING'}});if(liveSocket){liveSocket.onclose=null;liveSocket.close()}const ws=liveSocket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws?mode='+selectedMode());ws.onmessage=e=>{if(liveSocket!==ws)return;try{update(JSON.parse(e.data))}catch{$('error').textContent='수신 자료를 표시하지 못했습니다. 연결 상태를 확인해 주세요.'}};ws.onclose=()=>{if(liveSocket!==ws)return;$('connection').className='pill bad';$('connection').innerHTML='<span class="dot"></span>재연결 중';publishNewsroom({connection:{state:'DISCONNECTED'}});reconnectTimer=setTimeout(connect,2000)}}
function show(a){
 if(typeof window!=='undefined'){const articles=(window.newsroomView?.articles||[]).map(item=>item.id===a.id?a:item);publishNewsroom({current:a,articles})}
 if(current?.id!==a.id){$('checked').checked=false;$('aiAck').checked=false;$('reason').value=''}current=a;
 $('selectedTitle').textContent=a.title;$('selectedAuthor').textContent='작성자 '+a.author;$('selectedStatus').textContent=statuses[a.status]||a.status;$('selectedStatus').className='pill '+(a.status==='APPROVED'?'good':a.status==='REVIEW_REQUIRED'?'warn':'draft-pill');
 $('articleStatus').textContent=`${a.title} · ${a.status} · ${a.mode==='demo'?'시뮬레이션':'과거 자료'} · 작성자 ${a.author}`;
 $('article').innerHTML=a.sentences.map(s=>`<p>${esc(s.text)}<span class="evidence-tag">근거 ID: ${esc((s.row_ids||s.evidence_ids||[]).join(', '))}</span></p>`).join('');
 const v=a.validation;$('checks').textContent=JSON.stringify(v||{status:'검증 전',ai:a.ai_review},null,2);$('ruleBadge').textContent=v?(v.rule==='PASS'?'규칙 검증 통과':'검토 필요'):'검증 전';$('ruleBadge').className='pill '+(v?(v.rule==='PASS'?'good':'bad'):'');
 $('aiBadge').textContent=v?.disagreement?'규칙·AI 판정 불일치':a.ai_review?.verdict==='UNAVAILABLE'?'AI 보조 검토 미연결':'AI 판정: '+(a.ai_review?.verdict||'미확인');$('aiBadge').className='pill '+(v?.disagreement?'bad':'warn');$('checkErrors').textContent=(v?.errors||[]).join(' / ');$('checkErrors').hidden=!v?.errors?.length;
 $('validate').disabled=false;syncApproval();$('export').disabled=a.status!=='APPROVED';
}
function syncApproval(){const v=current?.validation,allowed=typeof loggedUser==='undefined'||loggedUser?.role==='editor';$('approve').disabled=!(allowed&&current?.status==='PENDING_HUMAN'&&v?.rule==='PASS'&&!v?.disagreement&&$('checked').checked&&$('aiAck').checked&&$('reason').value.trim().length>=5)}
['checked','aiAck','reason'].forEach(id=>$(id).addEventListener('input',syncApproval));
const action=f=>async()=>{try{await f();$('message').className='message';$('message').textContent='처리했습니다.'}catch(e){$('message').className='message is-error';$('message').textContent=e.message}};
function renderEvidence(hits,context,query,view='all'){
 const source=context.directory,showPublications=view!=='existing',showExisting=view!=='publications';
 const stats=`<div class="evidence-summary"><strong>${esc(context.region_name)} · ${esc(context.candidate_name)}</strong><span>공식 공보 위치 ${source?1:0}건 · 기존 보유 문서 ${context.registered_documents}건 · 검색 가능한 본문 ${context.active_chunks}개 문단</span></div>`;
 const directory=showPublications&&source?`<div class="source-directory"><span class="pill">선거공보·홍보물 확인</span><h3>${esc(source.title)}</h3><p>${esc(source.location)} · 발행연도 ${source.publication_year}년 · 발행기관 ${esc(source.publisher)} · 소장기관 ${esc(source.catalog_provider)}</p><p class="source-links"><a href="${safeSource(source.source_url)}" target="_blank" rel="noopener noreferrer">국회도서관 공보 자료 열기 ↗</a><a href="${safeSource(source.original_portal_url)}" target="_blank" rel="noopener noreferrer">선관위 홍보물 찾아보기 ↗</a><a href="${safeSource(source.policy_url)}" target="_blank" rel="noopener noreferrer">정책·공약마당 확인 ↗</a></p><div class="material-instructions"><strong>자료 확인 순서</strong><p>2024년 제22대 총선 → 인천 → ${esc(context.region_name)} → ${esc(context.candidate_name)} → 선거공보·홍보물</p><p>국회도서관 자료에서는 목차의 ${source.catalog_start_page}쪽부터 해당 후보를 확인하세요. 쪽수는 합본 목차 기준입니다.</p>${query?`<p>보도 질문: “${esc(query)}” · 자료를 연 뒤 해당 내용을 찾아 출처·쪽수·발행 시점을 대조하세요.</p>`:''}</div><p class="evidence-meta">자료 ID ${esc(source.source_id)} · 수집 ${esc(timeText(source.collected_at))} · 게시일 미제공</p><p class="evidence-disclosure">공보 위치 정보이며 공약 내용의 증거가 아닙니다. 외부 자료 열람만으로 기사 근거와 승인 상태가 변경되지는 않습니다.</p></div>`:'';
 const cards=showExisting?hits.map(c=>{const url=safeSource(c.url),state=context.document_states[c.document_id],status=c.is_demo?'가상 자료':state==='APPROVED'?'독립 검수 완료':state==='REJECTED'?'반려·승인 철회':'독립 검수 필요';return `<div class="evidence-card"><span class="pill ${!c.is_demo&&state==='APPROVED'?'good':'warn'}">${status}</span>${!c.is_demo&&url?`<a class="evidence-link" href="${url}" target="_blank" rel="noopener noreferrer">기존 자료 출처 열기 ↗</a>`:''}<h3>▤ ${esc(c.title)}</h3><p>${esc(c.text)}</p><div class="evidence-meta">근거 ID <b>${esc(c.id)}</b>　|　발행기관 ${esc(c.publisher)}　|　게시일 ${esc(c.published_at)}　|　원문 위치 ${esc(c.location)}</div>${c.is_demo?'<div class="evidence-disclosure">시뮬레이션 문서 · 실제 후보 공약이 아닙니다</div>':''}</div>`}).join(''):'';
 const empty=showExisting&&!hits.length?`<p class="empty">${context.registered_documents?`“${esc(query)}”에 맞는 보유 자료의 문단이 없습니다. 기존 자료 전체 보기를 누르거나 검색어를 바꿔 주세요.`:'현재 보유 자료에는 이 후보의 공약 본문이 없습니다. 선거공보·홍보물 메뉴의 공식 자료를 열어 직접 확인하세요.'}</p>`:'';
 const resultCount=showExisting?`<p class="evidence-result-count">${query?'보유 자료 검색 결과':'기존 보유 자료'} ${hits.length}개 문단${hits.length===5?' · 최대 5개 표시':''}</p>`:'';
 const unavailable=showPublications&&!source?'<p class="empty">시뮬레이션 모드에서는 실제 후보의 홍보물을 연결하지 않습니다. 기존 보유 자료에서 가상 문단을 확인하세요.</p>':'';
 return stats+directory+unavailable+resultCount+cards+empty;
}
async function loadEvidence(){
 const request=++searchRequest,q=$('query').value.trim(),region=$('region').value,candidate=$('candidate').value;if(!region||!candidate)return;
 $('evidence').textContent='홍보물 위치와 기존 보유 자료를 확인하고 있습니다…';
 try{
  const params={region,candidate,mode:selectedMode()};
  const [hits,context]=await Promise.all([api('/api/search?'+new URLSearchParams({q,...params})),api('/api/pledge-context?'+new URLSearchParams(params))]);
  if(request!==searchRequest)return;
  $('evidence').innerHTML=renderEvidence(hits,context,q,$('evidenceView').value);
 }catch(error){if(request===searchRequest)$('evidence').textContent='공약 자료를 불러오지 못했습니다. '+error.message}
}
$('allEvidence').onclick=action(async()=>{$('query').value='';await loadEvidence()});
$('evidenceView').onchange=action(loadEvidence);
$('region').onchange=table;$('candidate').onchange=action(loadEvidence);$('search').onclick=action(loadEvidence);$('query').addEventListener('keydown',e=>{if(e.key==='Enter')$('search').click()});
$('official').onclick=action(async()=>{if(!$('officialRows').hidden){$('officialRows').hidden=true;$('official').setAttribute('aria-expanded','false');return}const v=await api('/api/official-results');$('officialRows').innerHTML='<p>'+esc(v.label)+'</p><div class="scroll"><table><thead><tr><th>지역구</th><th>후보</th><th>정당</th><th>집계 득표수</th><th>계산 득표율</th></tr></thead><tbody>'+v.rows.map(r=>`<tr><td>${esc(r.region_name)}</td><td>${esc(r.candidate_name)}</td><td>${esc(r.party)}</td><td>${Number(r.votes).toLocaleString('ko-KR')}</td><td>${Number(r.vote_share).toFixed(2)}%</td></tr>`).join('')+'</tbody></table></div>';$('officialRows').hidden=false;$('official').setAttribute('aria-expanded','true')});
$('productionToggle').onclick=()=>{const open=$('productionInfo').hidden;$('productionInfo').hidden=!open;$('productionToggle').setAttribute('aria-expanded',String(open))};
$('draft').onclick=async()=>{
 if(articleBusy)return;articleBusy=true;
 const button=$('draft'),notice=$('draftMessage');
 button.disabled=true;button.textContent='초안 생성 중…';notice.className='message';notice.textContent='작성자 연결과 선택 지역의 자료를 확인하고 있습니다…';
 try{
  if(!$('region').value)throw Error('02 영역에서 지역을 먼저 선택해 주세요.');
  const user=await ensureArticleSession();
  if(user.role!=='writer')throw Error('기사 생성은 작성자 계정으로 가능합니다. 로그아웃 후 담당자 로그인에서 작성자로 로그인해 주세요.');
  const article=await api('/api/articles',{region:$('region').value,mode:selectedMode()});show(article);
  const pledgeCount=article.sentences.filter(s=>s.kind==='pledge').length;
  notice.textContent='초안을 생성했습니다. 아래 05 영역에서 본문과 근거를 확인하고 규칙 검증을 진행하세요.'+(pledgeCount?'':' 등록된 공약 근거가 없어 개표 결과만 작성했습니다. 03에서 홍보물·기존 자료를 확인하세요. 기사에 공약 문장을 넣으려면 검증 가능한 본문 근거가 필요합니다.');
 }catch(e){notice.className='message is-error';notice.textContent=e.message}
 finally{articleBusy=false;button.disabled=typeof loggedUser!=='undefined'&&loggedUser&&loggedUser.role!=='writer';button.textContent='▤ 기사 초안 생성'}
};
$('list').onclick=async()=>{
 const button=$('list'),notice=$('draftMessage');button.disabled=true;button.textContent='목록 불러오는 중…';notice.className='message';notice.textContent='기사 목록을 확인하고 있습니다…';
 try{
  await ensureArticleSession();
  const articles=(await api('/api/articles')).filter(a=>a.mode===selectedMode());renderArticleButtons(articles);
  if(!articles.length){notice.textContent='기사 초안 생성으로 새 기사를 작성하세요.';return}
  notice.textContent=(selectedMode()==='official'?'공식 자료':'시뮬레이션')+' 기사 '+articles.length+'건을 불러왔습니다. 목록에서 기사를 선택하세요.';
 }catch(error){notice.className='message is-error';notice.textContent=error.message}
 finally{button.disabled=false;button.textContent='☷ 기사 목록'}
};
$('validate').onclick=action(async()=>show(await api(`/api/articles/${current.id}/validate`,{})));
$('approve').onclick=action(async()=>show(await api(`/api/articles/${current.id}/approve`,{reason:$('reason').value,evidence_checked:$('checked').checked,ai_unavailable_ack:$('aiAck').checked})));
$('export').onclick=action(async()=>{const v=await api(`/api/articles/${current.id}/export`),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(v,null,2)],{type:'application/json'}));a.download=current.id+'.json';a.click();URL.revokeObjectURL(a.href)});
if(typeof window!=='undefined'){
 window.addEventListener('newsroom:candidate',event=>{if([...$('candidate').options].some(option=>option.value===event.detail)){$('candidate').value=event.detail;table()}});
 window.addEventListener('newsroom:select-article',event=>{if(window.newsroomView?.articles?.some(article=>article.id===event.detail))void action(async()=>show(await api('/api/articles/'+event.detail)))()});
 window.addEventListener('pageshow',event=>{if(event.persisted)connect()});
 window.addEventListener('pagehide',()=>{clearTimeout(reconnectTimer);if(liveSocket){liveSocket.onclose=null;liveSocket.close()}});
}
connect();
