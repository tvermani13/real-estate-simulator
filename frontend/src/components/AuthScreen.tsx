"use client";

import { FormEvent, useState } from "react";

import { api, type User } from "@/lib/api";

export function AuthScreen({ onAuthenticated }: Readonly<{ onAuthenticated: (user: User) => void }>) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = mode === "login"
        ? await api.login({ email, password })
        : await api.register({ name, email, password });
      onAuthenticated(result.user);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not sign you in.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#eef1ec] p-3 sm:p-6 lg:p-10">
      <div className="mx-auto grid min-h-[calc(100vh-3rem)] max-w-6xl overflow-hidden rounded-[28px] border border-white/70 bg-white shadow-[0_30px_90px_-45px_rgba(15,23,42,.55)] lg:grid-cols-[1.05fr_.95fr]">
        <section className="relative hidden overflow-hidden bg-[#12372a] p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div className="absolute -right-24 -top-24 size-80 rounded-full border border-white/10" />
          <div className="absolute -bottom-32 -left-24 size-[420px] rounded-full border border-white/10" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-white text-sm font-bold text-[#12372a]">H</span>
              <div>
                <div className="font-semibold">Hearthline</div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-emerald-100/70">Property planner</div>
              </div>
            </div>
            <div className="mt-24 max-w-lg">
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#a7d8bd]">From finances to front doors</p>
              <h1 className="mt-5 text-5xl font-semibold leading-[1.05] tracking-[-0.045em]">Know your range.<br />Find the right property.</h1>
              <p className="mt-6 max-w-md text-base leading-7 text-emerald-50/75">
                Turn income, liquidity, debt, and risk tolerance into a practical buying plan—then screen homes and rentals against it.
              </p>
            </div>
          </div>
          <div className="relative grid grid-cols-3 gap-3">
            {["Private profile", "Clear math", "Saved scans"].map((label, index) => (
              <div key={label} className="rounded-xl border border-white/10 bg-white/[.06] p-3">
                <div className="text-[10px] font-bold text-[#a7d8bd]">0{index + 1}</div>
                <div className="mt-2 text-xs font-medium">{label}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-12">
          <div className="w-full max-w-sm">
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <span className="grid size-9 place-items-center rounded-xl bg-[#12372a] text-sm font-bold text-white">H</span>
              <span className="font-semibold text-slate-950">Hearthline</span>
            </div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#2d6a4f]">Your property workspace</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-slate-950">
              {mode === "login" ? "Welcome back" : "Build your buying plan"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {mode === "login" ? "Sign in to review your ranges and saved scans." : "Create an account to save your finances, criteria, and results."}
            </p>

            <form className="mt-8 space-y-4" onSubmit={submit}>
              {mode === "register" ? (
                <label className="block">
                  <span className="mb-1.5 block text-xs font-semibold text-slate-700">Name</span>
                  <input className="product-input" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} placeholder="Your name" />
                </label>
              ) : null}
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-slate-700">Email</span>
                <input className="product-input" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="you@example.com" />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold text-slate-700">Password</span>
                <input className="product-input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === "register" ? 10 : 1} placeholder={mode === "register" ? "10+ characters, with a number" : "Your password"} />
              </label>
              {error ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}
              <button className="w-full rounded-xl bg-[#12372a] px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#0d2b21] disabled:opacity-60" disabled={loading}>
                {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>

            <div className="mt-6 text-center text-sm text-slate-500">
              {mode === "login" ? "New to Hearthline?" : "Already have an account?"}{" "}
              <button className="font-semibold text-[#1f5b43] hover:underline" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
                {mode === "login" ? "Create an account" : "Sign in"}
              </button>
            </div>
            <p className="mt-10 border-t border-slate-200 pt-5 text-center text-[11px] leading-5 text-slate-400">
              Planning estimates only—not lending, tax, legal, or investment advice.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
