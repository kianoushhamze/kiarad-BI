"use client";

import { useId, useMemo, useRef, useState } from "react";

export type ChartSeries = { name: string; color: string; values: (number | null)[] };

type Props = {
  labels: string[];
  series: ChartSeries[];
  height?: number;
  format?: (value: number) => string;
  ariaLabel: string;
};

const fa = (n: number) => new Intl.NumberFormat("fa-IR").format(Math.round(n));

/**
 * Dependency-free SVG chart: line or bars, per-series legend toggle, and a
 * tooltip that follows the pointer, touch or arrow keys. Labels run
 * right-to-left (oldest at the right) to match the Persian reading order.
 */
export function InteractiveChart({ labels, series, height = 240, format = fa, ariaLabel }: Props) {
  const uid = useId().replace(/:/g, "");
  const [kind, setKind] = useState<"line" | "bar">("line");
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [active, setActive] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const W = 640, padT = 14, padB = 30, padX = 12;
  const n = labels.length;

  const visible = series.filter((s) => !hidden[s.name]);
  const max = useMemo(() => {
    const all = visible.flatMap((s) => s.values.filter((v): v is number => v != null));
    return Math.max(1, ...all);
  }, [visible]);

  if (n === 0) return <p className="py-6 text-center text-xs text-slate-500">هنوز داده‌ای برای نمودار نیست.</p>;

  const innerW = W - padX * 2, innerH = height - padT - padB;
  const slot = innerW / n;
  const xAt = (i: number) => W - padX - slot * (i + 0.5);
  const yAt = (v: number) => padT + innerH - (v / max) * innerH;

  const pick = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const x = ((clientX - box.left) / box.width) * W;
    setActive(Math.min(n - 1, Math.max(0, Math.floor((W - padX - x) / slot))));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setActive((a) => Math.min(n - 1, (a ?? -1) + 1)); }
    if (e.key === "ArrowRight") { e.preventDefault(); setActive((a) => Math.max(0, (a ?? n) - 1)); }
    if (e.key === "Escape") setActive(null);
  };

  const barW = Math.max(4, Math.min(34, (slot * 0.7) / Math.max(1, visible.length)));
  const tipLeft = active == null ? 0 : (xAt(active) / W) * 100;

  return (
    <div className="relative" dir="rtl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {series.map((s) => (
            <button key={s.name} type="button" aria-pressed={!hidden[s.name]}
              onClick={() => setHidden((h) => ({ ...h, [s.name]: !h[s.name] }))}
              className={`flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] transition ${hidden[s.name] ? "border-white/10 text-slate-600 line-through" : "border-white/15 text-slate-200"}`}>
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.name}
            </button>
          ))}
        </div>
        <div className="flex overflow-hidden rounded-lg border border-white/10 text-[11px]" role="group" aria-label="نوع نمودار">
          {(["line", "bar"] as const).map((k) => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}
              className={`px-3 py-1 ${kind === k ? "bg-violet-500/25 text-violet-100" : "text-slate-400"}`}>{k === "line" ? "خطی" : "ستونی"}</button>
          ))}
        </div>
      </div>

      <svg ref={ref} viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img" aria-label={ariaLabel}
        tabIndex={0} onKeyDown={onKey} onBlur={() => setActive(null)}
        onPointerMove={(e) => pick(e.clientX)} onPointerDown={(e) => pick(e.clientX)} onPointerLeave={() => setActive(null)}
        style={{ touchAction: "pan-y", display: "block" }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.name} id={`${uid}g${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={s.color} stopOpacity=".35" /><stop offset="1" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={padX} x2={W - padX} y1={yAt(max * t)} y2={yAt(max * t)} stroke="rgba(177,190,255,.1)" />
            {(t === 0.5 || t === 1) && <text x={W - padX} y={yAt(max * t) - 3} textAnchor="end" fontSize="9" fill="#7c86a8">{format(max * t)}</text>}
          </g>
        ))}
        {labels.map((l, i) => (i % Math.ceil(n / 7) === 0 || i === n - 1) && (
          <text key={i} x={xAt(i)} y={height - 9} textAnchor="middle" fontSize="9.5" fill="#8b94b3">{l}</text>
        ))}
        {active != null && <line x1={xAt(active)} x2={xAt(active)} y1={padT} y2={padT + innerH} stroke="rgba(139,124,255,.5)" strokeDasharray="3 3" />}
        {series.map((s, si) => {
          if (hidden[s.name]) return null;
          const idx = visible.indexOf(s);
          if (kind === "bar") {
            return s.values.map((v, i) => v == null ? null : (
              <rect key={`${s.name}${i}`} x={xAt(i) - (barW * visible.length) / 2 + barW * idx} y={yAt(v)} width={barW - 1} height={Math.max(1, padT + innerH - yAt(v))}
                rx="3" fill={s.color} opacity={active == null || active === i ? 0.95 : 0.4} />
            ));
          }
          const pts = s.values.map((v, i) => (v == null ? null : [xAt(i), yAt(v)] as const));
          const path = pts.reduce((d, p) => (p ? `${d}${d && !d.endsWith("M") ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}` : d), "");
          const solid = pts.filter(Boolean) as (readonly [number, number])[];
          return (
            <g key={s.name}>
              {solid.length > 1 && <path d={`${path}L${solid[solid.length - 1][0]},${padT + innerH}L${solid[0][0]},${padT + innerH}Z`} fill={`url(#${uid}g${si})`} />}
              <path d={path} fill="none" stroke={s.color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
              {active != null && pts[active] && <circle cx={pts[active]![0]} cy={pts[active]![1]} r="4.5" fill={s.color} stroke="#0d0b16" strokeWidth="2" />}
            </g>
          );
        })}
      </svg>

      {active != null && (
        <div role="status" className="pointer-events-none absolute top-8 z-10 min-w-[130px] -translate-x-1/2 rounded-xl border border-white/10 bg-[#0d0b16]/95 px-3 py-2 text-[11px] shadow-xl backdrop-blur"
          style={{ left: `clamp(70px, ${tipLeft}%, calc(100% - 70px))`, direction: "rtl" }}>
          <div className="mb-1 font-bold text-white">{labels[active]}</div>
          {visible.map((s) => (
            <div key={s.name} className="flex items-center justify-between gap-3 text-slate-300">
              <span className="flex items-center gap-1"><span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.name}</span>
              <b>{s.values[active] == null ? "—" : format(s.values[active] as number)}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
