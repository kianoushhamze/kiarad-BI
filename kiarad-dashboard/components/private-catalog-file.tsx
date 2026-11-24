"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { authFetch } from "../lib/secure-api";

// Read protected files with the same account as the page. Never put a token in a URL.
export function PrivateCatalogFile({ path, name, image = false, className = "" }: {
  path: string; name: string; image?: boolean; className?: string;
}) {
  const [file, setFile] = useState<{ path: string; url: string } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    const load = async () => {
      if (!/^\/api\/files\/(?:products\/(?:images|pdfs)|catalog)\/[a-zA-Z0-9._-]+$/.test(path)) {
        setFailure(path); return;
      }
      try {
        const response = await authFetch(path.slice(4), { signal: controller.signal, cache: "no-cache" });
        if (!response.ok) throw new Error("دریافت فایل انجام نشد.");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setFile({path, url: objectUrl});
      } catch {
        if (!controller.signal.aborted) setFailure(path);
      }
    };
    void load();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  if (failure === path) return <span role="status" className="text-xs text-amber-300">دریافت فایل انجام نشد؛ صفحه را تازه کنید.</span>;
  if (file?.path !== path) return <span className="text-xs text-slate-400">در حال دریافت فایل…</span>;
  return <a href={file.url} download={name} className={image ? "block" : className}>
    {image ? <Image src={file.url} alt={name} width={240} height={160} unoptimized className={className}/> : <>📄 {name}</>}
  </a>;
}
