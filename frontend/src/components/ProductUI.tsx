"use client";

import type { User } from "@/lib/api";

export type Workspace = "overview" | "profile" | "discover" | "simulator";

const navItems: Array<{ id: Workspace; label: string; eyebrow: string }> = [
  { id: "overview", label: "Plan", eyebrow: "01" },
  { id: "profile", label: "Finances", eyebrow: "02" },
  { id: "discover", label: "Properties", eyebrow: "03" },
  { id: "simulator", label: "SBLOC lab", eyebrow: "04" },
];

export function AppHeader({
  user,
  active,
  onNavigate,
  onLogout,
}: Readonly<{
  user: User;
  active: Workspace;
  onNavigate: (workspace: Workspace) => void;
  onLogout: () => void;
}>) {
  const initials = user.name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-[#f7f8f5]/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] items-center gap-5 px-4 py-3 lg:px-8">
        <button className="flex shrink-0 items-center gap-3 text-left" onClick={() => onNavigate("overview")}>
          <span className="grid size-9 place-items-center rounded-xl bg-[#12372a] text-sm font-semibold text-white shadow-sm">H</span>
          <span className="hidden sm:block">
            <span className="block text-sm font-semibold tracking-tight text-slate-950">Hearthline</span>
            <span className="block text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">Property planner</span>
          </span>
        </button>

        <nav className="mx-auto flex min-w-0 items-center gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold transition sm:px-4 ${
                active === item.id ? "bg-[#12372a] text-white shadow-sm" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"
              }`}
            >
              <span className="mr-1.5 hidden text-[9px] opacity-60 md:inline">{item.eyebrow}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <div className="hidden text-right md:block">
            <div className="max-w-36 truncate text-xs font-semibold text-slate-800">{user.name}</div>
            <button className="text-[11px] text-slate-500 hover:text-slate-900" onClick={onLogout}>Sign out</button>
          </div>
          <span className="grid size-9 place-items-center rounded-full border border-[#b7c8bf] bg-[#e6efe9] text-xs font-bold text-[#12372a]">{initials}</span>
        </div>
      </div>
    </header>
  );
}

export function Panel({
  children,
  className = "",
}: Readonly<{ children: React.ReactNode; className?: string }>) {
  return <section className={`rounded-2xl border border-slate-200 bg-white shadow-[0_14px_40px_-32px_rgba(15,23,42,.35)] ${className}`}>{children}</section>;
}

export function Pill({
  children,
  tone = "neutral",
}: Readonly<{ children: React.ReactNode; tone?: "neutral" | "green" | "amber" | "red" | "blue" }>) {
  const tones = {
    neutral: "border-slate-200 bg-slate-50 text-slate-600",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    red: "border-rose-200 bg-rose-50 text-rose-700",
    blue: "border-sky-200 bg-sky-50 text-sky-700",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tones[tone]}`}>{children}</span>;
}

export function WorkspaceIntro({
  eyebrow,
  title,
  description,
  action,
}: Readonly<{ eyebrow: string; title: string; description: string; action?: React.ReactNode }>) {
  return (
    <div className="flex flex-col justify-between gap-5 border-b border-slate-200 pb-6 sm:flex-row sm:items-end">
      <div className="max-w-3xl">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#2d6a4f]">{eyebrow}</div>
        <h1 className="text-3xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-4xl">{title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function LoadingBlock({ label = "Loading your plan…" }: Readonly<{ label?: string }>) {
  return (
    <div className="grid min-h-[360px] place-items-center">
      <div className="text-center">
        <span className="mx-auto mb-3 block size-6 animate-spin rounded-full border-2 border-slate-200 border-t-[#2d6a4f]" />
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  );
}

export function ErrorNotice({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{children}</div>;
}
