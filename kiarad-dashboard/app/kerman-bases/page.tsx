"use client";
import { useEffect,useState } from "react";
import {secureApi} from "@/lib/secure-api";
import { PortalShell } from "@/components/portal-shell";
import { CrudTable, type CrudColumn } from "@/components/crud-table";
import { BaseCheckIn } from "@/components/base-checkin";
import { BaseProposals } from "@/components/base-proposals";
import { BaseCoach } from "@/components/base-coach";
import { PublicRegistryReview } from "@/components/public-registry-review";

const TABS: { key: string; label: string; columns: CrudColumn[] }[] = [
  {
    key: "pharmacies",
    label: "داروخانه‌ها",
    columns: [
      { key: "name", label: "نام" },
      { key: "city", label: "شهر" },
      { key: "address", label: "آدرس" },
      { key: "phone", label: "تلفن" },
      { key: "type", label: "نوع" },
      { key: "source", label: "منبع" },
    ],
  },
  {
    key: "cosmetics_shops",
    label: "آرایشی و بهداشتی",
    columns: [
      { key: "name", label: "نام" },
      { key: "city", label: "شهر" },
      { key: "address", label: "آدرس" },
      { key: "phone", label: "تلفن" },
      { key: "source", label: "منبع" },
    ],
  },
  {
    key: "kerman_bases_manual",
    label: "دفتر محلی و طرف حساب‌های هلو",
    columns: [
      { key: "name", label: "نام" },
      { key: "city", label: "شهر" },
      { key: "address", label: "آدرس" },
      { key: "phone", label: "تلفن" },
      { key: "type", label: "نوع" },
    ],
  },
];

export default function KermanBasesPage() {
  const [tab, setTab] = useState("pharmacies");
  const [baseRevision,setBaseRevision]=useState(0);
  const [canManage,setCanManage]=useState(false);
  const [canCoach,setCanCoach]=useState(false);
  useEffect(()=>{let active=true;secureApi<{role:string}>("/auth/me").then(u=>{if(active){setCanManage(["ceo","sales_manager"].includes(u.role));setCanCoach(["ceo","sales_manager","salesperson","visitor"].includes(u.role));}}).catch(()=>{});return()=>{active=false;};},[]);
  const current = TABS.find((t) => t.key === tab)!;

  return (
    <PortalShell title="پایگاه‌های کرمان" eyebrow="مدیریت پایگاه‌های تحت پوشش استان">
      <div className="kskin">
        {canManage&&<PublicRegistryReview/>}
        {canCoach && <BaseCoach refreshKey={baseRevision} onImported={()=>setBaseRevision(value=>value+1)} />}
        <BaseCheckIn key={baseRevision} />
        <BaseProposals onApproved={()=>setBaseRevision(value=>value+1)} />
        <div className="mb-4 flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={
                "rounded-lg px-4 py-2 text-xs font-bold " +
                (tab === t.key
                  ? "bg-violet-600 text-white"
                  : "border border-white/10 text-slate-400 hover:bg-white/5")
              }
            >
              {t.label}
            </button>
          ))}
        </div>
        <CrudTable key={`${tab}:${baseRevision}`} table={current.key} title={current.label} columns={current.columns} readOnly={!canManage} />
      </div>
    </PortalShell>
  );
}
