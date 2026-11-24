// Execute the actual page script with an in-memory DOM to check review controls.
// This checks logic; it is not a rendered-browser or accessibility certification.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const html=fs.readFileSync(path.join(root,'election-news-server/index.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements=new Map();
const element=id=>{
  if(!elements.has(id)) elements.set(id,{value:'',checked:false,disabled:false,options:[],listeners:{},style:{},addEventListener(event,fn){this.listeners[event]=fn;},children:[],appendChild(child){this.children.push(child)}});
  return elements.get(id);
};
const sandbox={document:{getElementById:element,createElement:()=>({})},location:{protocol:'http:',host:'127.0.0.1:8102'},WebSocket:class{},setTimeout(){},URLSearchParams,URL,Blob,console};
vm.createContext(sandbox);
vm.runInContext(script,sandbox);
const checks=[];
function check(name,code){vm.runInContext(code,sandbox);checks.push({name,passed:true});}
sandbox.assert=assert;
check('New article requires explicit manual review', `
  const a={id:'UI-1',title:'TEST',author:'TEST-writer',mode:'demo',sentences:[],status:'PENDING_HUMAN',validation:{rule:'PASS',disagreement:false},ai_review:{verdict:'UNAVAILABLE'}};
  show(a); assert.equal($('approve').disabled,true);
  $('checked').checked=true; $('aiAck').checked=true; $('reason').value='근거 직접 확인'; syncApproval();
  assert.equal($('approve').disabled,false);
`);
check('Rule failure cannot enable approval', `
  current.validation.rule='FAIL'; syncApproval(); assert.equal($('approve').disabled,true);
  current.validation.rule='PASS'; current.validation.disagreement=true; syncApproval(); assert.equal($('approve').disabled,true);
`);
check('Switching article clears confirmations', `
  show({...a,id:'UI-2'}); assert.equal($('checked').checked,false); assert.equal($('aiAck').checked,false); assert.equal($('reason').value,'');
`);
check('Changing account clears review confirmations', `
  $('checked').checked=true; $('aiAck').checked=true; $('reason').value='근거 직접 확인'; resetReviewConfirmation();
  assert.equal($('checked').checked,false); assert.equal($('approve').disabled,true);
`);
check('Unavailable values are never printed as zero or null', `
  assert.equal(showValue(null,'%'),'미제공'); assert.equal(showValue(0,'%'),'0%');
`);
check('Review badges show actual validation and AI disagreement', `
  show({...a,id:'UI-3',status:'REVIEW_REQUIRED',validation:{rule:'FAIL',errors:['S1:VOTES_MISMATCH'],disagreement:true}});
  assert.equal($('ruleBadge').textContent,'검토 필요');
  assert.equal($('aiBadge').textContent,'규칙·AI 판정 불일치');
  assert.equal($('checkErrors').hidden,false);
  assert.equal($('approve').disabled,true);
`);
check('Unsafe evidence URLs never become clickable sources', `
  assert.equal(safeSource('javascript:alert(1)'),null);
  assert.equal(safeSource('demo://fixtures/pledges'),null);
  assert.equal(safeSource('https://www.data.go.kr/'),'https://www.data.go.kr/');
`);
check('Official catalogue locations never masquerade as pledge evidence', `
  const context={region_name:'계양구갑',candidate_name:'TEST',registered_documents:0,active_chunks:0,approved_documents:0,document_states:{},directory:{title:'TEST 공보',publication_year:2024,publisher:'선관위',catalog_provider:'국회도서관',source_url:'https://dl.nanet.go.kr/detail/TEST',original_portal_url:'https://library.nec.go.kr/',policy_url:'https://policy.nec.go.kr/',source_id:'TEST-INDEX',location:'목차 193쪽'}};
  const result=renderEvidence([],context,'교통 주거');
  assert.ok(result.includes('공약 내용의 증거가 아닙니다'));
  assert.ok(result.includes('현재 보유 자료에는 이 후보의 공약 본문이 없습니다'));
  assert.ok(result.includes('목차 193쪽'));
  assert.ok(!result.includes('근거 ID <b>TEST-INDEX'));
  const demoCard=renderEvidence([{title:'<script>unsafe</script>',text:'TEST',id:'TEST-CHUNK',document_id:'doc',is_demo:true}],{...context,directory:null},'');
  assert.ok(!demoCard.includes('<script>unsafe</script>'));
  assert.ok(demoCard.includes('시뮬레이션 문서'));
`);
check('Promotional material browsing needs no new document registration', `
 const materialContext={region_name:'계양구갑',candidate_name:'TEST',registered_documents:1,active_chunks:1,approved_documents:0,document_states:{doc:'REVIEW_REQUIRED'},directory:{title:'TEST 홍보물',publication_year:2024,publisher:'선관위',catalog_provider:'국회도서관',source_url:'https://dl.nanet.go.kr/detail/TEST',original_portal_url:'https://library.nec.go.kr/',policy_url:'https://policy.nec.go.kr/',source_id:'TEST-INDEX',location:'목차 193쪽',catalog_start_page:193}};
 const materials=[{title:'TEST 기존 자료',text:'TEST 기존 본문',id:'TEST-REF',document_id:'doc',is_demo:false,url:'https://library.nec.go.kr/'}];
 const publicView=renderEvidence(materials,materialContext,'교통','publications');
 assert.ok(publicView.includes('선관위 홍보물 찾아보기'));
 assert.ok(publicView.includes('193쪽'));
 assert.ok(!publicView.includes('TEST 기존 본문'));
 assert.ok(!publicView.includes('공약 원문 등록'));
 const existingView=renderEvidence(materials,materialContext,'교통','existing');
 assert.ok(existingView.includes('TEST 기존 본문'));
 assert.ok(existingView.includes('독립 검수 필요'));
 assert.ok(!existingView.includes('선관위 홍보물 찾아보기'));
`);
assert.ok(!html.includes('id="token"'));
assert.ok(!script.includes("$('token')"));
const calls=[];let connected=false;
sandbox.fetch=async(url,options)=>{
 calls.push({url,options});
 const writer={name:'local-writer',role:'writer'};
 const draft={id:'UI-SESSION-DRAFT',title:'TEST 생성 기사',author:'local-writer',mode:'official',sentences:[],status:'DRAFT',ai_review:{verdict:'UNAVAILABLE'}};
 if(url==='/api/me')return {ok:connected,status:connected?200:401,json:async()=>connected?writer:{detail:'login required'}};
 if(url==='/api/capabilities')return {ok:true,json:async()=>({local_writer_available:true})};
 if(url==='/api/session/local-writer'){connected=true;return {ok:true,json:async()=>writer}};
 if(url==='/api/articles')return {ok:true,json:async()=>options.method==='POST'?draft:[draft,{...draft,id:'UI-DEMO',mode:'demo'}]};
 throw Error('Unexpected URL '+url);
};
await vm.runInContext(`(async()=>{$('region').value='계양구갑';$('dataMode').value='official';await $('draft').onclick();assert.equal(current.id,'UI-SESSION-DRAFT');assert.equal($('draft').disabled,false);await $('list').onclick();assert.equal($('articles').children.length,1);assert.ok($('draftMessage').textContent.includes('기사 1건'));})()`,sandbox);
assert.ok(calls.some(call=>call.url==='/api/session/local-writer'));
assert.ok(calls.every(call=>call.options.credentials==='same-origin'&&!('Authorization' in call.options.headers)));
checks.push({name:'Token-free buttons establish writer session, create and list scoped articles',passed:true});
fs.mkdirSync(path.join(root,'outputs'),{recursive:true});
fs.writeFileSync(path.join(root,'outputs/ui_logic_results.json'),JSON.stringify({at:new Date().toISOString(),method:'Node VM with DOM stubs; no rendered browser',total:checks.length,passed:checks.length,checks},null,2));
console.log(`${checks.length} UI logic checks passed`);
