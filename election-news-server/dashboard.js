const $=x=>document.getElementById(x);
let snap={},current=null,selectionKey='',searchRequest=0,liveSocket,reconnectTimer;
const selectedMode=()=> $('dataMode')?.value||'demo';
let officialRegions=[];
const selectedRegion=()=>selectedMode()==='demo'?'계양구을':($('region').value||'');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setSelectOptions(select,markup){if(select&&select._optionsMarkup!==markup){select.innerHTML=markup;select._optionsMarkup=markup}}
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
let articleBusy=false,articleContextKey='',selectedNews={ids:[]};
function publishNewsroom(patch){
 if(typeof window==='undefined')return;
 window.newsroomView={...(window.newsroomView||{}),...patch};
 window.dispatchEvent(new CustomEvent('newsroom:view',{detail:window.newsroomView}));
}
function renderArticleButtons(articles){
 publishNewsroom({articles});
 if(typeof window!=='undefined'&&window.newsroomReactLists)return;
 $('articles').innerHTML='';
 articles.forEach(a=>{const item=document.createElement('button');item.className='secondary';item.textContent=a.title+' · '+(statuses[a.status]||a.status);item.onclick=action(async()=>{show(await api('/api/articles/'+a.id));focusArticleWorkspace('editor')});$('articles').appendChild(item)});
}

