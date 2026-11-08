"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authFetch, secureApi, type SessionUser } from "../../lib/secure-api";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { formatIranDateTime } from "../../lib/iran-date";
import { microphoneErrorMessage } from "../../lib/voice-errors";

type Draft={submission_key:string;raw_text:string;customer_id?:number | null;customer_name:string;summary:string;followup_task:string;visits_count:number;orders_count:number;reported_sales_amount:number;reported_collections_amount:number};
type Customer={id:number;name:string;city?:string};
type Person={id:number;full_name:string;salesperson_id?:number | null};
type Report={id:number;salesperson_name:string;customer_name:string;summary:string;raw_text:string;task_id?:number;created_at:string};
type SpeechStatus={state:string;conversion_verified?:boolean;public_sample_quality_warning?:boolean};
const MAX_AUDIO=10*1024*1024;
function speechMessage(status:SpeechStatus | null){
  if(status?.public_sample_quality_warning || status?.state==="quality_rejected")return "مدل در یک نمونهٔ عمومی فارسی دقت پایینی داشت؛ تبدیل صوت در دسترس است، اما متن هر صوت را پیش از ثبت با دقت بازبینی کنید.";
  if(status?.conversion_verified)return "تبدیل صوت در این نوبت اجرای سرویس موفق بوده است؛ متن هر گزارش را پیش از ثبت بررسی کنید.";
  const messages:Record<string,string>={
    local_files_present:"فایل‌های مدل محلی آماده‌اند؛ تبدیل با نخستین فایل صوتی بررسی می‌شود.",
    loaded:"مدل محلی بارگذاری شده است؛ برای بررسی تبدیل، یک صوت کوتاه انتخاب کنید.",
    local_files_missing:"فایل‌های مدل صوتی کامل نیستند؛ فعلاً گزارش را متنی وارد کنید.",
    dependency_missing:"موتور تبدیل گفتار نصب نیست؛ فعلاً گزارش را متنی وارد کنید.",
    load_failed:"بارگذاری مدل صوتی موفق نبود؛ مدیر باید مدل و سرویس را بررسی کند. ورود متن فعال است.",
    cache_not_verified:"آمادگی مدل محلی هنوز تأیید نشده است؛ می‌توانید یک صوت کوتاه را امتحان کنید یا متن بنویسید.",
  };
  return status ? messages[status.state] || "وضعیت مدل صوتی نیاز به بررسی دارد؛ ورود متن فعال است." : "وضعیت مدل صوتی هنوز دریافت نشده است؛ ورود متن فعال است.";
}
function key(){
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,value=>value.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
const emptyDraft=():Draft=>({submission_key:key(),raw_text:"",customer_name:"",summary:"",followup_task:"",visits_count:0,orders_count:0,reported_sales_amount:0,reported_collections_amount:0});

export default function VoiceReportPage(){
  const [user,setUser]=useState<SessionUser | null>(null);
  const [people,setPeople]=useState<Person[]>([]);
  const [person,setPerson]=useState("");
  const [customers,setCustomers]=useState<Customer[]>([]);
  const [draft,setDraft]=useState<Draft | null>(null);
  const [recording,setRecording]=useState(false);
  const [requesting,setRequesting]=useState(false);
  const [busy,setBusy]=useState(false);
  const [seconds,setSeconds]=useState(0);
  const [audioUrl,setAudioUrl]=useState("");
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [history,setHistory]=useState<Report[]>([]);
  const [historyError,setHistoryError]=useState("");
  const [historyLoading,setHistoryLoading]=useState(true);
  const [speech,setSpeech]=useState<SpeechStatus | null>(null);
  const [speechLoading,setSpeechLoading]=useState(true);
  const [speechError,setSpeechError]=useState("");
  const recorder=useRef<MediaRecorder | null>(null);
  const stream=useRef<MediaStream | null>(null);
  const chunks=useRef<Blob[]>([]);
  const blob=useRef<Blob | null>(null);
  const url=useRef("");
  const timer=useRef<ReturnType<typeof setInterval> | null>(null);
  const mounted=useRef(true);
  const working=useRef(false);
  const manager=!!user && ["ceo","sales_manager"].includes(user.role);
  const speechBlocked=speechLoading || ["dependency_missing","local_files_missing","load_failed"].includes(speech?.state || "");
  const target=people.find(item=>String(item.id)===person);
  const loadHistory=async()=>{
    setHistoryLoading(true);setHistoryError("");
    try{const result=await secureApi<{items:Report[]}>("/operations/voice-reports");if(mounted.current)setHistory(result.items);}
    catch(reason){if(mounted.current)setHistoryError(reason instanceof Error ? reason.message : "دریافت سوابق ناموفق بود.");}
    finally{if(mounted.current)setHistoryLoading(false);}
  };
  const refreshSpeech=async()=>{
    if(!mounted.current)return;setSpeechLoading(true);setSpeechError("");
    try{const result=await secureApi<SpeechStatus>("/operations/speech-readiness");if(mounted.current)setSpeech(result);}
    catch{if(mounted.current)setSpeechError("دریافت وضعیت موتور صوت انجام نشد؛ می‌توانید دوباره بررسی کنید.");}
    finally{if(mounted.current)setSpeechLoading(false);}
  };
  const clearAudio=()=>{if(url.current)URL.revokeObjectURL(url.current);url.current="";blob.current=null;setAudioUrl("");};
  const release=()=>{if(timer.current)clearInterval(timer.current);timer.current=null;stream.current?.getTracks().forEach(track=>track.stop());stream.current=null;};
  useEffect(()=>{
    mounted.current=true;
    void Promise.resolve().then(()=>{if(mounted.current){void loadHistory();void refreshSpeech();}});
    secureApi<SessionUser>("/auth/me").then(async value=>{
      if(!mounted.current)return;setUser(value);
      if(["ceo","sales_manager"].includes(value.role)){
        const result=await secureApi<{users:Person[]}>("/tasks/assignees");
        if(mounted.current)setPeople(result.users.filter(item=>!!item.salesperson_id));
      }
    }).catch(()=>{if(mounted.current)setError("اطلاعات حساب یا فهرست پرسنل دریافت نشد.");});
    secureApi<{items:Customer[]}>("/operations/voice-customers").then(result=>{if(mounted.current)setCustomers(result.items);}).catch(()=>{if(mounted.current)setError("فهرست مشتریان دریافت نشد؛ نام را می‌توانید دستی وارد کنید.");});
    return()=>{mounted.current=false;if(recorder.current){recorder.current.onstop=null;recorder.current.ondataavailable=null;if(recorder.current.state!=="inactive")recorder.current.stop();}release();if(url.current)URL.revokeObjectURL(url.current);};
  },[]);
  const processAudio=async(audio:Blob)=>{
    if(working.current || !mounted.current)return;
    if(!audio.size || audio.size>MAX_AUDIO){setError("صوت باید غیرخالی و حداکثر ۱۰ مگابایت باشد.");return;}
    working.current=true;setBusy(true);setError("");setMessage("در حال تبدیل گفتار به متن…");
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),120000);
    try{
      const form=new FormData();const extension=audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
      form.append("file",audio,`report.${extension}`);
      const response=await authFetch("/operations/transcribe-audio",{method:"POST",body:form,signal:controller.signal});
      const result=await response.json().catch(()=>null);
      if(!response.ok)throw new Error(typeof result?.detail==="string" ? result.detail : `سرویس تبدیل صوت پاسخ ناموفق داد (${response.status.toLocaleString("fa-IR")}).`);
      if(!result || typeof result.raw_text!=="string")throw new Error("پاسخ سرویس تبدیل صوت قابل استفاده نبود؛ دوباره تلاش کنید یا متن را دستی وارد کنید.");
      if(mounted.current){setDraft({...emptyDraft(),...result,submission_key:key(),followup_task:result.followup_task || ""});setMessage("متن و پیشنهاد پیگیری را بررسی کنید؛ تعدادها و مبلغ‌ها را خودتان وارد کنید.");}
    }catch(reason){if(mounted.current){setMessage("");setError(controller.signal.aborted ? "تبدیل صوت بیش از دو دقیقه طول کشید؛ صوت روی همین صفحه برای تلاش دوباره باقی است. می‌توانید گزارش را متنی وارد کنید." : reason instanceof TypeError ? "ارتباط با سرویس تبدیل صوت برقرار نشد؛ اینترنت و اتصال شبکهٔ خصوصی را بررسی کنید. صوت روی همین صفحه باقی است." : reason instanceof Error ? reason.message : "پردازش صوت ناموفق بود؛ می‌توانید گزارش را متنی وارد کنید.");}}
    finally{clearTimeout(timeout);working.current=false;if(mounted.current){setBusy(false);void refreshSpeech();}}
  };
  const stop=()=>{if(recorder.current?.state==="recording")recorder.current.stop();};
  const start=async()=>{
    if(working.current || recording || requesting || draft || speechBlocked)return;
    if(!window.isSecureContext){setError("ضبط به نشانی امن داشبورد نیاز دارد؛ نشانی امن همین صفحه را در اج یا کروم باز کنید. ورود متن و انتخاب فایل صوتی نیز در دسترس است.");return;}
    if(!navigator.mediaDevices?.getUserMedia){setError("مرورگر فعلی امکان دسترسی به میکروفون را ندارد. اگر صفحه در مرورگر داخلی برنامه باز است، نشانی همین صفحه را در اج یا کروم باز کنید؛ یا فایل صوتی انتخاب کنید و متن بنویسید.");return;}
    if(typeof MediaRecorder==="undefined"){setError("مرورگر قالب ضبط صوت را پشتیبانی نمی‌کند؛ نشانی همین صفحه را در اج یا کروم باز کنید، فایل صوتی انتخاب کنید یا متن را وارد کنید.");return;}
    working.current=true;setRequesting(true);setError("");setMessage("");
    let expired=false;
    let permissionTimer:ReturnType<typeof setTimeout> | undefined;
    try{
      const request=navigator.mediaDevices.getUserMedia({audio:true});
      void request.then(media=>{if(expired || !mounted.current)media.getTracks().forEach(track=>track.stop());},()=>{});
      const media=await Promise.race([request,new Promise<never>((_,reject)=>{permissionTimer=setTimeout(()=>{expired=true;reject(new DOMException("Microphone request timed out","TimeoutError"));},25000);})]);
      clearTimeout(permissionTimer);
      if(!mounted.current){media.getTracks().forEach(track=>track.stop());return;}
      stream.current=media;
      if(!media.getAudioTracks().some(track=>track.readyState==="live"))throw new DOMException("No live audio input","NotReadableError");
      const mime=typeof MediaRecorder.isTypeSupported==="function" ? ["audio/webm;codecs=opus","audio/mp4","audio/ogg;codecs=opus"].find(type=>MediaRecorder.isTypeSupported(type)) : undefined;
      const active=new MediaRecorder(media,mime ? {mimeType:mime} : undefined);recorder.current=active;chunks.current=[];clearAudio();setSeconds(0);
      let size=0;
      active.ondataavailable=event=>{if(event.data.size){chunks.current.push(event.data);size+=event.data.size;if(size>MAX_AUDIO && active.state==="recording")active.stop();}};
      active.onerror=event=>{active.onstop=null;if(active.state!=="inactive")active.stop();release();working.current=false;if(mounted.current){setRecording(false);setRequesting(false);const failure=(event as Event & {error?:DOMException}).error;setError(failure ? microphoneErrorMessage(failure) : "هنگام ضبط خطای دستگاه رخ داد؛ میکروفون را بررسی کنید یا فایل صوتی انتخاب کنید.");}};
      active.onstop=()=>{release();setRecording(false);working.current=false;if(!mounted.current)return;
        const audio=new Blob(chunks.current,{type:active.mimeType || chunks.current[0]?.type || "audio/webm"});blob.current=audio;url.current=URL.createObjectURL(audio);setAudioUrl(url.current);void processAudio(audio);};
      active.start(1000);setRecording(true);working.current=false;
      let elapsed=0;timer.current=setInterval(()=>{elapsed+=1;setSeconds(elapsed);if(elapsed>=120)stop();},1000);
    }catch(reason){release();working.current=false;if(mounted.current)setError(microphoneErrorMessage(reason));}
    finally{clearTimeout(permissionTimer);working.current=false;if(mounted.current)setRequesting(false);}
  };
  const upload=async(file?:File)=>{if(!file || working.current || recording || draft)return;if(file.size>MAX_AUDIO || !file.size){setError("فایل باید غیرخالی و حداکثر ۱۰ مگابایت باشد.");return;}clearAudio();blob.current=file;url.current=URL.createObjectURL(file);setAudioUrl(url.current);await processAudio(file);};
  const submit=async()=>{
    if(!draft || working.current)return;
    if(!draft.raw_text.trim() || !draft.summary.trim()){setError("متن و خلاصهٔ گزارش را کامل کنید.");return;}
    if(manager && !target){setError("پرسنل مسئول گزارش را انتخاب کنید.");return;}
    working.current=true;setBusy(true);setError("");setMessage("");
    try{
      const result=await secureApi<{report_id:number;task_created:boolean;replayed:boolean}>("/operations/submit-daily-report",{method:"POST",body:JSON.stringify({...draft,salesperson_id:manager ? target?.salesperson_id : undefined,assigned_user_id:manager ? target?.id : undefined})});
      if(mounted.current){setMessage(`گزارش روزانهٔ ${result.report_id.toLocaleString("fa-IR")} ثبت شد${result.task_created ? " و کار پیگیری به مسئول گزارش تخصیص یافت." : "."}${result.replayed ? " درخواست تکراری بود و دوباره ثبت نشد." : ""}`);setDraft(null);clearAudio();await loadHistory();}
    }catch(reason){if(mounted.current)setError(reason instanceof Error ? reason.message : "ثبت انجام نشد؛ پیش‌نویس برای تلاش دوباره باقی است.");}
    finally{working.current=false;if(mounted.current)setBusy(false);}
  };
  const edit=(field:keyof Draft,value:string | number | null)=>setDraft(current=>current ? {...current,[field]:value} : current);
  return <PortalShell title="گزارش صوتی و متنی" eyebrow="ضبط، بازبینی و ثبت نتیجه">
    <div className="kskin space-y-5" dir="rtl">
      <Surface className="p-5"><h2 className="font-bold text-white">گزارش کار روزانه</h2><p className="mt-3 text-sm leading-7 text-slate-400">حداکثر دو دقیقه ضبط کنید، فایل صوتی انتخاب کنید یا متن بنویسید. گزارش پس از بازبینی شما ثبت می‌شود؛ فایل صوتی در سرور نگهداری نمی‌شود.</p>
        <div className="mt-4 rounded-xl border border-white/10 p-3"><p role="status" className="text-sm leading-7 text-slate-300">{speechLoading ? "در حال بررسی آمادگی تبدیل صوت…" : speechMessage(speech)}</p>{speechError && <p className="mt-2 text-sm text-amber-200">{speechError}</p>}<button type="button" disabled={speechLoading || busy || recording || requesting} onClick={()=>void refreshSpeech()} className="mt-2 text-xs text-violet-300 underline disabled:opacity-40">بررسی دوبارهٔ موتور صوت</button></div>
        {user && !manager && !user.salesperson_id && <p className="mt-3 text-sm text-amber-200">حساب شما باید به پروفایل پرسنل متصل شود تا گزارش ثبت شود.</p>}
        <div className="mt-4 flex flex-wrap gap-3"><button type="button" disabled={busy || requesting || !!draft || (!recording && speechBlocked)} onClick={recording ? stop : start} className={primaryButton}>{requesting ? "دریافت اجازهٔ میکروفون…" : recording ? `توقف ضبط · ${seconds.toLocaleString("fa-IR")} ثانیه` : "شروع ضبط گزارش"}</button><button type="button" disabled={busy || recording || requesting || !!draft} onClick={()=>{setDraft(emptyDraft());setError("");setMessage("");}} className="rounded-xl border border-white/15 px-4 py-2 text-sm text-violet-200 disabled:opacity-40">ورود متن گزارش</button><label className="text-sm text-slate-300">انتخاب فایل صوتی<input aria-label="فایل صوتی گزارش" disabled={busy || recording || requesting || !!draft || speechBlocked} type="file" accept="audio/*" className="mt-2 block max-w-full text-xs" onChange={event=>{void upload(event.target.files?.[0]);event.target.value="";}}/></label></div>
        {audioUrl && <div className="mt-4"><audio controls src={audioUrl} className="w-full"/>{!draft && <button type="button" disabled={busy || recording || requesting} onClick={()=>{if(blob.current)void processAudio(blob.current);}} className="mt-3 text-sm text-violet-300 underline disabled:opacity-40">تلاش دوباره برای تبدیل همین صوت</button>}</div>}
        {error && <p role="alert" className="mt-4 text-sm leading-7 text-rose-300">{error}</p>}{message && <p role="status" className="mt-4 text-sm leading-7 text-emerald-200">{message}</p>}
      </Surface>
      {draft && <Surface className="space-y-4 p-5"><h2 className="font-bold text-white">بازبینی و ثبت گزارش</h2>
        {manager && <label className="block text-sm text-slate-300">پرسنل مسئول<select disabled={busy} value={person} onChange={event=>setPerson(event.target.value)} className={`${fieldClass} mt-2`}><option value="">انتخاب پرسنل متصل به پروفایل</option>{people.map(item=><option key={item.id} value={item.id}>{item.full_name}</option>)}</select>{!people.length && <span className="mt-2 block text-xs text-amber-200">حساب فعال و متصل پرسنل در فهرست موجود نیست.</span>}</label>}
        <label className="block text-sm text-slate-300">متن کامل گزارش<textarea disabled={busy} maxLength={20000} rows={5} value={draft.raw_text} onChange={event=>edit("raw_text",event.target.value)} className={`${fieldClass} mt-2`}/></label>
        <label className="block text-sm text-slate-300">خلاصهٔ نتیجه<textarea disabled={busy} maxLength={5000} rows={3} value={draft.summary} onChange={event=>edit("summary",event.target.value)} className={`${fieldClass} mt-2`}/></label>
        <label className="block text-sm text-slate-300">مشتری<select disabled={busy} value={draft.customer_id || ""} onChange={event=>{const customer=customers.find(item=>item.id===Number(event.target.value));setDraft(current=>current ? {...current,customer_id:customer?.id || null,customer_name:customer?.name || current.customer_name} : current);}} className={`${fieldClass} mt-2`}><option value="">ورود نام مشتری به‌صورت دستی</option>{customers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label>
        <input aria-label="نام مشتری" disabled={busy} maxLength={300} placeholder="نام مشتری یا محل مراجعه" value={draft.customer_name} onChange={event=>setDraft(current=>current ? {...current,customer_id:null,customer_name:event.target.value} : current)} className={fieldClass}/>
        <div className="grid gap-3 sm:grid-cols-2">{([["visits_count","تعداد بازدید"],["orders_count","تعداد سفارش"],["reported_sales_amount","فروش گزارش‌شده (ریال)"],["reported_collections_amount","وصول گزارش‌شده (ریال)"]] as const).map(([field,label])=><label key={field} className="text-sm text-slate-300">{label}<input disabled={busy} type="number" min={0} step={field.endsWith("count") ? 1 : "any"} value={draft[field]} onChange={event=>edit(field,Number(event.target.value))} className={`${fieldClass} mt-2`}/></label>)}</div>
        <p className="text-xs leading-6 text-slate-400">این اعداد گزارش پرسنل‌اند و به‌تنهایی فروش حسابداری یا وصول بانکی محسوب نمی‌شوند.</p>
        <label className="block text-sm text-slate-300">کار پیگیری اختیاری<textarea disabled={busy} maxLength={200} rows={2} placeholder="با خالی‌گذاشتن، کار پیگیری ساخته نمی‌شود" value={draft.followup_task} onChange={event=>edit("followup_task",event.target.value)} className={`${fieldClass} mt-2`}/></label>
        <div className="flex flex-wrap gap-3"><button type="button" onClick={submit} disabled={busy || !user || (!manager && !user.salesperson_id)} className={primaryButton}>{busy ? "در حال ثبت…" : "تأیید و ثبت گزارش"}</button><button type="button" disabled={busy} onClick={()=>{setDraft(null);clearAudio();setError("");setMessage("");}} className="rounded-xl border border-white/15 px-4 py-2 text-sm text-slate-300 disabled:opacity-40">حذف پیش‌نویس و شروع گزارش تازه</button></div>
      </Surface>}
      <Surface className="p-5"><div className="flex flex-wrap justify-between gap-3"><h2 className="font-bold text-white">گزارش‌های ثبت‌شده</h2><button type="button" disabled={historyLoading} onClick={()=>void loadHistory()} className="text-sm text-violet-300 underline">تازه‌سازی</button></div>{historyError && <p role="alert" className="mt-3 text-sm text-rose-300">{historyError}</p>}{historyLoading ? <p className="mt-4 text-sm text-slate-400">در حال دریافت سوابق…</p> : <div className="mt-4 space-y-4">{history.map(report=><article key={report.id} className="rounded-xl border border-white/10 p-4"><h3 className="text-sm text-white">{report.salesperson_name} · {report.customer_name}</h3><p className="mt-2 text-xs text-slate-400">{formatIranDateTime(report.created_at)}</p><p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200">{report.summary}</p><details className="mt-3 text-sm text-slate-300"><summary className="cursor-pointer">متن کامل ثبت‌شده</summary><p className="mt-2 whitespace-pre-wrap leading-7">{report.raw_text}</p></details>{report.task_id && <Link href="/tasks" className="mt-3 inline-block text-sm text-violet-300 underline">مشاهدهٔ کار پیگیری ←</Link>}</article>)}{!history.length && !historyError && <p className="text-sm text-slate-400">هنوز گزارشی ثبت نشده است.</p>}</div>}</Surface>
    </div>
  </PortalShell>;
}
