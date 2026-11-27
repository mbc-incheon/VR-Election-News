/* Guide the existing workflow without treating a mode switch as a new reviewer. */
function workflowErrorLabel(code){
 if(code==='DATASET_REVIEW_REQUIRED')return '공식 개표 자료의 독립 검수를 완료하세요.';
 if(code.includes('DOCUMENT_REVIEW_REQUIRED'))return '기사에 사용한 공약 문서의 독립 검수를 완료하세요.';
 if(code==='NO_PLEDGE_EVIDENCE')return '공약 본문 근거가 없습니다. 근거를 등록하거나 개표 결과 기사로 다시 작성하세요.';
 if(code.includes('NEWS_REFERENCE'))return '선택한 참고 기사의 지역·기간·출처를 다시 확인하세요.';
 return '문장과 원본 근거를 대조하세요: '+code;
}
function updateWorkflowGuidance(){
 const stage=document.getElementById('workflowStage'),next=document.getElementById('workflowNext'),handoff=document.getElementById('reviewHandoff'),production=document.getElementById('workflowProduction');if(!stage)return;
 const article=current,user=typeof loggedUser==='undefined'?null:loggedUser;
 const request=document.getElementById('workflowRefresh'),writerView=document.body.dataset.workspace!=='editor';
 request.textContent=writerView?'편집자 승인 요청':'기사 상태 새로고침';request.disabled=!article||(writerView&&article.status==='APPROVED');
 handoff.hidden=!article||article.status==='APPROVED';if(article)handoff.href='/login?article='+encodeURIComponent(article.id);
 production.disabled=article?.status!=='APPROVED';production.textContent=production.disabled?'최종 승인 후 뉴스 제작':'승인 기사로 뉴스 제작';production.title=production.disabled?'승인 대기 상태입니다. 확인란과 승인 사유를 입력하고 최종 승인을 완료하세요.':'';
 const approveShortcut=document.getElementById('workflowApprove');if(approveShortcut)approveShortcut.disabled=document.getElementById('approve').disabled;
 if(!article){stage.textContent='1. 기사 작성';next.textContent='04에서 후보와 제목을 입력하고 기사 초안 생성을 누르세요.';return}
 stage.textContent=article.title+' · v'+(article.revision||1)+' · '+(statuses[article.status]||article.status)+' · 작성자 '+article.author;
 if(article.status==='APPROVED'){next.textContent='최종 승인이 완료됐습니다. 승인본을 내보내거나 뉴스 제작을 시작하세요.';return}
 if(article.validation?.errors?.length){next.textContent='2. 검증 보완: '+[...new Set(article.validation.errors.map(workflowErrorLabel))].join(' ');return}
 if(article.validation?.disagreement){next.textContent='2. 규칙 검증과 AI 보조 판정이 다릅니다. 근거를 대조하고 불일치를 해소한 뒤 다시 검증하세요.';return}
 if(!article.validation||article.validation.rule!=='PASS'){next.textContent='2. 규칙 검증을 실행하세요. 연결 실패 시 초안은 목록에 보존되어 있습니다.';return}
 if(user?.name===article.author){next.textContent='3. 규칙 검증 통과. 현재 계정이 이 기사의 작성자이므로 직접 승인할 수 없습니다. 아래에서 다른 편집자·관리자로 로그인하면 같은 기사를 이어서 엽니다.';return}
 if(!user||!['editor','admin'].includes(user.role)){next.textContent='3. 규칙 검증 통과. 다른 편집자 또는 관리자 계정으로 로그인해 최종 검토하세요.';return}
 const missing=[];if(!document.getElementById('checked').checked)missing.push('원문 대조 확인');if(!document.getElementById('aiAck').checked)missing.push('AI 미연결 확인');if(document.getElementById('reason').value.trim().length<5)missing.push('승인 사유 5자 이상');
 next.textContent=missing.length?'3. 최종 승인 준비: '+missing.join(' · '):'3. 검토 완료·최종 승인 버튼을 누르세요. 완료되면 뉴스 제작 버튼이 활성화됩니다.';
}
document.getElementById('workflowApprove').onclick=()=>document.getElementById('approve').click();
document.getElementById('workflowRefresh').onclick=async()=>{
 const button=document.getElementById('workflowRefresh');if(!current||button.disabled)return;button.disabled=true;
 try{await wbIdentity();const writerView=document.body.dataset.workspace!=='editor';
 const path='/api/articles/'+current.id;const article=writerView?await api(path+'/validate',{}):await api(path);show(article);
 if(writerView)document.getElementById('workflowNext').textContent=article.status==='PENDING_HUMAN'?'편집자 승인 요청이 완료됐습니다. 편집자는 기사 목록에서 이 기사를 선택해 검토·최종 승인할 수 있습니다.':'승인 요청을 완료하지 못했습니다. 검증 실패 항목을 보완한 뒤 다시 요청하세요.';
 }catch(error){document.getElementById('workflowNext').textContent=error.message}finally{button.disabled=!current||(document.body.dataset.workspace!=='editor'&&current.status==='APPROVED')}
};
document.getElementById('workflowProduction').onclick=()=>document.getElementById('productionToggle').click();
updateWorkflowGuidance();
(async()=>{
 const params=new URLSearchParams(location.search),id=params.get('article'),production=params.get('production')==='1';
 if(!id){if(production){try{const mode=params.get('mode');if(['demo','official'].includes(mode)){const snapshot=await api('/api/snapshot?mode='+mode);if(mode==='official')officialRegions=[...new Set(snapshot.rows.map(row=>row.region_name))];$('dataMode').value=mode;refreshRegionOptions();$('dataMode').onchange();const region=params.get('region');if(region&&mode==='official')$('region').value=region;update(snapshot)}await $('productionToggle').onclick()}catch(error){wbError(error)}}return}if(!/^[a-f0-9]{16}$/.test(id))return;
 try{
  await ensureArticleSession();const article=await api('/api/articles/'+id);const snapshot=await api('/api/snapshot?mode='+article.mode);
  $('dataMode').value=article.mode;officialRegions=snapshot.mode==='official'?[...new Set(snapshot.rows.map(row=>row.region_name))]:officialRegions;refreshRegionOptions();$('region').value=article.mode==='demo'?'':article.region_name;$('dataMode').onchange();$('region').value=article.mode==='demo'?'':article.region_name;update(snapshot);
  await loadSelectedArticles();selectedNews={region:article.region_name,ids:(article.news_references||[]).map(item=>item.id),references:article.news_references||[],from:article.news_period?.start,to:article.news_period?.end};
  $('newArticleTitle').value=article.title;$('draftType').value=article.article_type||'combined';if(loggedUser?.role==='editor'||document.body.dataset.workspace==='editor')await openSelectedArticle(article.id);else show(article);syncPreparation();location.hash=production?'production':'review';if(production)await $('productionToggle').onclick();
 }catch(error){document.getElementById('workflowStage').textContent='검토할 기사를 열지 못했습니다.';document.getElementById('workflowNext').textContent=error.message;const link=document.getElementById('reviewHandoff');link.hidden=false;link.href='/login?article='+encodeURIComponent(id);location.hash='review'}
})();
