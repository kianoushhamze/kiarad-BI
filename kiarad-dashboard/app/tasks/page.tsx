"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { getSavedUser, secureApi } from "../../lib/secure-api";

type Task = { id: number; title: string; description?: string; priority: string; status: string; progress: number; assigned_to: number; assignee_name: string; customer_name?: string; due_date?: string; updated_at?: string; };
type User = { id: number; full_name: string; role: string; salesperson_name?: string; is_active: number; };

const labels: Record<string, string> = { new: "جدید", in_progress: "در حال انجام", completed: "تکمیل‌شده", blocked: "مسدود", low: "کم", normal: "عادی", high: "بالا", urgent: "فوری" };

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const session = getSavedUser();
  const manager = session?.role === "ceo" || session?.role === "sales_manager";

  const load = useCallback(async () => {
    setError("");
    try {
      setTasks((await secureApi<{ tasks: Task[] }>("/tasks")).tasks);
      if (manager) setUsers((await secureApi<{ users: User[] }>("/users")).users.filter(u => u.is_active && u.role === "salesperson"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "دریافت تسک‌ها انجام نشد."); }
  }, [manager]);
  useEffect(() => { load(); }, [load]);

  const createTask = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); setError("");
    try {
      await secureApi("/tasks", { method: "POST", body: JSON.stringify({ title: form.get("title"), description: form.get("description") || null, priority: form.get("priority"), assigned_to: Number(form.get("assigned_to")), due_date: form.get("due_date") ? new Date(String(form.get("due_date"))).toISOString() : null }) });
      setShowCreate(false); setMessage("تسک ایجاد و به ویزیتور تخصیص داده شد."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ایجاد تسک انجام نشد."); }
  };

  const update = async (task: Task, status: string, progress: number) => {
    setError("");
    try {
      await secureApi(`/tasks/${task.id}/progress`, { method: "PATCH", body: JSON.stringify({ status, progress, note: null }) });
      setMessage("وضعیت تسک به‌روزرسانی شد."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "به‌روزرسانی انجام نشد."); }
  };

  const open = tasks.filter(t => t.status !== "completed").length;
  const overdue = tasks.filter(t => t.status !== "completed" && t.due_date && new Date(t.due_date) < new Date()).length;
  const avg = tasks.length ? Math.round(tasks.reduce((a, b) => a + b.progress, 0) / tasks.length) : 0;

  return <PortalShell title="تسک‌ها و پیگیری عملیات" eyebrow="کنترل اجرا" actions={manager && <button onClick={() => setShowCreate(true)} className={primaryButton}>ایجاد تسک</button>}>
    {(error || message) && <div className={`mb-4 rounded-xl border p-3 text-xs ${error ? "border-rose-500/20 bg-rose-500/10 text-rose-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"}`}>{error || message}</div>}
    <div className="grid gap-3 sm:grid-cols-3"><Stat label="تسک باز" value={open} color="text-cyan-300" /><Stat label="عقب‌افتاده" value={overdue} color="text-rose-300" /><Stat label="میانگین پیشرفت" value={`${avg}٪`} color="text-violet-300" /></div>
    <div className="mt-4 grid gap-3">{tasks.map(task => <Surface key={task.id} className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><h2 className="text-sm font-bold text-white">{task.title}</h2><span className={`rounded-md px-2 py-1 text-[8px] ${task.priority === "urgent" || task.priority === "high" ? "bg-rose-500/10 text-rose-300" : "bg-white/5 text-slate-400"}`}>{labels[task.priority] ?? task.priority}</span></div><p className="mt-2 max-w-3xl text-[10px] leading-5 text-slate-500">{task.description || "بدون توضیح"}</p></div><div className="text-left text-[10px]"><div className="text-slate-300">{task.assignee_name}</div><div className="mt-1 text-slate-600">{task.due_date ? new Date(task.due_date).toLocaleDateString("fa-IR") : "بدون سررسید"}</div></div></div>
      <div className="mt-4 grid items-center gap-3 sm:grid-cols-[1fr_140px_220px]"><div><div className="mb-2 flex justify-between text-[9px]"><span className="text-slate-600">پیشرفت</span><span className="text-violet-300">{task.progress}٪</span></div><div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-gradient-to-l from-violet-500 to-cyan-400" style={{ width: `${task.progress}%` }} /></div></div><span className="rounded-lg bg-white/[0.04] px-2 py-2 text-center text-[9px] text-slate-400">{labels[task.status] ?? task.status}</span><div className="flex gap-2"><button onClick={() => update(task, "in_progress", Math.max(task.progress, 25))} disabled={task.status === "completed"} className="flex-1 rounded-lg border border-white/10 px-2 py-2 text-[9px] text-slate-300 disabled:opacity-30">شروع/ادامه</button><button onClick={() => update(task, "completed", 100)} disabled={task.status === "completed"} className="flex-1 rounded-lg bg-emerald-500/10 px-2 py-2 text-[9px] text-emerald-300 disabled:opacity-30">تکمیل</button></div></div>
    </Surface>)}{!tasks.length && <Surface className="p-10 text-center text-xs text-slate-600">تسکی ثبت نشده است.</Surface>}</div>
    {showCreate && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"><form onSubmit={createTask} className="w-full max-w-lg rounded-3xl border border-white/10 bg-[#0c0e19] p-5"><div className="mb-5 flex items-center justify-between"><h2 className="text-sm font-bold text-white">ایجاد تسک جدید</h2><button type="button" onClick={() => setShowCreate(false)} className="text-xl text-slate-500">×</button></div><div className="space-y-3"><input name="title" required placeholder="عنوان تسک" className={fieldClass} /><textarea name="description" rows={3} placeholder="شرح کار و نتیجه مورد انتظار" className={fieldClass} /><div className="grid gap-3 sm:grid-cols-2"><select name="assigned_to" required className={fieldClass}><option value="">انتخاب ویزیتور</option>{users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select><select name="priority" defaultValue="normal" className={fieldClass}><option value="normal">اولویت عادی</option><option value="high">اولویت بالا</option><option value="urgent">فوری</option><option value="low">کم</option></select></div><input name="due_date" type="datetime-local" className={fieldClass} /><button className={`${primaryButton} w-full`}>ثبت و تخصیص</button></div></form></div>}
  </PortalShell>;
}

function Stat({ label, value, color }: { label: string; value: string | number; color: string }) { return <Surface className="p-4"><div className="text-[10px] text-slate-500">{label}</div><div className={`mt-3 text-2xl font-black ${color}`}>{typeof value === "number" ? new Intl.NumberFormat("fa-IR").format(value) : value}</div></Surface>; }
