"use client";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { authFetch } from "../lib/secure-api";

export type CrudColumn = {
  key: string;
  label: string;
  type?: "text" | "number" | "boolean";
};

type Row = Record<string, unknown> & { id?: number; _new?: boolean };

function isRow(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type Props = {
  table: string;
  title: string;
  columns: CrudColumn[];
  readOnly?: boolean;
};

export function CrudTable({ table, title, columns, readOnly=false }: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Row | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const url = "/crud/" + table + "?limit=500" + (q ? "&q=" + encodeURIComponent(q) : "");
      const r = await authFetch(url);
      if (!r.ok) {
        setMsg("دریافت اطلاعات جدول ناموفق بود (" + r.status + ").");
        return;
      }
      const data: unknown = await r.json();
      setRows(Array.isArray(data) ? data.filter(isRow) : []);
      setMsg("");
    } catch {
      setMsg("دریافت اطلاعات جدول انجام نشد؛ دوباره تلاش کنید.");
    } finally {
      setLoading(false);
    }
  }, [q, table]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  const openNew = () => {
    if(readOnly)return;
    const empty: Row = { _new: true };
    columns.forEach(c => empty[c.key] = c.type === "number" ? 0 : c.type === "boolean" ? 0 : "");
    setEditing(empty);
  };

  const save = async () => {
    if (!editing || readOnly) return;
    setSaving(true);
    setMsg("");
    try {
      const payload: Record<string, unknown> = {};
      columns.forEach(c => {
        let v: unknown = editing[c.key];
        if (c.type === "number") v = v === "" || v === null ? null : Number(v);
        if (c.type === "boolean") v = v ? 1 : 0;
        payload[c.key] = v;
      });
      const isNew = !!editing._new;
      if (!isNew && typeof editing.id !== "number") {
        setMsg("شناسهٔ ردیف معتبر نیست؛ ذخیره انجام نشد.");
        return;
      }
      const url = isNew ? "/crud/" + table : "/crud/" + table + "/" + editing.id;
      const method = isNew ? "POST" : "PUT";
      const r = await authFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        setMsg("ذخیره شد");
        setEditing(null);
        load();
      } else {
        setMsg("خطا: " + r.status);
      }
    } catch (e: unknown) {
      setMsg("خطا: " + (e instanceof Error ? e.message : ""));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    if(readOnly)return;
    if (!confirm("حذف این ردیف؟")) return;
    try {
      const r = await authFetch("/crud/" + table + "/" + id, { method: "DELETE" });
      if (r.ok) load();
    } catch {}
  };

  const importExcel = async (file: File) => {
    if(readOnly)return;
    const fd = new FormData();
    fd.append("file", file);
    setMsg("در حال ایمپورت...");
    try {
      const r = await authFetch("/import/excel/" + table, { method: "POST", body: fd });
      const data = await r.json();
      setMsg("ایمپورت شد: " + (data.inserted || 0) + " ردیف" + (data.errors?.length ? " — خطا: " + data.errors.length : ""));
      load();
    } catch (e: unknown) {
      setMsg("خطا: " + (e instanceof Error ? e.message : ""));
    }
  };

  const downloadTemplate = async () => {
    setMsg("");
    try {
      const response = await authFetch(table==="products"?"/data-entry/products/template":"/import/template/" + encodeURIComponent(table));
      if (!response.ok) {
        setMsg("دریافت قالب ناموفق بود (" + response.status + ").");
        return;
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = table + "_template.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error: unknown) {
      setMsg("دریافت قالب انجام نشد: " + (error instanceof Error ? error.message : "خطای ناشناخته"));
    }
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-white">{title} <span className="text-[10px] text-slate-500">({rows.length})</span></h2>
        <div className="flex flex-wrap gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو..." className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none placeholder:text-slate-600" />
          {!readOnly&&<button onClick={openNew} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500">+ افزودن</button>}
          <button onClick={downloadTemplate} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10">📤 قالب اکسل</button>
          {!readOnly&&table==="products"&&<Link href="/data-entry?entity=products" className="rounded-lg border border-white/10 px-3 py-2 text-xs text-white">ورود اکسل با پیش‌نمایش</Link>}
          {!readOnly&&table!=="products"&&<label className="cursor-pointer rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10">
            📥 ایمپورت اکسل
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importExcel(f); e.target.value = ""; }} />
          </label>}
        </div>
      </div>

      {msg && <div className="mb-3 rounded-lg bg-violet-500/10 px-3 py-2 text-xs text-violet-200">{msg}</div>}

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-right text-xs">
          <thead className="bg-white/5 text-slate-400">
            <tr>
              <th className="p-2">#</th>
              {columns.map((c) => <th key={c.key} className="whitespace-nowrap p-2">{c.label}</th>)}
              <th className="p-2">عملیات</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 2} className="p-4 text-center text-slate-500">در حال بارگذاری...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={columns.length + 2} className="p-4 text-center text-slate-500">خالی — هنوز ردیفی اضافه نشده</td></tr>
            ) : rows.map((r, index) => (
              <tr key={r.id ?? index} className="border-t border-white/5 hover:bg-white/5">
                <td className="p-2 text-slate-500">{r.id ?? ""}</td>
                {columns.map((c) => <td key={c.key} className="whitespace-nowrap p-2">{String(r[c.key] ?? "")}</td>)}
                <td className="p-2">{!readOnly&&<>
                  <button onClick={() => setEditing({ ...r })} className="mr-1 text-violet-300 hover:text-violet-200">✏️</button>
                  {typeof r.id === "number" && <button onClick={() => remove(r.id!)} className="text-rose-300 hover:text-rose-200">🗑️</button>}
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onClick={() => setEditing(null)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0f1222] p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-sm font-bold text-white">{editing._new ? "افزودن" : "ویرایش"} — {title}</h3>
            <div className="grid max-h-[60vh] gap-3 overflow-y-auto">
              {columns.map((c) => (
                <label key={c.key} className="block">
                  <span className="mb-1 block text-[10px] text-slate-400">{c.label}</span>
                  {c.type === "boolean" ? (
                    <input type="checkbox" checked={!!editing[c.key]} onChange={(e) => setEditing({ ...editing, [c.key]: e.target.checked ? 1 : 0 })} />
                  ) : (
                    <input
                      type={c.type === "number" ? "number" : "text"}
                      value={String(editing[c.key] ?? "")}
                      onChange={(e) => setEditing({ ...editing, [c.key]: e.target.value })}
                      className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none"
                    />
                  )}
                </label>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setEditing(null)} className="rounded-lg border border-white/10 px-4 py-2 text-xs text-slate-400">انصراف</button>
              <button onClick={save} disabled={saving} className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{saving ? "..." : "ذخیره"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
