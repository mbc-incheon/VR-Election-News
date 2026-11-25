/* An administrator stays the same authenticated person in every work mode. */
(async()=>{
 const host=document.getElementById('adminWorkMode');if(!host)return;
 try{
  const response=await fetch('/api/admin/work-mode',{credentials:'same-origin',cache:'no-store'});if(!response.ok)return;const initial=await response.json();
  host.hidden=false;host.className='workbar';host.style.cssText='padding:14px;margin:12px 0;border:1px solid #a6c5d7;border-radius:8px;background:#eef7fb;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
  const label=document.createElement('label');label.textContent='관리자 작업 모드 ';label.htmlFor='adminWorkModeSelect';const select=document.createElement('select');select.id='adminWorkModeSelect';
  for(const [value,text] of [['writer','작성자'],['editor','편집자'],['approval','최종 승인']]){const option=document.createElement('option');option.value=value;option.textContent=text;select.appendChild(option)}
  select.value=initial.mode;const status=document.createElement('span');status.setAttribute('role','status');status.textContent=initial.account+' · 관리자 로그인 유지';
  const hint=document.createElement('small');hint.textContent='작업 모드는 화면 이동용입니다. 실제 계정과 승인 책임은 유지됩니다.';
  host.append(label,select,status,hint);
  select.onchange=async()=>{const mode=select.value;select.disabled=true;try{const result=await fetch('/api/admin/work-mode',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});const data=await result.json();if(!result.ok)throw Error(typeof data.detail==='string'?data.detail:'모드를 변경하지 못했습니다.');initial.mode=data.mode;status.textContent=data.account+' · '+select.selectedOptions[0].textContent+' 모드';
   const target=mode==='writer'?'article-generator':mode==='editor'?'pledges':'review';
   if(location.pathname==='/admin'){location.assign('/#'+target);return}
   if(typeof resetReviewConfirmation==='function')resetReviewConfirmation();location.hash=target;
   if(mode==='editor'&&typeof wbReviewList==='function')await wbReviewList();
  }catch(error){select.value=initial.mode;status.textContent=error.message}finally{select.disabled=false}};
 }catch{host.hidden=true}
})();
