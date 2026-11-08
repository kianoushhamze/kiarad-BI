const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const source=fs.readFileSync(require('node:path').join(__dirname,'../lib/pending-submission.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const mod={exports:{}};vm.runInNewContext(code,{module:mod,exports:mod.exports});
let keys=0,checks=0;const eq=(a,b)=>{assert.equal(a,b);checks++;};
const queue=new mod.exports.PendingSubmission(()=>String(++keys));
const original={lat:30,report:'synthetic'};
const first=queue.prepare('base-one',original);original.lat=31;
eq(first.payload.lat,30);eq(queue.get('base-one').key,'1');
// Lost response: retry must retain the original body, including measured location.
const retry=queue.prepare('base-one',{lat:32});eq(retry,first);eq(retry.payload.lat,30);eq(keys,1);
queue.clear('foreign');eq(queue.get('base-one'),first);
const changed=queue.prepare('base-two',{lat:33});eq(changed.key,'2');eq(queue.get('base-one'),null);
queue.clear(first.key);eq(queue.get('base-two'),changed);
queue.clear(changed.key);eq(queue.get('base-two'),null);
eq(queue.prepare('base-two',{lat:34}).key,'3');
console.log(JSON.stringify({checks,passed:true,offline_storage:false,real_location:false,network:false}));