let preparation={key:'',confirmed:{},loaded:null};
function preparationTargets(){return (snap.rows||[]).filter(row=>row.region_name===selectedRegion()&&(!$('draftCandidate').value||row.candidate_id===$('draftCandidate').value))}
function preparationKey(){return JSON.stringify([selectedMode(),selectedRegion(),preparationTargets().map(row=>row.candidate_id)])}
function preparationReady(){const targets=preparationTargets();return preparation.key===preparationKey()&&targets.length>0&&targets.every(row=>preparation.confirmed[row.candidate_id])}
function syncPreparation(){
 const key=preparationKey();if(preparation.key!==key){preparation={key,confirmed:{},loaded:null};$('evidenceAcknowledged').checked=false}
 const targets=preparationTargets(),done=targets.filter(row=>preparation.confirmed[row.candidate_id]).length;
 $('preparationStatus').textContent=selectedRegion()+' · 자료 확인 '+done+'/'+targets.length+'명'+(preparationReady()?' 완료 · 기사 생성 가능':' · 초안 생성 가능 · 자료 확인은 진행 중입니다.');
 const loaded=preparation.loaded,valid=loaded&&loaded.key===key&&loaded.candidate===$('candidate').value&&targets.some(row=>row.candidate_id===loaded.candidate);
 $('evidenceAcknowledged').disabled=!valid;$('confirmEvidence').disabled=!valid||!$('evidenceAcknowledged').checked;
 const newsMatches=selectedNews.region===selectedRegion()&&selectedMode()==='official'&&selectedNews.ids?.length;
 $('selectedNewsSummary').hidden=!newsMatches;if(newsMatches)$('selectedNewsSummary').innerHTML='<strong>03에서 선택한 참고 기사 '+selectedNews.ids.length+'건</strong><p>'+esc(selectedNews.from)+' ~ '+esc(selectedNews.to)+'</p>'+(selectedNews.references||[]).map(item=>'<p><a href="'+safeSource(item.url)+'" target="_blank" rel="noopener noreferrer">'+esc(item.title)+' ↗</a> · '+esc(item.publisher)+'</p>').join('')+'<p>선택 기사는 참고자료이며 공약 근거 확인과 독립 검수를 대신하지 않습니다.</p>';
 const row=(snap.rows||[]).find(row=>row.candidate_id===$('candidate').value&&row.region_name===selectedRegion());
 $('evidenceScope').textContent='03 연결 지역: '+selectedRegion()+' · 확인 후보: '+(row?.candidate_name||'자료 대기');
}
async function goToEvidence(){
 syncPreparation();const targets=preparationTargets();if(!targets.length)throw Error('지역과 후보 자료를 먼저 선택하세요.');
 const next=targets.find(row=>!preparation.confirmed[row.candidate_id])||targets[0];$('candidate').value=next.candidate_id;
 location.hash='pledges';$('evidenceFlowMessage').textContent='자료와 출처를 확인한 뒤 아래 확인란을 선택하세요.';await loadEvidence();
}
async function confirmEvidenceAndContinue(){
 syncPreparation();if($('confirmEvidence').disabled)throw Error('선택 후보의 자료를 불러온 뒤 확인란을 선택하세요.');
 const loaded=preparation.loaded;preparation.confirmed[loaded.candidate]={at:new Date().toISOString(),evidence_ids:loaded.ids,has_body:loaded.hasBody};$('evidenceAcknowledged').checked=false;
 const next=preparationTargets().find(row=>!preparation.confirmed[row.candidate_id]);
 if(next){$('candidate').value=next.candidate_id;$('evidenceFlowMessage').textContent='다음 후보 '+next.candidate_name+'의 자료를 확인해 주세요.';await loadEvidence();return}
 syncPreparation();syncDraftAvailability();location.hash='article-generator';$('article-generator').focus();$('draftMessage').textContent='선택 후보의 자료 확인을 마쳤습니다. 기사 유형과 후보를 확인하고 기사 초안 생성을 누르세요.';
}
function focusArticleWorkspace(view='editor'){
 const target=view==='list'?$('articles'):$('inlineArticleWorkspace');
 target.scrollIntoView({behavior:'smooth',block:'start'});
}
function syncDraftAvailability(){
 const disabled=articleBusy||!preparationTargets().length||(typeof loggedUser!=='undefined'&&loggedUser&&!['writer','admin'].includes(loggedUser.role));
 $('draft').disabled=Boolean(disabled);
 $('draftAvailability').textContent=articleBusy?'초안을 생성하고 있습니다. 잠시 기다려 주세요.':typeof loggedUser!=='undefined'&&loggedUser&&!['writer','admin'].includes(loggedUser.role)?'현재 계정은 '+(loggedUser.role==='admin'?'관리자':'편집자')+'입니다. 작성자로 로그인해야 초안을 생성할 수 있습니다.':!preparationTargets().length?'지역·후보 자료를 불러오는 중입니다.':!preparationReady()?'초안 생성 가능 · 자료 확인 미완료: '+preparationTargets().filter(row=>!preparation.confirmed[row.candidate_id]).map(row=>row.candidate_name).join(' · ')+'. 생성 후 본문·근거를 확인하세요.':'작성 가능 · '+selectedRegion()+' · 생성 시점 데이터로 초안을 고정합니다.';
}
function articleScope(){return {mode:selectedMode(),region:selectedRegion()}}
function sameArticleScope(scope){return scope.mode===selectedMode()&&scope.region===selectedRegion()}
async function loadSelectedArticles(connectSession=false){
 const scope=articleScope();if(!scope.region)return [];
 if(connectSession)await ensureArticleSession();
 const articles=(await api('/api/articles')).filter(article=>article.mode===scope.mode&&article.region_name===scope.region);
 if(sameArticleScope(scope)){
  renderArticleButtons(articles);
  $('draftMessage').textContent=scope.region+' · '+(scope.mode==='official'?'실제 선거 결과':'가상 개표')+' 기사 '+articles.length+'건.'+(articles.length?' 목록에서 선택하거나 새 초안을 생성하세요.':' 기사 초안 생성으로 새 기사를 작성하세요.');
 }
 return articles;
}
function resetArticleWorkspace(){
 current=null;renderArticleButtons([]);publishNewsroom({current:null});
 $('draftPreview').hidden=true;$('draftPreview').innerHTML='';
 $('selectedTitle').textContent=selectedRegion()+' · 기사를 생성하거나 선택하세요';$('selectedAuthor').textContent='작성자 —';$('selectedStatus').textContent='대기';
 $('article').innerHTML='<p class="empty">선택한 지역의 기사를 생성하거나 목록에서 선택하세요.</p>';
 $('checked').checked=false;$('aiAck').checked=false;$('reason').value='';$('validate').disabled=true;$('export').disabled=true;syncApproval();
}
function displayArchive(snapshot){return snapshot.mode==='official'&&snapshot.stage==='FINAL_FILE_AGGREGATION'}
function table(){
 const selected=$('candidate').value,region=selectedRegion(),rows=(snap.rows||[]).filter(r=>r.region_name===region);
 $('rows').innerHTML=rows.length?rows.map((r,i)=>{const share=Number(r.vote_share),url=safeSource(r.source_url);return `<tr><td class="candidate-name"><span class="candidate-mark ${i%2?'alternate':''}"></span>${esc(r.candidate_name)}</td><td>${showValue(r.votes==null?null:Number(r.votes).toLocaleString('ko-KR'),'표')}</td><td><div class="vote-share"><span class="share-value">${showValue(r.vote_share==null?null:share.toFixed(2),'%')}</span><div class="bar" aria-hidden="true"><span style="width:${Number.isFinite(share)?Math.max(0,Math.min(100,share)):0}%"></span></div></div></td><td>${displayArchive(snap)?'100% (표시값)':showValue(r.count_rate,'%')}</td><td class="table-time" title="${esc(displayArchive(snap)?'임의 기준시각: 2024.04.11 06:00 (한국시간)':r.baseline_at||'미제공')}">${displayArchive(snap)?'06:00 (임의)':esc(timeText(r.baseline_at,true))}</td><td class="table-source">${r.is_demo?'시뮬레이션':url?`<a href="${url}" target="_blank" rel="noopener noreferrer">공식 원문</a>`:'출처 미제공'}</td></tr>`}).join(''):'<tr><td colspan="6" class="empty">선택한 지역의 자료가 없습니다.</td></tr>';
 setSelectOptions($('candidate'),rows.map(r=>`<option value="${esc(r.candidate_id)}">${esc(r.candidate_name)}${r.is_demo?' · 가상 후보 '+r.candidate_number:''}</option>`).join(''));if(rows.some(r=>r.candidate_id===selected))$('candidate').value=selected;
 const draftSelected=$('draftCandidate').value;setSelectOptions($('draftCandidate'),'<option value="">지역 후보 전체</option>'+rows.map(row=>`<option value="${esc(row.candidate_id)}">${esc(row.candidate_name)}</option>`).join(''));if(rows.some(row=>row.candidate_id===draftSelected))$('draftCandidate').value=draftSelected;const draftScope=selectedMode()+'|'+region;if(rows.length&&$('draftCandidate')._scope!==draftScope){$('draftCandidate')._scope=draftScope;$('draftCandidate').value=$('candidate').value}syncPreparation();syncDraftAvailability();
 publishNewsroom({snapshot:snap,region,candidate:$('candidate').value});
 const articleKey=snap.mode+'|'+region;if(region&&snap.mode===selectedMode()&&articleKey!==articleContextKey){articleContextKey=articleKey;resetArticleWorkspace();void loadSelectedArticles().catch(error=>{if(articleContextKey===articleKey){$('draftMessage').textContent=error.status===401?'선택 지역: '+region+'. 기사 초안 생성 또는 기사 목록을 누르면 작성자 계정을 연결합니다.':'기사 목록을 불러오지 못했습니다. '+error.message}})}
 const key=region+'|'+$('candidate').value+'|'+snap.mode;if(key!==selectionKey){selectionKey=key;void loadEvidence().catch(e=>{$('evidence').textContent=e.message})}
}
function update(v){
 if(v.mode!==selectedMode())return;
 snap=v;publishNewsroom({connection:v.connection});const state=v.connection?.state,demo=v.mode==='demo';$('mode').textContent=demo?'▤ 시뮬레이션 데이터':v.mode==='unavailable'?'자료 없음':'2024년 공식 자료';$('modeNote').textContent=demo?'가상 후보 3명 · '+(v.simulation_cycle||1)+'회차 · 개표율 0~100% 반복 · 실제 개표 아님':'과거 선거 자료 · 현재 속보 아님';
 $('connection').className='pill '+(state==='CONNECTED'||state==='ARCHIVE'?'good':state==='DISCONNECTED'?'bad':'');$('connection').innerHTML='<span class="dot"></span>'+({CONNECTED:'연결됨',ARCHIVE:'공식 보관 자료',DISCONNECTED:'연결 끊김',CONNECTING:'연결 중'}[state]||'연결 대기');$('error').textContent=v.connection?.error||'';
 if($('dataReviewBadge')){$('dataReviewBadge').textContent=demo?'가상 자료 · 실제 보도와 분리':v.review?.status==='APPROVED'?'공식 집계 · 독립 검수 완료':'공식 집계 · 독립 검수 필요';$('dataReviewBadge').className='pill '+(demo?'draft-pill':v.review?.status==='APPROVED'?'good':'warn')}
 $('baseline').textContent=displayArchive(v)?'2024.04.11 06:00 (임의)':timeText(v.rows?.[0]?.baseline_at);$('collected').textContent=timeText(v.collected_at);$('updated').textContent=new Date().toLocaleTimeString('ko-KR',{hour12:false,timeZone:'Asia/Seoul'});
 if(v.mode==='official')officialRegions=[...new Set((v.rows||[]).map(r=>r.region_name))].sort((a,b)=>a.localeCompare(b,'ko'));refreshRegionOptions();table();
}
function refreshRegionOptions(){
 const select=$('region'),selected=select.value;
 setSelectOptions(select,'<option value="">계양구을 · 가상 후보 3명 (기본)</option>'+officialRegions.map(region=>`<option value="${esc(region)}">${esc(region)} · 2024년 실제 결과</option>`).join(''));
 select.value=selectedMode()==='demo'?'':officialRegions.includes(selected)?selected:(officialRegions[0]||'');
 if($('evidenceRegion')){setSelectOptions($('evidenceRegion'),select.innerHTML);$('evidenceRegion').value=select.value}
 if($('articleRegion')){setSelectOptions($('articleRegion'),select.innerHTML);$('articleRegion').value=select.value}
}
function chooseRegion(){
 const mode=$('region').value?'official':'demo';
 if(mode!==selectedMode()){$('dataMode').value=mode;$('dataMode').onchange()}else table();
}
async function loadRegionChoices(){
 try{const result=await api('/api/snapshot?mode=official');if(result.mode!=='official'||result.stage!=='FINAL_FILE_AGGREGATION')throw Error('공식 선거구 자료가 없습니다.');officialRegions=[...new Set((result.rows||[]).map(row=>row.region_name))].sort((a,b)=>a.localeCompare(b,'ko'));refreshRegionOptions()}catch(error){$('error').textContent='지난 선거 지역구를 불러오지 못했습니다. 새로고침해 주세요. '+error.message}
}
function connect(){if(typeof clearTimeout!=='undefined')clearTimeout(reconnectTimer);publishNewsroom({connection:{state:'CONNECTING'}});if(liveSocket){liveSocket.onclose=null;liveSocket.close()}const ws=liveSocket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws?mode='+selectedMode());ws.onmessage=e=>{if(liveSocket!==ws)return;try{update(JSON.parse(e.data))}catch{$('error').textContent='수신 자료를 표시하지 못했습니다. 연결 상태를 확인해 주세요.'}};ws.onclose=()=>{if(liveSocket!==ws)return;$('connection').className='pill bad';$('connection').innerHTML='<span class="dot"></span>재연결 중';publishNewsroom({connection:{state:'DISCONNECTED'}});reconnectTimer=setTimeout(connect,2000)}}
function show(a){
 if(typeof window!=='undefined'){const articles=(window.newsroomView?.articles||[]).map(item=>item.id===a.id?a:item);publishNewsroom({current:a,articles})}
 if(current?.id!==a.id){$('checked').checked=false;$('aiAck').checked=false;$('reason').value=''}current=a;
 $('draftPreview').hidden=true;
 $('selectedTitle').textContent=a.title;$('selectedAuthor').textContent='작성자 '+a.author;$('selectedStatus').textContent=statuses[a.status]||a.status;$('selectedStatus').className='pill '+(a.status==='APPROVED'?'good':a.status==='REVIEW_REQUIRED'?'warn':'draft-pill');
 $('articleStatus').textContent=`${a.title} · ${a.status} · ${a.mode==='demo'?'시뮬레이션':'과거 자료'} · 작성자 ${a.author}`;
 $('article').innerHTML=a.sentences.map(s=>`<p>${esc(s.text)}<span class="evidence-tag">근거 ID: ${esc((s.row_ids||s.evidence_ids||[]).join(', '))}</span></p>`).join('');
 const v=a.validation;$('checks').textContent=JSON.stringify(v||{status:'검증 전',ai:a.ai_review},null,2);$('ruleBadge').textContent=v?(v.rule==='PASS'?'규칙 검증 통과':'검토 필요'):'검증 전';$('ruleBadge').className='pill '+(v?(v.rule==='PASS'?'good':'bad'):'');
 $('aiBadge').textContent=v?.disagreement?'규칙·AI 판정 불일치':a.ai_review?.verdict==='UNAVAILABLE'?'AI 보조 검토 미연결':'AI 판정: '+(a.ai_review?.verdict||'미확인');$('aiBadge').className='pill '+(v?.disagreement?'bad':'warn');$('checkErrors').textContent=(v?.errors||[]).join(' / ');$('checkErrors').hidden=!v?.errors?.length;
 $('validate').disabled=false;syncApproval();$('export').disabled=a.status!=='APPROVED';
}
function syncApproval(){const v=current?.validation,allowed=typeof loggedUser==='undefined'||['editor','admin'].includes(loggedUser?.role);$('approve').disabled=!(allowed&&(typeof loggedUser==='undefined'||loggedUser?.name!==current?.author)&&current?.status==='PENDING_HUMAN'&&v?.rule==='PASS'&&!v?.disagreement&&$('checked').checked&&$('aiAck').checked&&$('reason').value.trim().length>=5);if(typeof updateWorkflowGuidance==='function')updateWorkflowGuidance()}
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
 const request=++searchRequest,q=$('query').value.trim(),region=selectedRegion(),candidate=$('candidate').value;if(!region||!candidate)return;
 preparation.loaded=null;$('evidenceAcknowledged').checked=false;syncPreparation();syncDraftAvailability();
 $('evidence').textContent='홍보물 위치와 기존 보유 자료를 확인하고 있습니다…';
 try{
  const params={region,candidate,mode:selectedMode()};
  const [hits,context]=await Promise.all([api('/api/search?'+new URLSearchParams({q,...params})),api('/api/pledge-context?'+new URLSearchParams(params))]);
  if(request!==searchRequest)return;
  $('evidence').innerHTML=renderEvidence(hits,context,q,$('evidenceView').value);
  preparation.loaded={key:preparationKey(),candidate,ids:hits.map(hit=>hit.id),hasBody:context.active_chunks>0};syncPreparation();syncDraftAvailability();
 }catch(error){if(request===searchRequest)$('evidence').textContent='공약 자료를 불러오지 못했습니다. '+error.message}
}
$('allEvidence').onclick=action(async()=>{$('query').value='';await loadEvidence()});
$('evidenceView').onchange=action(loadEvidence);
$('region').onchange=chooseRegion;
$('evidenceRegion').onchange=action(async()=>{$('region').value=$('evidenceRegion').value;chooseRegion();if(snap.mode===selectedMode())await loadEvidence()});
$('articleRegion').onchange=action(async()=>{$('region').value=$('articleRegion').value;chooseRegion();await loadSelectedArticles(true)});
$('searchArticles').onclick=action(async()=>{focusArticleWorkspace('list');await loadSelectedArticles(true)});

