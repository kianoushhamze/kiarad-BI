"use client";
import { useEffect, useState } from "react";
import { PrivateCatalogFile } from "./private-catalog-file";
import { authFetch } from "../lib/secure-api";

type Media = {
  id: number;
  media_type: string;
  file_path: string;
  file_name?: string;
  size_bytes?: number;
  caption?: string;
};

export function CatalogFiles() {
  const [items, setItems] = useState<Media[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState("");
  const [caption, setCaption] = useState("");

  const load = async () => {
    try {
      const r = await authFetch("/catalog-files");
      if (r.ok) {
        const data = await r.json();
        setItems(Array.isArray(data) ? data : []);
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, []);

  const upload = async (file: File, mediaType: "image" | "pdf") => {
    setUploading(true);
    setMsg("");
    const fd = new FormData();
    fd.append("media_type", mediaType);
    fd.append("caption", caption);
    fd.append("file", file);
    try {
      const r = await authFetch("/upload/catalog-file", { method: "POST", body: fd });
      const data = await r.json();
      if (r.ok) {
        setMsg("آپلود شد");
        setCaption("");
        load();
      } else {
        setMsg("خطا: " + (data.detail || r.status));
      }
    } catch (e: unknown) {
      setMsg("خطا: " + (e instanceof Error ? e.message : ""));
    }
    setUploading(false);
  };

  const remove = async (id: number) => {
    if (!confirm("حذف این فایل؟")) return;
    try {
      const r = await authFetch("/catalog-files/" + id, { method: "DELETE" });
      if (r.ok) load();
    } catch {}
  };

  const fmtSize = (b?: number) => {
    if (!b) return "";
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return Math.round(b / 1024) + " KB";
    return (b / 1024 / 1024).toFixed(1) + " MB";
  };

  const images = items.filter((m) => m.media_type === "image");
  const pdfs = items.filter((m) => m.media_type === "pdf");

  return (
    <div>
      <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/[0.08] p-4">
        <div className="mb-3 flex items-center justify-between">
          <b className="text-sm text-white">📚 کاتالوگ دیجیتال شرکت</b>
          <span className="text-[10px] text-slate-400">{images.length} عکس · {pdfs.length} PDF</span>
        </div>
        <p className="mb-3 text-[10px] text-slate-400">عکس‌ها و کاتالوگ‌های عمومی شرکت — برای همه‌ی محصولات یا فایل‌های تبلیغاتی</p>

        <input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="توضیح (اختیاری)"
          className="mb-3 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-[11px] text-white outline-none placeholder:text-slate-600"
        />

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <label className={"cursor-pointer rounded-lg border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-center text-[11px] text-emerald-200 hover:bg-emerald-500/20 " + (uploading ? "opacity-50" : "")}>
            🖼️ آپلود عکس
            <input type="file" accept="image/*" className="hidden" disabled={uploading}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f, "image"); e.target.value = ""; }} />
          </label>
          <label className={"cursor-pointer rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-center text-[11px] text-rose-200 hover:bg-rose-500/20 " + (uploading ? "opacity-50" : "")}>
            📄 آپلود PDF
            <input type="file" accept=".pdf" className="hidden" disabled={uploading}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f, "pdf"); e.target.value = ""; }} />
          </label>
        </div>

        {msg && <div className="mt-3 rounded-lg bg-violet-500/10 px-3 py-2 text-[10px] text-violet-200">{msg}</div>}
        {uploading && <div className="mt-3 text-center text-[10px] text-slate-400">در حال آپلود...</div>}
      </div>

      {loading ? (
        <div className="p-8 text-center text-xs text-slate-500">در حال بارگذاری...</div>
      ) : items.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-600">هنوز فایلی آپلود نشده — اولین عکس یا PDF رو اضافه کن</div>
      ) : (
        <div className="space-y-6">
          {images.length > 0 && (
            <div>
              <div className="mb-3 text-xs font-bold text-white">🖼️ عکس‌ها</div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {images.map((m) => (
                  <div key={m.id} className="group relative overflow-hidden rounded-xl border border-white/10 bg-black/30">
                    <PrivateCatalogFile path={m.file_path} name={m.file_name || m.caption || "تصویر کاتالوگ"} image className="h-40 w-full object-cover"/>
                    <button onClick={(e) => { e.preventDefault(); remove(m.id); }}
                      className="absolute right-2 top-2 rounded bg-rose-600/80 px-2 py-1 text-[10px] text-white transition hover:bg-rose-500">
                      حذف
                    </button>
                    {m.caption && <div className="bg-black/40 p-2 text-center text-[10px] text-slate-300">{m.caption}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {pdfs.length > 0 && (
            <div>
              <div className="mb-3 text-xs font-bold text-white">📄 فایل‌های PDF</div>
              <div className="space-y-2">
                {pdfs.map((m) => (
                  <div key={m.id} className="flex items-center justify-between rounded-xl border border-white/10 bg-black/20 px-4 py-3">
                    <PrivateCatalogFile path={m.file_path} name={m.file_name || m.caption || "کاتالوگ"} className="text-xs text-violet-200"/>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-slate-600">{fmtSize(m.size_bytes)}</span>
                      <button onClick={() => remove(m.id)} className="text-rose-300 hover:text-rose-200">🗑️</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
