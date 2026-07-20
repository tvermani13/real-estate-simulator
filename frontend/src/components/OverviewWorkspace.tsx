"use client";

import { useEffect, useState } from "react";

import { api, type AffordabilityResponse, type ProviderStatus, type SavedSearch } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { ErrorNotice, LoadingBlock, Panel, Pill, WorkspaceIntro, type Workspace } from "@/components/ProductUI";

export function OverviewWorkspace({ onNavigate }: Readonly<{ onNavigate: (workspace: Workspace) => void }>) {
  const [plan, setPlan] = useState<AffordabilityResponse | null>(null);
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.affordability(), api.searches(), api.providerStatus()])
      .then(([nextPlan, nextSearches, nextProvider]) => {
        setPlan(nextPlan);
        setSearches(nextSearches);
        setProvider(nextProvider);
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, []);

  if (!plan && !error) return <LoadingBlock />;

  return (
    <main className="mx-auto max-w-[1320px] px-4 py-8 lg:px-8 lg:py-10">
      <WorkspaceIntro
        eyebrow="Your buying plan"
        title="Start with a range you can live with."
        description="Your income sets the payment ceiling. Your liquidity protects your reserves. Your risk preference decides how close to either edge you should get."
        action={<button className="primary-button" onClick={() => onNavigate("profile")}>Review finances</button>}
      />
      {error ? <div className="mt-6"><ErrorNotice>{error}</ErrorNotice></div> : null}
      {plan ? (
        <>
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Calculated net worth" value={formatCurrency(plan.net_worth)} note={`${formatCurrency(plan.liquid_net_worth)} liquid`} />
            <MetricCard label="Cash after reserves" value={formatCurrency(plan.investable_cash)} note={`${formatCurrency(plan.required_reserves)} held back`} />
            <MetricCard label="Current debt ratio" value={formatPct(plan.current_back_end_dti, 1)} note="Before a new property" />
            <MetricCard label="Listing feed" value={provider?.mode === "live" ? "Live" : "Demo"} note={provider?.provider ?? "Loading"} tone={provider?.mode === "live" ? "green" : "amber"} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <RangeCard
              label="Primary residence"
              title="A home that fits everyday life"
              range={plan.primary}
              accent="bg-[#12372a]"
              onExplore={() => onNavigate("discover")}
            />
            <RangeCard
              label="Rental investment"
              title="Capital first, then deal quality"
              range={plan.investment}
              accent="bg-[#9a6b24]"
              onExplore={() => onNavigate("discover")}
            />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.35fr_.65fr]">
            <Panel className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                <div>
                  <h2 className="text-sm font-semibold text-slate-950">Saved property scans</h2>
                  <p className="mt-1 text-xs text-slate-500">Reusable criteria for homes and investments</p>
                </div>
                <button className="text-xs font-semibold text-[#1f5b43]" onClick={() => onNavigate("discover")}>Manage scans →</button>
              </div>
              {searches.length ? (
                <div className="divide-y divide-slate-100">
                  {searches.slice(0, 4).map((search) => (
                    <button key={search.id} className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50" onClick={() => onNavigate("discover")}>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-slate-900">{search.name}</div>
                        <div className="mt-1 text-xs text-slate-500">{search.criteria.location} · {search.criteria.min_bedrooms}+ bd · {search.criteria.purpose === "primary" ? "Home" : "Rental"}</div>
                      </div>
                      <div className="text-right">
                        <Pill tone={search.notifications_enabled ? "green" : "neutral"}>{search.notifications_enabled ? "Alerts on" : "Manual"}</Pill>
                        <div className="mt-1.5 text-[10px] text-slate-400">{search.last_scanned_at ? `Last scan ${new Date(search.last_scanned_at).toLocaleDateString()}` : "Not scanned yet"}</div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="px-5 py-10 text-center">
                  <div className="text-sm font-semibold text-slate-800">No scans saved yet</div>
                  <p className="mx-auto mt-2 max-w-sm text-xs leading-5 text-slate-500">Choose a market and property criteria. We will score listings against the financial plan above.</p>
                  <button className="secondary-button mt-4" onClick={() => onNavigate("discover")}>Create your first scan</button>
                </div>
              )}
            </Panel>

            <Panel className="p-5">
              <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">How the guardrails work</div>
              <div className="mt-5 space-y-4">
                {plan.assumptions.map((assumption, index) => (
                  <div key={assumption} className="flex gap-3">
                    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#e7efe9] text-[10px] font-bold text-[#1f5b43]">{index + 1}</span>
                    <p className="text-xs leading-5 text-slate-600">{assumption}</p>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      ) : null}
    </main>
  );
}

function MetricCard({ label, value, note, tone }: Readonly<{ label: string; value: string; note: string; tone?: "green" | "amber" }>) {
  return (
    <Panel className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium text-slate-500">{label}</div>
        {tone ? <span className={`mt-0.5 size-2 rounded-full ${tone === "green" ? "bg-emerald-500" : "bg-amber-500"}`} /> : null}
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-[-0.035em] text-slate-950">{value}</div>
      <div className="mt-1 text-[11px] text-slate-400">{note}</div>
    </Panel>
  );
}

function RangeCard({ label, title, range, accent, onExplore }: Readonly<{ label: string; title: string; range: AffordabilityResponse["primary"]; accent: string; onExplore: () => void }>) {
  const denominator = Math.max(range.stretch_max, 1);
  const comfortStart = Math.min(100, (range.comfortable_min / denominator) * 100);
  const comfortWidth = Math.max(2, ((range.comfortable_max - range.comfortable_min) / denominator) * 100);
  return (
    <Panel className="overflow-hidden">
      <div className={`h-1.5 ${accent}`} />
      <div className="p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">{label}</div>
            <h2 className="mt-2 text-lg font-semibold tracking-tight text-slate-950">{title}</h2>
          </div>
          <Pill tone={range.purpose === "primary" ? "green" : "amber"}>{Math.round(range.down_payment_pct * 100)}% down</Pill>
        </div>
        <div className="mt-7">
          <div className="text-xs text-slate-500">Comfortable purchase range</div>
          <div className="mt-1 text-3xl font-semibold tracking-[-0.04em] text-slate-950">{formatCurrency(range.comfortable_min)}–{formatCurrency(range.comfortable_max)}</div>
          <div className="relative mt-6 h-2 rounded-full bg-slate-100">
            <div className={`absolute top-0 h-2 rounded-full ${accent}`} style={{ left: `${comfortStart}%`, width: `${comfortWidth}%` }} />
            <span className="absolute right-0 top-4 text-[10px] text-slate-400">Stretch {formatCurrency(range.stretch_max)}</span>
          </div>
        </div>
        <div className="mt-10 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">Capital available</div>
            <div className="mt-1 text-sm font-semibold text-slate-800">{formatCurrency(range.capital_available)}</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{range.monthly_payment_budget ? "Monthly ceiling" : "Cash-limited max"}</div>
            <div className="mt-1 text-sm font-semibold text-slate-800">{formatCurrency(range.monthly_payment_budget ?? range.cash_limited_max)}</div>
          </div>
        </div>
        <p className="mt-4 text-xs leading-5 text-slate-500">{range.explanation}</p>
        <button className="mt-5 text-xs font-semibold text-[#1f5b43]" onClick={onExplore}>Find matching properties →</button>
      </div>
    </Panel>
  );
}
