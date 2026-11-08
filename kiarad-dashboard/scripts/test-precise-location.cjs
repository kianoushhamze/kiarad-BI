const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../lib/precise-location.ts'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
let checks=0;const eq=(a,b)=>{assert.equal(a,b);checks++;};
function fixture(){
 let now=100000,success,failure,cleared=0,timer;const testModule={exports:{}};
 const geo={watchPosition:(s,f,o)=>{success=s;failure=f;eq(o.enableHighAccuracy,true);eq(o.maximumAge,0);return 7;},clearWatch:id=>{eq(id,7);cleared++;}};
 vm.runInNewContext(code,{module:testModule,exports:testModule.exports,navigator:{geolocation:geo},Date:class extends Date{static now(){return now;}},DOMException,
 setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{timer=null;}});
 return {api:testModule.exports,point:(accuracy,extra={})=>({coords:{latitude:30,longitude:57,accuracy,...extra},timestamp:now}),
  emit:p=>success(p),error:code=>failure({code}),expire:()=>{now+=30000;timer?.();},cleared:()=>cleared,geo};
}
async function main(){
 let f=fixture(),p=f.api.acquireBestPosition(),point=f.point(.8);f.emit(point);eq(await p,point);eq(f.cleared(),1);
 f=fixture();p=f.api.acquireBestPosition();const best=f.point(5);f.emit(f.point(80));f.emit(best);f.emit(f.point(15));f.expire();eq(await p,best);eq(best.coords.accuracy,5);eq(f.cleared(),1);
 f=fixture();p=f.api.acquireBestPosition().catch(e=>e);f.emit({...f.point(.5),timestamp:1});f.emit(f.point(0));f.emit(f.point(NaN));f.emit(f.point(.5,{latitude:91}));f.expire();eq((await p).code,3);eq(f.cleared(),1);
 f=fixture();p=f.api.acquireBestPosition().catch(e=>e);f.error(1);eq((await p).code,1);eq(f.cleared(),1);
 f=fixture();const controller=new AbortController();p=f.api.acquireBestPosition({signal:controller.signal}).catch(e=>e);controller.abort();eq((await p).name,'AbortError');eq(f.cleared(),1);
 f=fixture();f.geo.watchPosition=()=>{throw new Error('synthetic');};eq((await f.api.acquireBestPosition().catch(e=>e)).code,2);
 f=fixture();p=f.api.acquireBestPosition();point=f.point(.9);f.emit(point);await p;f.emit(f.point(.1));eq(point.coords.accuracy,.9);eq(f.cleared(),1);
 console.log(JSON.stringify({checks,passed:true,real_location_used:false,network:false}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
