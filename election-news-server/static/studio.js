import {candidateColor} from './candidate-colors.js';
import * as THREE from 'three';
import {OrbitControls} from '/static/vendor/OrbitControls.js';
const $=id=>document.getElementById(id);
const contextParams=new URLSearchParams(location.search),requestedArticle=contextParams.get('article'),requestedRegion=contextParams.get('region');let initialRegionPending=!!requestedRegion;
const modeParam=contextParams.get('mode');if(['official','demo'].includes(modeParam))$('mode').value=modeParam;
let renderer,scene,camera,controls,screenTexture,screenCanvas,chartGroup,rows=[],snapshot={},approved=[],currentBundle=null,ws;
const material=(color,metalness=.1)=>new THREE.MeshStandardMaterial({color,metalness,roughness:.5});
function box(w,h,d,x,y,z,color){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material(color));m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;scene.add(m);return m}
function init(){
 scene=new THREE.Scene();scene.background=new THREE.Color('#050d1b');scene.fog=new THREE.Fog('#050d1b',22,60);
 camera=new THREE.PerspectiveCamera(48,1,.1,100);camera.position.set(0,5.0,13);
 renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.outputColorSpace=THREE.SRGBColorSpace;
 $('stage').prepend(renderer.domElement);controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,2,-1);controls.minDistance=7;controls.maxDistance=30;controls.maxPolarAngle=Math.PI*.48;controls.enableDamping=true;
 scene.add(new THREE.HemisphereLight('#9ad8ff','#0b1326',2));const key=new THREE.SpotLight('#e0f7ff',350);key.position.set(4,12,8);key.angle=.7;key.castShadow=true;scene.add(key);scene.add(key.target);
 const glow=new THREE.PointLight('#15d7ca',120);glow.position.set(-7,6,-3);scene.add(glow);
 const floor=new THREE.Mesh(new THREE.CylinderGeometry(12,13,.3,96),material('#102c43',.5));floor.position.y=-.25;floor.receiveShadow=true;scene.add(floor);
 const ring=new THREE.Mesh(new THREE.TorusGeometry(11.5,.045,12,100),new THREE.MeshBasicMaterial({color:'#24dfd1'}));ring.rotation.x=Math.PI/2;ring.position.y=-.05;scene.add(ring);
 const grid=new THREE.GridHelper(60,60,'#174d63','#102235');grid.position.y=-.42;scene.add(grid);
 box(23,11,.4,0,5,-7,'#0d2038');box(.3,10,11,-11,4,-2,'#12344c');box(.3,10,11,11,4,-2,'#12344c');
 for(const x of [-10,-8,8,10])box(.07,9,.2,x,4.5,-6.7,'#1dc4c2');
 box(15.8,7.8,.4,0,5,-6.5,'#244c65');
 screenCanvas=document.createElement('canvas');screenCanvas.width=2048;screenCanvas.height=1024;screenTexture=new THREE.CanvasTexture(screenCanvas);screenTexture.colorSpace=THREE.SRGBColorSpace;
 const display=new THREE.Mesh(new THREE.PlaneGeometry(15.2,7.2),new THREE.MeshBasicMaterial({map:screenTexture}));display.position.set(0,5,-6.25);scene.add(display);
 const desk=box(7.0,.45,2,0,1.4,3.0,'#d8e7ee');desk.rotation.y=-.04;box(6.2,1.2,1.5,0,.6,3.0,'#0c4a5c');box(5.7,.06,.08,0,1.03,3.79,'#20d9c8');
 chartGroup=new THREE.Group();scene.add(chartGroup);
 const resize=()=>{const {width,height}=$('stage').getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix()};new ResizeObserver(resize).observe($('stage'));resize();
 renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera)});$('canvasStatus').hidden=true;draw();
}
function draw(){
 if(!renderer)return;const ctx=screenCanvas.getContext('2d');ctx.fillStyle='#071b31';ctx.fillRect(0,0,2048,1024);ctx.fillStyle='#19b8b2';ctx.fillRect(0,0,2048,12);
 ctx.font='bold 68px "Malgun Gothic", sans-serif';ctx.fillStyle='white';ctx.fillText('VR 선거보도 시스템',85,115);ctx.font='34px "Malgun Gothic", sans-serif';ctx.fillStyle='#8db7c8';ctx.fillText('2024 제22대 총선 · '+($('region').value||'인천 지역구'),85,178);
 const demo=snapshot.mode==='demo';ctx.fillStyle=demo?'#ffd17b':'#84dfd2';ctx.font='28px "Malgun Gothic", sans-serif';ctx.fillText(demo?'시뮬레이션 데이터 · 실제 후보와 수치가 아닙니다':('공식 파일 집계 · '+(snapshot.review?.status==='APPROVED'?'독립 검수 완료':'독립 검수 전')),85,232);
 const displayed=rows.slice(0,5);displayed.forEach((row,i)=>{const y=335+i*119;ctx.fillStyle='white';ctx.font='bold 52px "Malgun Gothic", sans-serif';ctx.fillText(row.candidate_name,85,y);ctx.font='30px "Malgun Gothic", sans-serif';ctx.fillStyle='#b6d4e6';ctx.fillText(Number(row.votes).toLocaleString('ko-KR')+'표',470,y);ctx.fillStyle='#17374c';ctx.fillRect(850,y-35,800,38);ctx.fillStyle=candidateColor(row,i);ctx.fillRect(850,y-35,800*row.vote_share/100,38);ctx.fillStyle='white';ctx.fillText(row.vote_share.toFixed(2)+'%',1700,y)});
 ctx.font='24px "Malgun Gothic", sans-serif';ctx.fillStyle='#9bc0ce';ctx.fillText('득표율은 유효 후보 득표 합 기준 · 기준시각/개표율 미제공 값은 생성하지 않습니다',85,984);screenTexture.needsUpdate=true;
 while(chartGroup.children.length){const mesh=chartGroup.children[0];chartGroup.remove(mesh);mesh.geometry.dispose();mesh.material.dispose()}
 displayed.forEach((r,i)=>{const h=.2+r.vote_share/100*3;const bar=new THREE.Mesh(new THREE.BoxGeometry(.7,h,.7),material(candidateColor(r,i),.4));bar.position.set(-5.8+i*1.0,h/2,-.1);chartGroup.add(bar)});
}
function update(data){
 if(currentBundle)return;snapshot=data;const selected=$('region').value,regions=[...new Set((data.rows||[]).map(r=>r.region_name))];$('region').replaceChildren(...regions.map(r=>new Option(r,r)));if(initialRegionPending&&regions.includes(requestedRegion)){$('region').value=requestedRegion;initialRegionPending=false}else if(regions.includes(selected))$('region').value=selected;
 rows=(data.rows||[]).filter(r=>r.region_name===$('region').value);renderSummary();draw();
}
function syncStudioLinks(){const context={article:currentBundle?.article.id,mode:currentBundle?.article.mode||$('mode').value,region:currentBundle?.article.region_name||$('region').value};$('studioProductionLink').href=NewsroomLinks.url('production',context);$('studioWorkLink').href=NewsroomLinks.url('work',context);}
function renderSummary(){syncStudioLinks();
 $('candidateSummary').replaceChildren(...rows.map(r=>{const div=document.createElement('div');div.className='candidate';const name=document.createElement('span');name.textContent=r.candidate_name+(r.party?' · '+r.party:'');const value=document.createElement('b');value.style.color=candidateColor(r);value.textContent=r.vote_share.toFixed(2)+'%';div.append(name,value);return div}));
 const demo=snapshot.mode==='demo';const note=demo?'시뮬레이션 · 가상 후보와 가상 수치':snapshot.review?.status==='APPROVED'?'2024년 공식 파일 집계 · 독립 검수 완료':'2024년 공식 파일 집계 · 독립 검수 전';$('dataStatus').textContent=note;$('stageDisclosure').textContent=note+(currentBundle?' · 승인 기사에 고정된 자료':'');
}
function connect(){if(ws){ws.onclose=null;ws.close()}ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws?mode='+$('mode').value);ws.onmessage=e=>update(JSON.parse(e.data));ws.onclose=()=>{$('message').textContent='연결이 끊겨 재접속 중입니다.';setTimeout(connect,2500)}}
async function loadArticles(){const selected=$('article').value,r=await fetch('/api/studio/articles');approved=await r.json();$('article').replaceChildren(new Option('승인된 기사 선택',''),...approved.map(b=>new Option(b.article.title+' · '+(b.article.mode==='demo'?'시뮬레이션':'공식 자료'),b.article.id)));if(approved.some(b=>b.article.id===selected))$('article').value=selected}
$('mode').onchange=()=>{currentBundle=null;$('article').value='';$('script').textContent='기사를 선택하면 대본과 근거가 표시됩니다.';connect()};$('region').onchange=()=>{if(currentBundle){$('message').textContent='승인 기사 모드에서는 고정된 지역을 사용합니다. 자료 선택을 바꾸면 결과 탐색으로 돌아갑니다.';return}rows=snapshot.rows.filter(r=>r.region_name===$('region').value);renderSummary();draw()};
$('article').onchange=async()=>{const id=$('article').value;if(!id){currentBundle=null;connect();return}await loadArticles();currentBundle=approved.find(b=>b.article.id===id);if(!currentBundle){$('script').textContent='연결한 승인 기사를 사용할 수 없습니다.';$('message').textContent='삭제·승인 철회·근거 변경 여부를 확인하세요.';syncStudioLinks();connect();return}$('article').value=id;const r=await fetch('/api/snapshot?mode='+currentBundle.article.mode);const live=await r.json();
 // The studio article uses the pinned result values, never a newer replay snapshot.
 $('mode').value=currentBundle.article.mode;snapshot={...live,mode:currentBundle.article.mode};rows=currentBundle.article.sentences.filter(s=>s.kind==='result').map(s=>({...s.values,is_demo:currentBundle.article.mode==='demo'}));$('region').replaceChildren(new Option(currentBundle.article.region_name,currentBundle.article.region_name));$('script').textContent=currentBundle.script+'\n\n'+currentBundle.disclosure+'\n근거: '+currentBundle.article.sentences.flatMap(s=>s.row_ids||s.evidence_ids||[]).join(', ');renderSummary();draw()};
document.querySelectorAll('[data-camera]').forEach(b=>b.onclick=()=>{if(!camera)return;const views={front:[0,5,13],left:[-10,5,12],right:[10,5,12],wide:[0,10,24]};camera.position.set(...views[b.dataset.camera]);controls.target.set(0,2,-1);controls.update()});
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('stage').requestFullscreen()}catch{$('message').textContent='이 브라우저에서는 전체 화면을 사용할 수 없습니다.'}};
$('capture').onclick=()=>{if(!renderer)return;const a=document.createElement('a');a.download='VR-election-studio.png';a.href=renderer.domElement.toDataURL('image/png');a.click()};
$('read').onclick=()=>{if(!currentBundle){$('message').textContent='승인된 기사를 먼저 선택해 주세요.';return}if(!('speechSynthesis'in window)){$('message').textContent='음성 읽기를 지원하지 않는 브라우저입니다.';return}speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(currentBundle.script);utterance.lang='ko-KR';utterance.rate=.95;speechSynthesis.speak(utterance)};$('stop').onclick=()=>window.speechSynthesis?.cancel();
try{init()}catch(e){$('canvasStatus').textContent='3D 그래픽을 시작하지 못했습니다. WebGL을 지원하는 브라우저와 하드웨어 가속을 확인해 주세요.';$('canvasStatus').className='fallback';$('capture').disabled=true;console.error(e)}connect();
(async()=>{try{await loadArticles();if(requestedArticle){if(!/^[a-f0-9]{16}$/.test(requestedArticle)||!approved.some(b=>b.article.id===requestedArticle)){$('message').textContent='연결한 승인 기사를 사용할 수 없습니다. 삭제·승인 상태를 확인하세요.';return}$('article').value=requestedArticle;await $('article').onchange()}else syncStudioLinks()}catch{$('message').textContent='승인 기사 목록을 불러오지 못했습니다. 다시 시도하세요.'}})();
// Approval revocations are checked without silently continuing an old script.
setInterval(async()=>{await loadArticles();if(currentBundle&&!approved.some(b=>b.article.id===currentBundle.article.id)){window.speechSynthesis?.cancel();currentBundle=null;$('script').textContent='기사 승인이 변경되어 표시를 중단했습니다.';$('message').textContent='승인 철회 또는 근거 변경을 확인해 주세요.';connect()}},10000);