const pastResultsLink=document.querySelector('a[href="#past-results"]');if(pastResultsLink)pastResultsLink.addEventListener('click',()=>{$('pastResultsToggle').open=true});
$('candidate').onchange=action(async()=>{if(selectedMode()==='demo')$('query').value='';$('draftCandidate').value=$('candidate').value;syncPreparation();syncDraftAvailability();await loadEvidence()});
$('draftCandidate').onchange=action(async()=>{syncPreparation();syncDraftAvailability();if($('draftCandidate').value){$('candidate').value=$('draftCandidate').value;await loadEvidence()}});
$('draftType').onchange=()=>{syncPreparation();syncDraftAvailability()};
$('goEvidence').onclick=action(goToEvidence);$('confirmEvidence').onclick=action(confirmEvidenceAndContinue);$('evidenceAcknowledged').onchange=syncPreparation;$('search').onclick=action(loadEvidence);$('query').addEventListener('keydown',e=>{if(e.key==='Enter')$('search').click()});
$('official').onclick=action(async()=>{if(!$('officialRows').hidden){$('officialRows').hidden=true;$('official').setAttribute('aria-expanded','false');return}const v=await api('/api/official-results');$('officialRows').innerHTML='<p>'+esc(v.label)+'</p><div class="scroll"><table><thead><tr><th>지역구</th><th>후보</th><th>정당</th><th>집계 득표수</th><th>계산 득표율</th></tr></thead><tbody>'+v.rows.map(r=>`<tr><td>${esc(r.region_name)}</td><td>${esc(r.candidate_name)}</td><td>${esc(r.party)}</td><td>${Number(r.votes).toLocaleString('ko-KR')}</td><td>${Number(r.vote_share).toFixed(2)}%</td></tr>`).join('')+'</tbody></table></div>';$('officialRows').hidden=false;$('official').setAttribute('aria-expanded','true')});
$('productionToggle').onclick=()=>{$('productionMessage').textContent='승인 기사와 제작 상태를 불러오는 중입니다…';if(!$('productionDialog').open)$('productionDialog').showModal();$('productionToggle').setAttribute('aria-expanded','true')};
$('closeProductionDialog').onclick=()=>$('productionDialog').close();$('productionDialog').addEventListener('close',()=>{$('productionToggle').setAttribute('aria-expanded','false');if(typeof jobTimer!=='undefined'&&jobTimer){clearTimeout(jobTimer);jobTimer=null}});
$('draft').onclick=async()=>{
 if(articleBusy)return;focusArticleWorkspace('editor');articleBusy=true;
 const button=$('draft'),notice=$('draftMessage');
 button.disabled=true;button.textContent='초안 생성 중…';notice.className='message';notice.textContent='작성자 연결과 선택 지역의 자료를 확인하고 있습니다…';
 try{
  const scope=articleScope();
  if(!scope.region)throw Error('02 영역에서 지역을 먼저 선택해 주세요.');
  const evidenceReady=preparationReady();
  const user=await ensureArticleSession();
  if(!['writer','admin'].includes(user.role))throw Error('기사 생성은 작성자 또는 관리자 계정으로 가능합니다. 로그아웃 후 담당자 로그인에서 작성자로 로그인해 주세요.');
  if(!sameArticleScope(scope))throw Error('선거구가 변경됐습니다. 선택 지역에서 다시 생성해 주세요.');
  const title=$('newArticleTitle').value.trim();if(title.length<2){$('newArticleTitle').focus();throw Error('기사 제목을 2자 이상 입력하세요.');}
  const articleType=$('draftType').value;
  const news=selectedNews.region===scope.region?selectedNews:{ids:[]};
  let article=await api('/api/articles',{region:scope.region,mode:scope.mode,article_type:articleType,title,evidence_ids:evidenceReady?Object.values(preparation.confirmed).flatMap(item=>item.evidence_ids||[]):null,candidate_id:$('draftCandidate').value||null,news_ids:news.ids,period_from:news.from||'2024-04-03',period_to:news.to||'2024-04-17'});
  if(!sameArticleScope(scope))return;
  let automaticCheckError='';try{article=await api('/api/articles/'+article.id+'/validate',{})}catch(error){automaticCheckError=' 규칙 검증 연결 실패: '+error.message}
  if(!sameArticleScope(scope))return;
  renderArticleButtons([article,...(window.newsroomView?.articles||[]).filter(item=>item.id!==article.id&&item.mode===scope.mode&&item.region_name===scope.region)]);show(article);
  const pledgeCount=article.sentences.filter(s=>s.kind==='pledge').length;
  notice.textContent=automaticCheckError+(!evidenceReady?'자료 확인 미완료 상태로 초안을 생성했습니다. 자동 승인되지 않습니다. ':'초안을 생성했습니다. ')+' 04 영역에서 본문·목록을 확인하고, 05에서 자동 규칙 검증 결과와 다음 단계를 확인하세요.'+(['pledge','combined','news'].includes(articleType)&&!pledgeCount?' 등록된 공약 근거가 없어 공약 문장은 작성하지 않았습니다. 04에서 홍보물·기존 자료를 확인하세요. 기사에 공약 문장을 넣으려면 검증 가능한 본문 근거가 필요합니다.':'');
 }catch(e){notice.className='message is-error';notice.textContent=e.message}
 finally{articleBusy=false;syncDraftAvailability();button.textContent='▤ 기사 초안 생성'}
};
$('list').onclick=async()=>{
 focusArticleWorkspace('list');
 const button=$('list'),notice=$('draftMessage');button.disabled=true;button.textContent='목록 불러오는 중…';notice.className='message';notice.textContent='기사 목록을 확인하고 있습니다…';
 try{
  await loadSelectedArticles(true);
 }catch(error){notice.className='message is-error';notice.textContent=error.message}
 finally{button.disabled=false;button.textContent='☷ 기사 목록'}
};
$('validate').onclick=action(async()=>show(await api(`/api/articles/${current.id}/validate`,{})));
$('approve').onclick=action(async()=>show(await api(`/api/articles/${current.id}/approve`,{reason:$('reason').value,evidence_checked:$('checked').checked,ai_unavailable_ack:$('aiAck').checked})));
$('export').onclick=action(async()=>{const v=await api(`/api/articles/${current.id}/export`),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(v,null,2)],{type:'application/json'}));a.download=current.id+'.json';a.click();URL.revokeObjectURL(a.href)});
if(typeof window!=='undefined'){
 window.addEventListener('newsroom:news-selection',event=>{selectedNews={...event.detail,references:(selectedNews.references||[]).filter(item=>event.detail.ids.includes(item.id))};syncPreparation()});
 window.addEventListener('newsroom:review-selected-news',event=>{void action(async()=>{const detail=event.detail;if(!detail.region||!detail.ids?.length)throw Error('지역선거구와 참고 기사를 먼저 선택하세요.');if(selectedMode()!=='official'||detail.region!==selectedRegion()){const official=await api('/api/snapshot?mode=official');if(official.mode!=='official'||!official.rows?.some(row=>row.region_name===detail.region))throw Error('선택 기사의 공식 선거구 자료를 찾을 수 없습니다.');officialRegions=[...new Set(official.rows.map(row=>row.region_name))];refreshRegionOptions();$('region').value=detail.region;$('dataMode').value='official';$('dataMode').onchange();$('region').value=detail.region;update(official)}selectedNews=detail;$('draftType').value='news';$('draftCandidate').value=detail.candidate_id||'';syncPreparation();syncDraftAvailability();await goToEvidence()})()});
 window.addEventListener('newsroom:save-revision',event=>{void action(async()=>{
  const req=event.detail;if(current?.id!==req.id)throw Error('선택 기사가 변경됐습니다. 다시 선택해 주세요.');
  const scope=articleScope(),user=await ensureArticleSession();if(!['writer','admin'].includes(user.role))throw Error('수정본 저장은 작성자 또는 관리자 계정이 필요합니다.');
  if(!sameArticleScope(scope)||current?.id!==req.id)throw Error('지역 또는 기사가 변경됐습니다.');
  const revised=await api('/api/articles/'+req.id+'/revisions',{title:req.title,sentences:req.sentences,reason:req.reason});
  if(!sameArticleScope(scope))return;renderArticleButtons([revised,...(window.newsroomView?.articles||[]).filter(item=>item.id!==revised.id)]);show(revised);$('draftMessage').textContent='수정본 v'+revised.revision+'을 초안으로 저장했습니다. 05에서 다시 검증해 주세요.';
 })()});
 window.addEventListener('newsroom:candidate' ,event=>{if([...$('candidate').options].some(option=>option.value===event.detail)){$('candidate').value=event.detail;$('draftCandidate').value=event.detail;table()}});
 window.addEventListener('newsroom:select-article',event=>{if(window.newsroomView?.articles?.some(article=>article.id===event.detail))void action(async()=>{const article=await api('/api/articles/'+event.detail);show(article);focusArticleWorkspace('editor')})()});
 window.addEventListener('pageshow',event=>{if(event.persisted)connect()});
 window.addEventListener('pagehide',()=>{clearTimeout(reconnectTimer);if(liveSocket){liveSocket.onclose=null;liveSocket.close()}});
}
connect();
void loadRegionChoices();
