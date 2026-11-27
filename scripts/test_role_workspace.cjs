const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const root='election-news-server/static/';
const elements=new Map();function element(id){if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',value:'',innerHTML:'',closest(){return element(id+'-label')}});return elements.get(id)}
const context=vm.createContext({URLSearchParams,document:{body:{dataset:{}},querySelector:s=>element(s),querySelectorAll:()=>[]},window:{addEventListener(){}},$:element,statuses:{},esc:String,wbAction:fn=>fn,api:async()=>[],loggedUser:{role:'admin'},console});
vm.runInContext(fs.readFileSync(root+'newsroom-links.js','utf8'),context);
const links=context.NewsroomLinks;
let target=new URL(links.url('studio',{article:'abcdef0123456789',mode:'demo',region:'하늘도시갑'}),'http://localhost');assert.equal(target.pathname,'/studio');assert.equal(target.searchParams.get('article'),'abcdef0123456789');assert.equal(target.searchParams.get('region'),'하늘도시갑');
target=new URL(links.url('production',{article:'abcdef0123456789',mode:'official',region:'계양구을'}),'http://localhost');assert.equal(target.searchParams.get('production'),'1');assert.equal(target.hash,'#production');assert.equal(target.searchParams.get('mode'),'official');
assert(!links.url('studio',{article:'https://evil.test',mode:'unsafe'}).includes('evil'));
vm.runInContext(fs.readFileSync(root+'role-workspace.js','utf8'),context);
context.applyWorkspace({role:'writer'},'editor');assert.equal(context.document.body.dataset.workspace,'writer');assert.equal(element('editorWorkspace').hidden,true);assert.equal(element('writing').hidden,false);assert.equal(element('approve').hidden,true);assert.equal(element('checked-label').hidden,true);
context.applyWorkspace({role:'editor'},'writer');assert.equal(context.document.body.dataset.workspace,'editor');assert.equal(element('editorWorkspace').hidden,false);assert.equal(element('writing').hidden,true);assert.equal(element('openDocuments').hidden,true);assert.equal(element('approve').hidden,false);
context.applyWorkspace({role:'admin'},'writer');assert.equal(element('writing').hidden,false);context.applyWorkspace({role:'admin'},'approval');assert.equal(element('writing').hidden,true);assert.equal(element('approve').hidden,false);
console.log('Verified writer/editor/admin workspaces and safe article-context links.');
