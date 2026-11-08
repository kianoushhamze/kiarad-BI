"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {getSavedUser} from "../lib/secure-api";
export function DataEntryLink({entity}:{entity:"products"|"customers"|"targets"|"batches"}) {
  const [visible,setVisible]=useState(false);
  useEffect(()=>{let active=true;void Promise.resolve().then(()=>{if(active)setVisible(["ceo","sales_manager","finance"].includes(getSavedUser()?.role||""));});return()=>{active=false;};},[]);
  if(!visible)return null;
  return <Link href={`/data-entry?entity=${entity}`} className="inline-block rounded-xl border border-violet-400/25 px-4 py-2 text-xs text-violet-200">ورود دستی، اکسل و منبع اطلاعات</Link>;
}
