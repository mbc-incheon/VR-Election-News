/* Role-specific workspaces change presentation, never the authenticated identity. */
let newsroomWorkspaceMode=null;
function applyWorkspace(user,mode){
 const editing=user?.role==='editor'||user?.role==='admin'&&['editor','approval'].includes(mode);
 newsroomWorkspaceMode=editing?'editor':'writer';document.body.dataset.workspace=newsroomWorkspaceMode;
 $('workspaceHeading').textContent=editing?'편집자 검토 화면':'작성자 업무 화면';
 $('workspaceDescription').textContent=editing?'검토할 기사를 선택하고 근거·규칙을 대조한 뒤 최종 승인합니다.':'참고 기사와 공약을 확인해 초안을 작성하고 편집자에게 검토를 요청합니다.';
 $('editorWorkspace').hidden=!editing;
 for(const id of ['writing','pledges','openDocuments','editArticle'])$(id).hidden=editing;
 $('writerWorkspaceLink').hidden=editing;$('editorWorkspaceLink').hidden=!editing;
 $('openReviews').hidden=!editing;$('openAudit').hidden=!editing;
 for(const id of ['checked','aiAck','reason'])$(id).closest('label').hidden=!editing;
 for(const id of ['approve','workflowApprove','export'])$(id).hidden=!editing;
 document.querySelector('a[href="#article-generator"]').hidden=editing;
 document.querySelector('nav a[href="#writing"]').hidden=editing;
 document.querySelector('nav a[href="#pledges"]').hidden=editing;
 $('review-title').textContent=editing?'기사와 팩트체크·최종 승인':'기사와 팩트체크·검토 요청';
 if(editing)loadEditorQueue().catch(error=>{$('editorQueueMessage').textContent=error.message});
}
async function refreshWorkspace(user){let mode='writer';if(user?.role==='admin'){try{mode=(await api('/api/admin/work-mode')).mode}catch{}}applyWorkspace(user,mode)}
async function loadEditorQueue(){
 const list=await api('/api/articles'),status=$('editorQueueStatus').value,query=$('editorQueueSearch').value.trim().toLowerCase();
 const visible=list.filter(a=>(!status||a.status===status)&&(!query||(a.title+' '+a.region_name+' '+a.author).toLowerCase().includes(query)));
 $('editorQueueMessage').textContent=visible.length+'건 · 선택 후 05에서 본문·근거와 검증 결과를 확인하세요.';
 $('editorQueue').innerHTML=visible.map(a=>'<div class="record-card"><strong>'+esc(a.title)+'</strong><p>'+esc(a.region_name)+' · 작성자 '+esc(a.author)+' · '+esc(statuses[a.status]||a.status)+'</p><button type="button" data-editor-article="'+esc(a.id)+'">검토할 기사 선택</button></div>').join('')||'<p>검색 조건에 맞는 기사가 없습니다.</p>';
 document.querySelectorAll('[data-editor-article]').forEach(button=>button.onclick=wbAction(async()=>{const article=await api('/api/articles/'+button.dataset.editorArticle),snapshot=await api('/api/snapshot?mode='+article.mode);$('dataMode').value=article.mode;if(article.mode==='official')officialRegions=[...new Set(snapshot.rows.map(r=>r.region_name))];refreshRegionOptions();$('dataMode').onchange();$('region').value=article.mode==='demo'?'':article.region_name;update(snapshot);show(article);location.hash='review'}));
}
$('editorQueueRefresh').onclick=wbAction(loadEditorQueue);$('editorQueueStatus').onchange=wbAction(loadEditorQueue);$('editorQueueSearch').oninput=wbAction(loadEditorQueue);
window.addEventListener('newsroom:identity',event=>refreshWorkspace(event.detail));
window.addEventListener('newsroom:work-mode',event=>applyWorkspace(loggedUser,event.detail));

applyWorkspace(null,'writer');
