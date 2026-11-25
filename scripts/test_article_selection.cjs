const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('election-news-server/dashboard.js','utf8');
const context=vm.createContext({});
vm.runInContext(`let mode='official',region='계양구갑',rendered=[],sessions=0,pending;const notice={};const $=()=>notice;const selectedMode=()=>mode,selectedRegion=()=>region;const ensureArticleSession=async()=>{sessions++};const renderArticleButtons=items=>{rendered=items};let api=async()=>[{id:'a',mode:'official',region_name:'계양구갑'},{id:'b',mode:'official',region_name:'연수구을'},{id:'c',mode:'demo',region_name:'계양구갑'}];`+source.slice(source.indexOf('function articleScope(){'),source.indexOf('function resetArticleWorkspace(){')),context);
(async()=>{
 await vm.runInContext('loadSelectedArticles(true)',context);
 assert.equal(vm.runInContext('rendered.map(a=>a.id).join()',context),'a');
 assert.equal(vm.runInContext('sessions',context),1);
 vm.runInContext('api=()=>new Promise(resolve=>{pending=resolve})',context);
 const request=vm.runInContext('loadSelectedArticles()',context);
 vm.runInContext("region='연수구을';pending([{id:'stale',mode:'official',region_name:'계양구갑'}])",context);
 await request;
 assert.equal(vm.runInContext('rendered[0].id',context),'a','late response must not render for another region');
 vm.runInContext("api=async()=>[{id:'b',mode:'official',region_name:'연수구을'}]",context);
 await vm.runInContext('loadSelectedArticles()',context);
 assert.equal(vm.runInContext('rendered[0].id',context),'b');
 console.log('Verified region/mode article filtering, session connection and stale response protection');
})().catch(error=>{console.error(error);process.exitCode=1});
