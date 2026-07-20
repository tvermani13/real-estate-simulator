"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  type PropertyMatch,
  type ProviderStatus,
  type SavedSearch,
  type ScanResponse,
  type SearchCriteria,
  type User,
} from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { ErrorNotice, LoadingBlock, Panel, Pill, WorkspaceIntro } from "@/components/ProductUI";

const defaultCriteria: SearchCriteria = {
  purpose: "primary",
  location: "Fairfield County, CT",
  radius_miles: 20,
  min_price: null,
  max_price: null,
  min_bedrooms: 3,
  min_bathrooms: 2,
  property_types: ["Single Family", "Condo", "Townhouse"],
  max_days_on_market: 90,
  down_payment_pct: null,
  min_match_score: 65,
  min_cap_rate: null,
  min_dscr: null,
  min_cash_on_cash: null,
  min_monthly_cashflow: null,
};

export function DiscoverWorkspace({ user }: Readonly<{ user: User }>) {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [matches, setMatches] = useState<PropertyMatch[]>([]);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [showBuilder, setShowBuilder] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "strong" | "possible">("all");
  const [name, setName] = useState("My home search");
  const [criteria, setCriteria] = useState<SearchCriteria>(defaultCriteria);
  const [notifications, setNotifications] = useState(false);

  useEffect(() => {
    Promise.all([api.searches(), api.providerStatus()])
      .then(([nextSearches, nextProvider]) => {
        setSearches(nextSearches);
        setProvider(nextProvider);
        if (nextSearches.length) setSelectedId(nextSearches[0].id);
        else setShowBuilder(true);
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) { setMatches([]); return; }
    api.savedMatches(selectedId)
      .then(setMatches)
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [selectedId]);

  const selected = searches.find((search) => search.id === selectedId) ?? null;
  const visibleMatches = useMemo(
    () => matches.filter((match) => filter === "all" || match.verdict === filter),
    [filter, matches],
  );

  async function createSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const created = await api.createSearch({
        name,
        criteria,
        notifications_enabled: notifications,
        notification_email: notifications ? user.email : null,
      });
      setSearches((current) => [created, ...current]);
      setSelectedId(created.id);
      setShowBuilder(false);
      setMatches([]);
      setScanResult(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the search.");
    }
  }

  async function runScan() {
    if (!selectedId) return;
    setScanning(true);
    setError(null);
    try {
      const result = await api.scanSearch(selectedId);
      setScanResult(result);
      setMatches(result.matches);
      setSearches((current) => current.map((search) => search.id === result.search.id ? result.search : search));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The property scan failed.");
    } finally {
      setScanning(false);
    }
  }

  async function removeSearch(id: string) {
    if (!window.confirm("Delete this saved search and its stored matches?")) return;
    setError(null);
    try {
      await api.deleteSearch(id);
      const next = searches.filter((search) => search.id !== id);
      setSearches(next);
      setSelectedId(next[0]?.id ?? null);
      if (!next.length) setShowBuilder(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete the search.");
    }
  }

  if (loading) return <LoadingBlock label="Loading property scans…" />;

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-8 lg:px-8 lg:py-10">
      <WorkspaceIntro
        eyebrow="Property discovery"
        title="Scan listings through your financial lens."
        description="Price is only the first filter. Each result is scored for upfront cash, monthly carrying cost, and—when it is a rental—DSCR, cash flow, cap rate, and cash-on-cash return."
        action={<button className="primary-button" onClick={() => setShowBuilder((open) => !open)}>{showBuilder ? "Close builder" : "+ New saved scan"}</button>}
      />

      {provider ? (
        <div className={`mt-6 flex flex-col justify-between gap-3 rounded-xl border px-4 py-3 sm:flex-row sm:items-center ${provider.mode === "live" ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
          <div className="flex items-center gap-3">
            <Pill tone={provider.mode === "live" ? "green" : "amber"}>{provider.mode === "live" ? "Live data" : "Demo data"}</Pill>
            <p className="text-xs leading-5 text-slate-600">{provider.detail}</p>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Provider: {provider.provider}</span>
        </div>
      ) : null}
      {error ? <div className="mt-4"><ErrorNotice>{error}</ErrorNotice></div> : null}

      {showBuilder ? (
        <Panel className="mt-6 overflow-hidden">
          <form onSubmit={createSearch}>
            <div className="border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold text-slate-950">Build a saved scan</h2>
              <p className="mt-1 text-xs text-slate-500">Leave max price blank to use your calculated comfortable maximum.</p>
            </div>
            <div className="grid gap-5 p-5 lg:grid-cols-4">
              <label><FieldLabel>Search name</FieldLabel><input className="product-input" value={name} onChange={(event) => setName(event.target.value)} required /></label>
              <label className="lg:col-span-2"><FieldLabel>Fairfield County, city/state, ZIP or address</FieldLabel><input className="product-input" value={criteria.location} onChange={(event) => setCriteria({ ...criteria, location: event.target.value })} placeholder="Fairfield County, CT or 06830" required /></label>
              <label><FieldLabel>Address radius</FieldLabel><span className="relative block"><input className="product-input pr-12" type="number" min={1} max={100} value={criteria.radius_miles} onChange={(event) => setCriteria({ ...criteria, radius_miles: Number(event.target.value) })} /><span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">miles</span></span><span className="mt-1 block text-[10px] text-slate-400">Used for street-address searches</span></label>
              {criteria.location.trim().toLowerCase().replace(/\s+/g, " ") === "fairfield county, ct" ? <div className="lg:col-span-4 -mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700">Fairfield County preset: results are searched geographically, then strictly filtered to Fairfield County, Connecticut.</div> : null}
              <div className="lg:col-span-2">
                <FieldLabel>Buying goal</FieldLabel>
                <div className="grid grid-cols-2 gap-2">
                  {(["primary", "investment"] as const).map((purpose) => (
                    <button type="button" key={purpose} onClick={() => setCriteria({ ...criteria, purpose })} className={`rounded-xl border px-4 py-3 text-left ${criteria.purpose === purpose ? "border-[#2d6a4f] bg-[#eff6f1] ring-1 ring-[#2d6a4f]" : "border-slate-200"}`}>
                      <div className="text-xs font-semibold text-slate-900">{purpose === "primary" ? "Primary home" : "Rental investment"}</div>
                      <div className="mt-1 text-[10px] text-slate-500">{purpose === "primary" ? "Budget and housing cost" : "Yield and cash flow"}</div>
                    </button>
                  ))}
                </div>
              </div>
              <label><FieldLabel>Minimum price</FieldLabel><MoneyField value={criteria.min_price} onChange={(value) => setCriteria({ ...criteria, min_price: value })} /></label>
              <label><FieldLabel>Maximum price</FieldLabel><MoneyField value={criteria.max_price} onChange={(value) => setCriteria({ ...criteria, max_price: value })} placeholder="Use my range" /></label>
              <label><FieldLabel>Minimum bedrooms</FieldLabel><input className="product-input" type="number" min={0} step={1} value={criteria.min_bedrooms} onChange={(event) => setCriteria({ ...criteria, min_bedrooms: Number(event.target.value) })} /></label>
              <label><FieldLabel>Minimum bathrooms</FieldLabel><input className="product-input" type="number" min={0} step={0.5} value={criteria.min_bathrooms} onChange={(event) => setCriteria({ ...criteria, min_bathrooms: Number(event.target.value) })} /></label>
              <label><FieldLabel>Max days on market</FieldLabel><input className="product-input" type="number" min={1} value={criteria.max_days_on_market ?? ""} onChange={(event) => setCriteria({ ...criteria, max_days_on_market: event.target.value ? Number(event.target.value) : null })} /></label>
              <label><FieldLabel>Minimum match score</FieldLabel><input className="product-input" type="number" min={0} max={100} value={criteria.min_match_score} onChange={(event) => setCriteria({ ...criteria, min_match_score: Number(event.target.value) })} /></label>
              <div className="lg:col-span-2">
                <FieldLabel>Property types</FieldLabel>
                <div className="flex flex-wrap gap-2">
                  {["Single Family", "Condo", "Townhouse", "Multi-Family"].map((propertyType) => {
                    const checked = criteria.property_types.includes(propertyType);
                    return <button type="button" key={propertyType} onClick={() => setCriteria({ ...criteria, property_types: checked ? criteria.property_types.filter((item) => item !== propertyType) : [...criteria.property_types, propertyType] })} className={`rounded-full border px-3 py-2 text-[11px] font-semibold ${checked ? "border-[#2d6a4f] bg-[#eff6f1] text-[#1f5b43]" : "border-slate-200 text-slate-500"}`}>{propertyType}</button>;
                  })}
                </div>
              </div>
              {criteria.purpose === "investment" ? (
                <div className="grid gap-4 border-t border-slate-100 pt-5 lg:col-span-4 lg:grid-cols-4">
                  <label><FieldLabel>Min DSCR (optional)</FieldLabel><NullableNumber value={criteria.min_dscr} onChange={(value) => setCriteria({ ...criteria, min_dscr: value })} placeholder="Profile default" /></label>
                  <label><FieldLabel>Min cap rate %</FieldLabel><PercentField value={criteria.min_cap_rate} onChange={(value) => setCriteria({ ...criteria, min_cap_rate: value })} /></label>
                  <label><FieldLabel>Min cash-on-cash %</FieldLabel><PercentField value={criteria.min_cash_on_cash} onChange={(value) => setCriteria({ ...criteria, min_cash_on_cash: value })} /></label>
                  <label><FieldLabel>Min monthly cash flow</FieldLabel><MoneyField value={criteria.min_monthly_cashflow} onChange={(value) => setCriteria({ ...criteria, min_monthly_cashflow: value })} placeholder="Profile default" /></label>
                </div>
              ) : null}
            </div>
            <div className="flex flex-col justify-between gap-4 border-t border-slate-200 bg-slate-50 px-5 py-4 sm:flex-row sm:items-center">
              <label className="flex items-start gap-3 text-xs text-slate-600">
                <input className="mt-0.5 size-4 accent-[#2d6a4f]" type="checkbox" checked={notifications} onChange={(event) => setNotifications(event.target.checked)} />
                <span><strong className="block text-slate-800">Notify me about new matches</strong>Send to {user.email} when email delivery is configured.</span>
              </label>
              <button className="primary-button">Save scan</button>
            </div>
          </form>
        </Panel>
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-[290px_1fr]">
        <aside>
          <Panel className="overflow-hidden lg:sticky lg:top-24">
            <div className="border-b border-slate-200 px-4 py-3 text-xs font-semibold text-slate-700">Saved scans</div>
            {searches.length ? <div className="divide-y divide-slate-100">{searches.map((search) => (
              <button key={search.id} onClick={() => { setSelectedId(search.id); setScanResult(null); }} className={`w-full px-4 py-4 text-left ${selectedId === search.id ? "bg-[#eff6f1]" : "hover:bg-slate-50"}`}>
                <div className="flex items-start justify-between gap-2"><span className="text-xs font-semibold text-slate-900">{search.name}</span><span className={`mt-1 size-1.5 rounded-full ${search.notifications_enabled ? "bg-emerald-500" : "bg-slate-300"}`} /></div>
                <div className="mt-1.5 text-[10px] leading-4 text-slate-500">{search.criteria.location} · {search.criteria.min_bedrooms}+ bd<br />{search.criteria.purpose === "primary" ? "Primary home" : "Rental investment"}</div>
              </button>
            ))}</div> : <div className="p-5 text-xs leading-5 text-slate-500">Create a saved scan to begin.</div>}
          </Panel>
        </aside>

        <section className="min-w-0">
          {selected ? (
            <>
              <Panel className="p-5">
                <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                  <div>
                    <div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold tracking-tight text-slate-950">{selected.name}</h2><Pill tone={selected.criteria.purpose === "primary" ? "green" : "amber"}>{selected.criteria.purpose === "primary" ? "Primary" : "Investment"}</Pill></div>
                    <p className="mt-1 text-xs text-slate-500">{selected.criteria.location} · {selected.criteria.min_bedrooms}+ bedrooms · max {selected.criteria.max_price ? formatCurrency(selected.criteria.max_price) : "calculated range"}</p>
                    {selected.last_scanned_at ? <p className="mt-1 text-[10px] text-slate-400">Last scanned {new Date(selected.last_scanned_at).toLocaleString()}</p> : null}
                  </div>
                  <div className="flex gap-2">
                    <button className="secondary-button text-rose-600" onClick={() => void removeSearch(selected.id)}>Delete</button>
                    <button className="primary-button" onClick={() => void runScan()} disabled={scanning}>{scanning ? "Scanning…" : "Run scan"}</button>
                  </div>
                </div>
              </Panel>

              {scanResult ? (
                <div className="mt-4 flex flex-col justify-between gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 sm:flex-row sm:items-center">
                  <p className="text-xs text-sky-800">Scanned {scanResult.total_scanned} listings · {scanResult.new_match_count} new matches · {scanResult.notification_status}</p>
                  <Pill tone={scanResult.provider_mode === "live" ? "green" : "amber"}>{scanResult.provider_mode}</Pill>
                </div>
              ) : null}

              <div className="mt-5 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-slate-700">{matches.length} stored result{matches.length === 1 ? "" : "s"}</div>
                <div className="flex rounded-lg border border-slate-200 bg-white p-1">
                  {(["all", "strong", "possible"] as const).map((value) => <button key={value} className={`rounded-md px-3 py-1.5 text-[10px] font-semibold capitalize ${filter === value ? "bg-slate-900 text-white" : "text-slate-500"}`} onClick={() => setFilter(value)}>{value}</button>)}
                </div>
              </div>

              {visibleMatches.length ? (
                <div className="mt-4 grid gap-4 xl:grid-cols-2">{visibleMatches.map((match) => <MatchCard key={match.listing.id} match={match} purpose={selected.criteria.purpose} providerMode={provider?.mode ?? "demo"} />)}</div>
              ) : (
                <Panel className="mt-4 px-6 py-14 text-center">
                  <div className="text-sm font-semibold text-slate-800">{matches.length ? "No results in this view" : "Ready for your first scan"}</div>
                  <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-slate-500">{matches.length ? "Try viewing all stored results." : "Run the scan to fetch listings, calculate carrying costs, and rank matches."}</p>
                  {!matches.length ? <button className="primary-button mt-5" onClick={() => void runScan()} disabled={scanning}>{scanning ? "Scanning…" : "Run scan"}</button> : null}
                </Panel>
              )}
            </>
          ) : (
            <Panel className="px-6 py-16 text-center"><div className="text-sm font-semibold text-slate-800">Create a saved scan to begin</div></Panel>
          )}
        </section>
      </div>
    </main>
  );
}

function MatchCard({ match, purpose, providerMode }: Readonly<{ match: PropertyMatch; purpose: "primary" | "investment"; providerMode: "demo" | "live" }>) {
  const tone = match.verdict === "strong" ? "green" : match.verdict === "possible" ? "amber" : "neutral";
  return (
    <Panel className="overflow-hidden">
      <div className={`h-1 ${match.verdict === "strong" ? "bg-emerald-500" : match.verdict === "possible" ? "bg-amber-400" : "bg-slate-300"}`} />
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-950">{match.listing.address}</div><div className="mt-1 text-[11px] text-slate-500">{match.listing.property_type} · {match.listing.bedrooms} bd · {match.listing.bathrooms} ba{match.listing.square_feet ? ` · ${match.listing.square_feet.toLocaleString()} sf` : ""}</div></div>
          <div className="shrink-0 text-right"><div className="text-lg font-semibold tracking-tight text-slate-950">{formatCurrency(match.listing.price)}</div><Pill tone={tone}>{match.score}/100</Pill></div>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2">
          <SmallMetric label="Cash needed" value={formatCurrency(match.metrics.cash_required)} />
          {purpose === "primary" ? (
            <><SmallMetric label="All-in / mo" value={formatCurrency(match.metrics.total_monthly_housing_cost)} /><SmallMetric label="Days listed" value={String(match.listing.days_on_market ?? "—")} /></>
          ) : (
            <><SmallMetric label="Cash flow / mo" value={match.metrics.monthly_cashflow === null ? "—" : formatCurrency(match.metrics.monthly_cashflow)} /><SmallMetric label="DSCR" value={match.metrics.dscr?.toFixed(2) ?? "—"} /></>
          )}
        </div>
        {purpose === "investment" ? <div className="mt-2 grid grid-cols-3 gap-2"><SmallMetric label="Rent estimate" value={match.metrics.projected_monthly_rent === null ? "—" : formatCurrency(match.metrics.projected_monthly_rent)} /><SmallMetric label="Cap rate" value={match.metrics.cap_rate === null ? "—" : formatPct(match.metrics.cap_rate, 1)} /><SmallMetric label="Cash-on-cash" value={match.metrics.cash_on_cash === null ? "—" : formatPct(match.metrics.cash_on_cash, 1)} /></div> : null}
        <div className="mt-4 border-t border-slate-100 pt-4">
          {match.reasons.slice(0, 2).map((reason) => <div key={reason} className="mt-1 flex gap-2 text-[11px] leading-4 text-emerald-700"><span>✓</span><span>{reason}</span></div>)}
          {match.warnings.slice(0, 2).map((warning) => <div key={warning} className="mt-1 flex gap-2 text-[11px] leading-4 text-amber-700"><span>!</span><span>{warning}</span></div>)}
        </div>
        {providerMode === "demo" ? <div className="mt-4 text-[9px] font-bold uppercase tracking-[0.15em] text-slate-300">Illustrative listing · not a real property</div> : null}
      </div>
    </Panel>
  );
}

function SmallMetric({ label, value }: Readonly<{ label: string; value: string }>) { return <div className="rounded-lg bg-slate-50 p-2.5"><div className="text-[9px] uppercase tracking-wide text-slate-400">{label}</div><div className="mt-1 truncate text-xs font-semibold text-slate-800">{value}</div></div>; }
function FieldLabel({ children }: Readonly<{ children: React.ReactNode }>) { return <span className="mb-1.5 block text-xs font-semibold text-slate-700">{children}</span>; }
function MoneyField({ value, onChange, placeholder }: Readonly<{ value: number | null; onChange: (value: number | null) => void; placeholder?: string }>) { return <span className="relative block"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">$</span><input className="product-input pl-7" type="number" min={0} value={value ?? ""} placeholder={placeholder} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)} /></span>; }
function NullableNumber({ value, onChange, placeholder }: Readonly<{ value: number | null; onChange: (value: number | null) => void; placeholder?: string }>) { return <input className="product-input" type="number" value={value ?? ""} placeholder={placeholder} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)} />; }
function PercentField({ value, onChange }: Readonly<{ value: number | null; onChange: (value: number | null) => void }>) { return <span className="relative block"><input className="product-input pr-8" type="number" step={0.1} value={value === null ? "" : value * 100} placeholder="Profile default" onChange={(event) => onChange(event.target.value ? Number(event.target.value) / 100 : null)} /><span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">%</span></span>; }
