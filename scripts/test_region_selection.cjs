const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync('election-news-server/dashboard.js','utf8');
const elements={dataMode:{value:'demo'},region:{value:'',innerHTML:''}};
const context=vm.createContext({document:{getElementById:id=>elements[id]}});
vm.runInContext(source.slice(0,source.indexOf('const showValue=')) + source.slice(source.indexOf('function refreshRegionOptions(){'),source.indexOf('async function loadRegionChoices(){')) + `
let changed=0,tabled=0;
function table(){tabled++}
$('dataMode').onchange=()=>{changed++;refreshRegionOptions()};
snap={rows:[{region_name:'계양구을'}]};officialRegions=['계양구갑','계양구을','연수구을'];
refreshRegionOptions();
`,context);
assert.equal(elements.region.value,'');
assert.match(elements.region.innerHTML,/계양구갑 · 2024년 실제 결과/);
assert.equal(vm.runInContext('selectedRegion()',context),'계양구을');
elements.region.value='연수구을';vm.runInContext('chooseRegion()',context);
assert.equal(elements.dataMode.value,'official');assert.equal(elements.region.value,'연수구을');
assert.equal(vm.runInContext('selectedRegion()',context),'연수구을');
vm.runInContext('refreshRegionOptions()',context);assert.equal(elements.region.value,'연수구을');
elements.region.value='계양구갑';vm.runInContext('chooseRegion()',context);
assert.equal(vm.runInContext('tabled',context),1);
elements.region.value='';vm.runInContext('chooseRegion()',context);
assert.equal(elements.dataMode.value,'demo');assert.equal(elements.region.value,'');
assert.equal(vm.runInContext('changed',context),2);
console.log('Verified default virtual candidates, district switch, stable official selection and return to simulation');
