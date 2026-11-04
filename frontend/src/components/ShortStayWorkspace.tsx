"use client";

import { useEffect, useState } from "react";
import { api, type StrDeal, type StrResults, type StrScenario } from "@/lib/api";
import { Panel, WorkspaceIntro } from "@/components/ProductUI";
import { StrEvidenceWorkspace } from "@/components/StrEvidenceWorkspace";

const base: StrDeal = {
  name: "Northeast cabin", address: "Lake Harmony, PA", strategy: "investment",
  property_price: 350000, down_payment_pct: .25, mortgage_apr: .08, loan_term_years: 30,
  closing_cost_pct: .05, furnishings: 25000, cash_reserve: 15000, annual_gross_revenue: 60000,
  revenue_source: "assumption", forecast_as_of: null, comparable_count: 0, monthly_gross_revenue: null,
  owner_nights: 0, owner_nights_by_month: null, property_tax_annual: 6000, insurance_annual: 3600,
  utilities_annual: 4800, property_services_annual: 2500, repairs_capex_annual: 5000, hoa_annual: 0,
  management_pct: .20, platform_pct: .08, turnovers_pct: .12, regulatory_gate: "unknown", hoa_gate: "unknown",
  refinance_after_months: 24, refinance_apr: .055, refinance_fees: 0,
};
const fmt = (n: number | null) => n === null ? "Unavailable" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
const numericFields: [keyof StrDeal, string, boolean?][] = [
  ["property_price", "Purchase price"], ["down_payment_pct", "Down payment", true],
  ["mortgage_apr", "Mortgage rate", true], ["loan_term_years", "Loan term (years)"],
  ["closing_cost_pct", "Closing and transfer taxes", true], ["furnishings", "Furniture / setup"],
  ["cash_reserve", "Retained reserve"], ["annual_gross_revenue", "Gross annual accommodation revenue"],
  ["owner_nights", "Personal nights"], ["property_tax_annual", "Annual property tax"],
  ["insurance_annual", "Annual insurance"], ["utilities_annual", "Annual utilities"],
  ["property_services_annual", "Snow / landscaping"], ["repairs_capex_annual", "Maintenance and capex reserve"],
  ["hoa_annual", "Annual HOA dues"], ["management_pct", "Manager fee", true],
  ["platform_pct", "Platform fee", true], ["turnovers_pct", "Cleaning and supplies expense", true],
  ["refinance_apr", "Future refinance rate", true], ["refinance_after_months", "Refinance after months"],
  ["refinance_fees", "Refinance fees"], ["comparable_count", "Self-reported comparable count"],
];

