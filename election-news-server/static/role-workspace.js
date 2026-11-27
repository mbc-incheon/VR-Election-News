/* Shared newsroom layout; role only changes the page background. */
function applyWorkspace(user,mode){
 const editing=user?.role==='editor'||user?.role==='admin'&&['editor','approval'].includes(mode);
 document.body.dataset.workspace=editing?'editor':'writer';
}
async function refreshWorkspace(user){let mode='writer';if(user?.role==='admin'){try{mode=(await api('/api/admin/work-mode')).mode}catch{}}applyWorkspace(user,mode)}
window.addEventListener('newsroom:identity',event=>refreshWorkspace(event.detail));
window.addEventListener('newsroom:work-mode',event=>applyWorkspace(loggedUser,event.detail));
applyWorkspace(null,'writer');
