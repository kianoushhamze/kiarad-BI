"use client";

import { useEffect, useState } from "react";
import { CustomerFile } from "./customer-file";
import { DataEntryLink } from "../../components/data-entry-link";
import { PortalShell } from "../../components/portal-shell";
import { authFetch, secureApi } from "../../lib/secure-api";
import { PublicRegistryReview } from "../../components/public-registry-review";

type Customer = {
  id: number;
  code?: string | null;
  name: string;
  city?: string | null;
  phone?: string | null;
  customer_type?: string | null;
  province_area?: string | null;
};

export default function CustomersPage() {
  const [selected, setSelected] = useState<number | null>(null);
  const [items, setItems] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<number|null>(null);
  const [canManage, setCanManage] = useState(false);
  useEffect(()=>{
    let active=true;
    secureApi<{role:string}>("/auth/me").then(user=>{if(active)setCanManage(["ceo","sales_manager"].includes(user.role));}).catch(()=>{});
    return()=>{active=false;};
  },[]);
  async function removeCustomer(customer:Customer){
    if(deleting||!window.confirm(`مشتری «${customer.name}» حذف شود؟ در صورت داشتن سابقهٔ مرتبط، حذف متوقف می‌شود.`))return;
    setDeleting(customer.id);
    try{
      await secureApi(`/kerman/coach/public-registry/customers/${customer.id}`,{method:"DELETE"});
      setItems(rows=>rows.filter(row=>row.id!==customer.id));setError("");
    }catch(reason){setError(reason instanceof Error?reason.message:"حذف انجام نشد.");}
    finally{setDeleting(null);}
  }

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setLoading(true);
      const suffix = appliedQuery ? `?q=${encodeURIComponent(appliedQuery)}` : "";
      return authFetch("/directory/customers" + suffix)
        .then(async (response) => {
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || "دریافت اطلاعات مشتریان ناموفق بود.");
          return data;
        })
        .then((data) => { if (active) { setItems(Array.isArray(data) ? data : []); setError(""); } })
        .catch((reason) => { if (active) { setItems([]); setError(reason instanceof Error ? reason.message : "خطای دریافت اطلاعات"); } })
        .finally(() => { if (active) setLoading(false); });
    });
    return () => { active = false; };
  }, [appliedQuery]);

  return (
    <PortalShell title="اطلاعات مشتریان" eyebrow="مشتریان و پیگیری فروش">
      {selected !== null ? <CustomerFile key={selected} id={selected} onClose={() => setSelected(null)}
        onUpdate={contact => { if (contact) setItems(rows => rows.map(row => row.id === selected ? {...row, ...contact} : row)); }} />
      : <div className="kskin space-y-4"><details><summary>افزودن مشتری و ورود گروهی</summary><DataEntryLink entity="customers"/>
        <PublicRegistryReview/></details>
        <section className="rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-56 flex-1 text-[11px] text-slate-400">
              جست‌وجو با بخشی از نام، شهر، شماره یا کد مشتری؛ ترتیب واژه‌ها مهم نیست
              <input aria-label="جست‌وجوی مشتریان" maxLength={100} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") setAppliedQuery(query.trim()); }} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-white outline-none focus:border-violet-400/50" />
            </label>
            <button type="button" onClick={() => setAppliedQuery(query.trim())} className="rounded-xl bg-violet-600 px-4 py-2.5 text-xs font-bold text-white">جست‌وجو</button>
            <button type="button" onClick={() => { setQuery(""); setAppliedQuery(""); }} className="rounded-xl border border-white/10 px-4 py-2.5 text-xs text-slate-300">پاک‌کردن</button>
          </div>
        </section>

        <section className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f1222]">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
            <b className="text-sm text-white">فهرست مشتریان</b>
            <span className="text-[10px] text-slate-500">{items.length} مشتری</span>
          </div>
          {loading ? <div className="p-10 text-center text-xs text-slate-500">در حال دریافت اطلاعات…</div> : null}
          {error ? <div className="p-6 text-center text-xs text-rose-300">{error}</div> : null}
          {!loading && !error && items.length === 0 ? <div className="p-10 text-center text-xs text-slate-500">مشتری‌ای پیدا نشد.</div> : null}
          {items.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-right text-xs">
                <thead className="bg-white/[0.025] text-slate-500"><tr><th className="px-4 py-3">نام</th><th className="px-4 py-3">نوع</th><th className="px-4 py-3">شهر / منطقه</th><th className="px-4 py-3">شماره تماس</th><th className="px-4 py-3">کد</th></tr></thead>
                <tbody>{items.map((customer) => (
                  <tr key={customer.id} className="border-t border-white/[0.05] text-slate-300">
                    <td className="px-4 py-3 font-bold text-white"><button type="button" className="text-right text-violet-300 hover:underline" onClick={() => setSelected(customer.id)}>{customer.name}</button></td>
                    <td className="px-4 py-3">{customer.customer_type || "—"}</td>
                    <td className="px-4 py-3">{[customer.city, customer.province_area].filter(Boolean).join("، ") || "—"}</td>
                    <td className="px-4 py-3" dir="ltr">{customer.phone || "—"}</td>
                    <td className="px-4 py-3">{customer.code || "—"}{canManage&&customer.code?.startsWith("PUBLIC-")&&<button type="button" disabled={deleting!==null} onClick={()=>void removeCustomer(customer)} className="mr-3 text-rose-300">{deleting===customer.id?"در حال حذف…":"حذف مشتری افزوده‌شده"}</button>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>}
    </PortalShell>
  );
}
