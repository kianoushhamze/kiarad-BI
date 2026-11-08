// Read-only UI smoke test using a separate Chrome/Edge profile on this PC.
// No npm dependencies, no screenshots, no real orders or messages.
import {spawn, execFileSync} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const base='http://127.0.0.1:3000';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const candidates=[process.env.KIARAD_QA_BROWSER,
 path.join(process.env.PROGRAMFILES??'', 'Google/Chrome/Application/chrome.exe'),
 path.join(process.env['PROGRAMFILES(X86)']??'', 'Microsoft/Edge/Application/msedge.exe'),
 path.join(process.env.PROGRAMFILES??'', 'Microsoft/Edge/Application/msedge.exe'),
 path.join(process.env.LOCALAPPDATA??'', 'Google/Chrome/Application/chrome.exe')].filter(Boolean);
const browserPath=candidates.find(existsSync);
if(!browserPath || typeof WebSocket==='undefined'){
 console.log(JSON.stringify({status:'blocked',reason:'Chrome/Edge executable and Node WebSocket are required'}));
 process.exit(2);
}
const profile=mkdtempSync(path.join(tmpdir(),'kiarad-ui-review-'));
let child,ws;
const results=[];
try {
 const python=path.join(root,'.venv','Scripts','python.exe');
 // Token is transferred only through a private child-process pipe; never logged
 // or saved in the report. The isolated browser profile is deleted on exit.
 const code=`import json\nfrom pathlib import Path\nfrom dotenv import load_dotenv\nload_dotenv(Path('.env'),override=True)\nfrom db import engine\nfrom operations import create_token\nfrom sqlalchemy import text\nwith engine.connect() as conn:\n rows=conn.execute(text("SELECT id,username,full_name,role,salesperson_id,password_version FROM users WHERE is_active=1 AND role='ceo' ORDER BY id LIMIT 1")).mappings().all()\nprint(json.dumps([dict(token=create_token(dict(r)),user=dict(r)) for r in rows]))`;
 const sessions=JSON.parse(execFileSync(python,['-c',code],{cwd:root,stdio:['ignore','pipe','pipe'],timeout:15000}).toString());
 if(!sessions.length) throw new Error('no_active_ceo');
 const session=sessions[0];
 child=spawn(browserPath,['--headless=new','--remote-debugging-port=0',`--user-data-dir=${profile}`,
  '--no-first-run','--no-default-browser-check','--disable-extensions','about:blank'],{stdio:'ignore'});
 let lines;
 for(let n=0;n<100;n++){
  try{lines=readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').trim().split(/\r?\n/);break;}catch{await delay(100);}
 }
 if(!lines) throw new Error('browser_startup_failed');
 ws=new WebSocket(`ws://127.0.0.1:${lines[0]}${lines[1]}`);
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 let nextId=0,errorCount=0;const pending=new Map();
 ws.addEventListener('message',event=>{
  const message=JSON.parse(event.data.toString());
  if(message.method==='Runtime.exceptionThrown') errorCount++;
  if(message.id && pending.has(message.id)){
   const entry=pending.get(message.id);pending.delete(message.id);clearTimeout(entry.timer);
   if(message.error) entry.reject(new Error('cdp_command_failed')); else entry.resolve(message.result);
  }
 });
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
  const id=++nextId; const timer=setTimeout(()=>{pending.delete(id);reject(new Error('cdp_timeout'));},25000);
  pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
 });
 const {browserContextId}=await send('Target.createBrowserContext',{disposeOnDetach:true});
 const {targetId}=await send('Target.createTarget',{url:'about:blank',browserContextId});
 const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
 const cmd=(method,params={})=>send(method,params,sessionId);
 await cmd('Page.enable');await cmd('Runtime.enable');
 const evalJS=async expression=>{
  const value=await cmd('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(value.exceptionDetails) throw new Error('page_evaluation_failed');return value.result.value;
 };
 const waitFor=async expression=>{for(let n=0;n<80;n++){if(await evalJS(expression))return;await delay(250);}throw new Error('page_ready_timeout');};
 const injection=`if(location.origin===${JSON.stringify(base)}){localStorage.setItem('kiarad_access_token',${JSON.stringify(session.token)});localStorage.setItem('kiarad_session_user',${JSON.stringify(JSON.stringify(session.user))});}`;
 const {identifier}=await cmd('Page.addScriptToEvaluateOnNewDocument',{source:injection});
 const pages=['/management','/customers','/catalog','/proformas','/treasury','/monthly-plans','/my-plan','/visitors','/team-chat','/site-cms','/platforms','/marketing','/assistant-automations','/account'];
 for(const width of [1440,390]){
  await cmd('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<500});
  for(const route of pages){
   const previous=errorCount;
   await cmd('Page.navigate',{url:base+route});
   try {
    await waitFor(`location.pathname===${JSON.stringify(route)} && document.readyState==='complete' && !!document.querySelector('main')`);
    await delay(600);
    const layout=await evalJS(`({horizontalOverflow:document.documentElement.scrollWidth>innerWidth+4,hasMain:!!document.querySelector('main')})`);
    results.push({route,width,status:errorCount!==previous?'runtime_error':layout.horizontalOverflow?'layout_overflow':'rendered',...layout});
   } catch {results.push({route,width,status:'not_ready_or_redirected'});}
  }
 }
 // Exercise the command palette without modifying business records.
 await cmd('Input.dispatchKeyEvent',{type:'keyDown',modifiers:2,key:'k',code:'KeyK',windowsVirtualKeyCode:75});
 await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'k',code:'KeyK',windowsVirtualKeyCode:75});
 await waitFor(`!!document.querySelector('[role="dialog"] input')`);
 await cmd('Input.insertText',{text:'حساب'});
 await waitFor(`Array.from(document.querySelectorAll('[role="dialog"] button')).some(x=>x.textContent.includes('حساب من'))`);
 const rect=await evalJS(`(()=>{const b=Array.from(document.querySelectorAll('[role="dialog"] button')).find(x=>x.textContent.includes('حساب من'));const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()`);
 await cmd('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...rect});
 await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...rect});
 await waitFor(`location.pathname==='/account' && !document.querySelector('[role="dialog"]')`);
 results.push({scenario:'command_palette_search_and_click',status:'passed'});
 await cmd('Page.removeScriptToEvaluateOnNewDocument',{identifier});
 await evalJS(`localStorage.removeItem('kiarad_access_token');localStorage.removeItem('kiarad_session_user');true`);
 await cmd('Page.navigate',{url:base+'/account'});
 await waitFor(`location.pathname==='/login'`);
 results.push({scenario:'anonymous_redirect',status:'passed'});
 const passed=results.every(row=>row.status==='rendered'||row.status==='passed');
 console.log(JSON.stringify({status:passed?'passed':'needs_review',scope:'read-only running-build UI smoke; no data mutations',results},null,2));
 process.exitCode=passed?0:1;
} catch {
 console.log(JSON.stringify({status:'blocked',reason:'Local browser/API/DB setup failed; no tokens included',results},null,2));
 process.exitCode=2;
} finally {
 if(ws) ws.close();
 if(child){child.kill();await delay(500);}
 try{rmSync(profile,{recursive:true,force:true});}catch{}
}