export function ShortStayWorkspace() {
  const [deal, setDeal] = useState<StrDeal>(base);
  const [result, setResult] = useState<StrResults | null>(null);
  const [saved, setSaved] = useState<StrScenario[]>([]);
  const [selected, setSelected] = useState("");
  const [calculationError, setCalculationError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api.strScenarios().then(x => { if (active) setSaved(x); }).catch(e => { if (active) setSaveError(String(e)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setResult(null);
    const timer = setTimeout(() => {
      api.underwriteStr(deal).then(r => { if (active) { setResult(r); setCalculationError(""); } })
        .catch(e => { if (active) { setResult(null); setCalculationError(String(e)); } });
    }, 300);
    return () => { active = false; clearTimeout(timer); };
  }, [deal]);
  const change = <K extends keyof StrDeal>(key: K, value: StrDeal[K]) => setDeal(d => ({ ...d, [key]: value }));
  async function persist() {
    setSaving(true); setSaveError("");
    try {
      const x = selected ? await api.updateStrScenario(selected, { name: deal.name, deal }) : await api.saveStrScenario({ name: deal.name, deal });
      setSelected(x.id); setSaved(await api.strScenarios());
    } catch (e) { setSaveError(String(e)); } finally { setSaving(false); }
  }
  async function remove() {
    setSaving(true); setSaveError("");
    try { await api.deleteStrScenario(selected); setSelected(""); setDeal(base); setSaved(await api.strScenarios()); }
    catch (e) { setSaveError(String(e)); } finally { setSaving(false); }
  }
  const attached = Boolean(deal.forecast_snapshot_id);
  const revenueKeys = new Set<keyof StrDeal>(["annual_gross_revenue", "comparable_count"]);

  return <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-8">
    <WorkspaceIntro eyebrow="Investment research" title="Short-term rental underwriting" description="Model investment cabins or personal-use hybrids. Property forecasts require licensed evidence; every acquisition needs municipality and HOA/deed permission. A passing screen is not purchase approval." />
    <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
      <div className="space-y-5">
        <Panel className="space-y-4 p-5"><h2 className="font-semibold">Scenario and property</h2>
          <label className="block text-sm">Saved scenario<select className="mt-1 w-full rounded-lg border p-2" value={selected} onChange={e => { setSelected(e.target.value); const x = saved.find(x => x.id === e.target.value); setDeal(x?.deal ?? base); }}><option value="">New scenario</option>{saved.map(s => <option key={s.id} value={s.id}>{s.name}: {s.deal.address}</option>)}</select></label>
          {(["name", "address"] as const).map(key => <label key={key} className="block text-sm">{key}<input className="mt-1 w-full rounded-lg border p-2" value={deal[key]} onChange={e => key === "address" ? setDeal(d => ({ ...d, address: e.target.value, forecast_snapshot_id: null, regulatory_evidence: null, hoa_evidence: null, regulatory_gate: "unknown", hoa_gate: "unknown" })) : change(key, e.target.value)} /></label>)}
          <div className="flex gap-2"><button disabled={saving} className="primary-button" onClick={() => void persist()}>{selected ? "Update" : "Save"} scenario</button><button className="rounded-lg border p-2 text-sm" onClick={() => { setSelected(""); setDeal(base); }}>New</button><button disabled={saving || !selected} className="rounded-lg border p-2 text-sm" onClick={() => void remove()}>Delete scenario</button></div>
          {saveError && <p role="alert" className="text-sm text-red-700">{saveError}</p>}
        </Panel>
        <Panel className="space-y-4 p-5"><h2 className="font-semibold">Economics and operations</h2>
          <label className="block text-sm">Ownership purpose<select className="mt-1 w-full rounded-lg border p-2" value={deal.strategy} onChange={e => setDeal(d => ({ ...d, strategy: e.target.value as StrDeal["strategy"], owner_nights: 0, owner_nights_by_month: null }))}><option value="investment">Investment-first</option><option value="hybrid">Hybrid personal use</option></select></label>
          {attached && <p className="text-sm">Revenue and seasonality come from the attached immutable snapshot. Inspect its dated evidence below. Cost and financing inputs remain editable.</p>}
          <div className="grid gap-3 sm:grid-cols-2">{numericFields.filter(([key]) => (deal.strategy === "hybrid" || key !== "owner_nights") && (!attached || !revenueKeys.has(key))).map(([key, label, percent]) => <label className="text-xs font-medium text-slate-600" key={key}>{label}{percent ? " (%)" : ""}<input type="number" min="0" step={percent ? ".25" : "1"} className="mt-1 w-full rounded-lg border p-2 text-sm" value={Number(deal[key] ?? 0) * (percent ? 100 : 1)} onChange={e => setDeal(d => ({ ...d, [key]: Number(e.target.value) / (percent ? 100 : 1), ...(key === "owner_nights" ? { owner_nights_by_month: null } : {}) }))} /></label>)}</div>
          {!attached && <>
            <label className="block text-sm">Self-reported revenue provenance<select className="mt-1 w-full rounded-lg border p-2" value={deal.revenue_source} onChange={e => change("revenue_source", e.target.value as StrDeal["revenue_source"])}><option value="assumption">Manual assumption</option><option value="market_average">Market average (research only)</option><option value="licensed_property_forecast">Self-reported licensed forecast (import required)</option><option value="actual_operations">Self-reported actual operations (research only)</option></select></label>
            <label className="block text-sm">Evidence date<input type="date" className="mt-1 w-full rounded-lg border p-2" value={deal.forecast_as_of ?? ""} onChange={e => change("forecast_as_of", e.target.value || null)} /></label>
          </>}
          <p className="text-xs">Revenue excludes cleaning-fee income and guest taxes. Personal nights are calendar-month blocks; displacement assumes uniform demand within each month.</p>
          <div className="grid grid-cols-3 gap-2">{Array.from({ length: 12 }, (_, i) => {
            const values = deal.monthly_gross_revenue ?? Array<number>(12).fill(deal.annual_gross_revenue / 12);
            const nights = deal.owner_nights_by_month ?? Array<number>(12).fill(0);
            return <div key={i} className="rounded-lg border p-2"><p className="text-xs">{new Date(2026, i, 1).toLocaleString("en-US", { month: "short" })}</p>
              {!attached && <input aria-label={`Revenue month ${i + 1}`} type="number" min="0" className="w-full text-xs" value={Math.round(values[i])} onChange={e => { const x = [...values]; x[i] = Number(e.target.value); change("monthly_gross_revenue", x); }} />}
              {deal.strategy === "hybrid" && <><span className="text-[10px]">Owner nights</span><input aria-label={`Owner nights month ${i + 1}`} type="number" min="0" className="w-full text-xs" value={nights[i]} onChange={e => { const x = [...nights]; x[i] = Number(e.target.value); setDeal(d => ({ ...d, owner_nights_by_month: x, owner_nights: x.reduce((a, b) => a + b, 0) })); }} /></>}
            </div>;
          })}</div>
          {!attached && <button className="rounded-lg border p-2 text-xs" onClick={() => change("monthly_gross_revenue", null)}>Clear monthly assumptions</button>}
        </Panel>
      </div>
      <div className="space-y-5"><Panel className="space-y-4 p-5"><h2 className="font-semibold">Underwriting results</h2>
        {calculationError && <p role="alert" className="text-sm text-red-700">{calculationError}</p>}
        {result && <><div className="rounded-xl bg-slate-100 p-4"><p className="text-xs">Annual cash flow after mortgage</p><p className="text-3xl font-bold">{fmt(result.annual_cash_flow)}</p><p className="text-xs">{result.screening_status.replaceAll("_", " ")}</p></div>
          <div className="grid grid-cols-2 gap-4">{[
            ["Gross after personal use", fmt(result.annual_gross_after_owner_use)], ["Foregone rent", fmt(result.foregone_owner_revenue)],
            ["Reserve-adjusted NOI", fmt(result.annual_noi)], ["Debt service", fmt(result.annual_debt_service)],
            ["Invested + reserves", fmt(result.capital_required_including_reserves)], ["Cash-on-cash", result.cash_on_cash === null ? "Undefined" : (result.cash_on_cash * 100).toFixed(1) + "%"],
            ["DSCR", result.debt_service_coverage?.toFixed(2) ?? "Cash"], ["−20% bookings", fmt(result.downside_cash_flow)],
            ["Cash-flow breakeven", result.break_even_gross_before_owner_use === null ? "No finite breakeven" : fmt(result.break_even_gross_before_owner_use)],
            ["Illustrative refinance cash flow", fmt(result.future_refinanced_annual_cash_flow)], ["Balance at refinance", fmt(result.refinance_remaining_principal)],
            ["Refinance remaining term", `${result.refinance_remaining_term_months} months`],
          ].map(([label, value]) => <div key={label}><p className="text-xs text-slate-500">{label}</p><p className="font-semibold">{value}</p></div>)}</div>
        </>}
      </Panel>
        {result && <Panel className="space-y-2 p-5"><h2 className="font-semibold">Evidence and limitations</h2>{result.warnings.map((warning, i) => <p className="text-sm text-slate-600" key={i}>{warning}</p>)}</Panel>}
      </div>
    </div>
    <StrEvidenceWorkspace deal={deal} onDeal={setDeal} />
  </main>;
}
