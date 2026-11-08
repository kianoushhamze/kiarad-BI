"use client";

import { useEffect, useState, type FormEvent } from "react";
import { secureApi } from "../lib/secure-api";
import { IranDateInput } from "./IranDateInput";
import { iranDateInputToIso } from "../lib/iran-date";
import { fieldClass, primaryButton } from "./portal-shell";

type Assignee = {id:number;full_name?:string;username?:string;is_active?:boolean|number};

export function AssistantActionReview({ answer }: {answer:string}) {
  const [people,setPeople]=useState<Assignee[]>([]);
  const [message,setMessage]=useState("");
  const [saving,setSaving]=useState(false);
  const [saved,setSaved]=useState(false);
  useEffect(()=>{
    let active=true;
    secureApi<Assignee[]|{users:Assignee[]}>("/users").then(data=>{
      if(active)setPeople((Array.isArray(data)?data:data.users||[]).filter(person=>person.is_active));
    }).catch(()=>{if(active)setMessage("دریافت مسئولان انجام نشد؛ صفحه را تازه کنید.");});
    return ()=>{active=false;};
  },[]);
  const submit=async(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(saving||saved)return;
    const form=new FormData(event.currentTarget);
    setSaving(true);setMessage("");
    try {
      const due=String(form.get("due_date")||"");
      await secureApi("/tasks",{method:"POST",body:JSON.stringify({
        title:String(form.get("title")||"").trim(),description:answer,
        priority:"normal",assigned_to:Number(form.get("assigned_to")),customer_id:null,
        due_date:due?iranDateInputToIso(due):null,
      })});
      setSaved(true);setMessage("وظیفه ثبت شد؛ از بخش کارها قابل پیگیری است.");
    } catch(error) {setMessage(error instanceof Error?error.message:"ثبت وظیفه انجام نشد.");}
    finally{setSaving(false);}
  };
  return <details className="mt-4 rounded-xl border border-violet-400/20 bg-violet-500/5 p-4 text-xs">
    <summary className="cursor-pointer font-bold text-violet-200">بازبینی و تبدیل این پاسخ به وظیفه</summary>
    <p className="my-3 leading-6 text-slate-400">متن پاسخ، شرح وظیفه می‌شود. عنوان، مسئول و موعد را مشخص کنید و پس از بررسی تأیید کنید.</p>
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <label>عنوان وظیفه<input name="title" required maxLength={200} className={fieldClass} disabled={saved}/></label>
      <label>مسئول<select name="assigned_to" required className={fieldClass} defaultValue="" disabled={saved}>
        <option value="" disabled>انتخاب مسئول</option>{people.map(person=><option key={person.id} value={person.id}>{person.full_name||person.username}</option>)}
      </select></label>
      <label>موعد شمسی ـ اختیاری<IranDateInput name="due_date" className={fieldClass}/></label>
      <button className={primaryButton} disabled={saving||saved||!people.length}>{saved?"ثبت شد":saving?"در حال ثبت…":"تأیید و ایجاد وظیفه"}</button>
    </form>
    {message&&<p role="status" className="mt-3 leading-6 text-amber-200">{message}</p>}
  </details>;
}
