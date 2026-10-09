"use client";

import { useEffect, useState } from "react";
import {
  api, type AcquisitionRun, type AcquisitionSearch, type ForecastProperty,
  type ForecastResult, type GateEvidence, type StrDeal,
} from "@/lib/api";
import { Panel } from "@/components/ProductUI";

const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
const unknownGate: GateEvidence = { status: "unknown" };

function EvidenceForm({ label, value, onChange }: { label: string; value: GateEvidence; onChange: (g: GateEvidence) => void }) {
  return <fieldset className="space-y-2 rounded-lg border p-3">
    <legend className="px-1 text-sm font-semibold">{label}</legend>
    <label className="block text-xs">Decision
      <select className="mt-1 w-full rounded border p-2" value={value.status} onChange={e => onChange({ ...value, status: e.target.value as GateEvidence["status"] })}>
        <option value="unknown">Unknown / pending review</option><option value="verified">Written permission verified</option><option value="blocked">Prohibited</option>
      </select>
    </label>
    {value.status !== "unknown" && <>
      {(["document_reference", "authority", "checked_on", "valid_until"] as const).map(key => <label key={key} className="block text-xs">
        {({ document_reference: "Document URL or reference", authority: "Issuing authority / HOA", checked_on: "Reviewed on", valid_until: "Review valid until" })[key]}
        <input required type={key.endsWith("on") || key.endsWith("until") ? "date" : "text"} className="mt-1 w-full rounded border p-2" value={value[key] ?? ""} onChange={e => onChange({ ...value, [key]: e.target.value })} />
      </label>)}
      <label className="block text-xs">Conditions / permitted use
        <textarea className="mt-1 w-full rounded border p-2" value={value.notes ?? ""} onChange={e => onChange({ ...value, notes: e.target.value })} />
      </label>
    </>}
  </fieldset>;
}

export function StrEvidenceWorkspace({ deal, onDeal }: { deal: StrDeal; onDeal: (d: StrDeal) => void }) {
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [searches, setSearches] = useState<AcquisitionSearch[]>([]);
  const [selected, setSelected] = useState("");
  const [location, setLocation] = useState("Fairfield County, CT");
  const [maxPrice, setMaxPrice] = useState(400000);
  const [enabled, setEnabled] = useState(false);
  const [run, setRun] = useState<AcquisitionRun | null>(null);
  const [subject, setSubject] = useState<ForecastProperty | null>(null);
  const [municipality, setMunicipality] = useState<GateEvidence>(unknownGate);
  const [hoa, setHoa] = useState<GateEvidence>(unknownGate);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    api.strAcquisitions().then(x => { if (active) setSearches(x); }).catch(e => { if (active) setError(String(e)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    if (deal.forecast_snapshot_id) api.strForecast(deal.forecast_snapshot_id).then(x => { if (active) setForecast(x); }).catch(e => { if (active) { setForecast(null); setError(String(e)); } });
    else setForecast(null);
    return () => { active = false; };
  }, [deal.forecast_snapshot_id]);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await work(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function importFile(file: File) {
    if (file.size > 1_000_000) throw new Error("Forecast export exceeds the 1 MB upload limit.");
    const imported = await api.importStrForecast(JSON.parse(await file.text()));
    setForecast(imported);
    if (imported.forecast) {
      setSubject(imported.forecast.property);
      setMunicipality(unknownGate); setHoa(unknownGate);
      setNotice("Snapshot imported. Review its source and comparables before attaching it to this scenario.");
    }
  }
  async function saveSearch() {
    const payload = { name: `${location} STR acquisitions`, criteria: { location, max_price: maxPrice }, deal_template: deal, enabled };
    const saved = selected ? await api.updateStrAcquisition(selected, payload) : await api.saveStrAcquisition(payload);
    setSelected(saved.id); setSearches(await api.strAcquisitions());
    setNotice("Search saved with this scenario’s cost and financing assumptions. Eligibility is reviewed per property.");
  }
  async function selectSearch(id: string) {
    setSelected(id); setRun(null);
    const search = searches.find(s => s.id === id);
    if (!search) return;
    setLocation(search.criteria.location ?? "Fairfield County, CT"); setMaxPrice(search.criteria.max_price ?? 400000); setEnabled(search.enabled);
    onDeal(search.deal_template);
    setRun((await api.strAcquisitionRuns(id))[0] ?? null);
  }
  async function saveGates() {
    if (!subject) return;
    await api.saveStrEligibility({ property: subject, municipality, hoa });
    if (subject.address.trim().toLowerCase() === deal.address.trim().toLowerCase()) {
      onDeal({ ...deal, regulatory_gate: municipality.status, hoa_gate: hoa.status, regulatory_evidence: municipality, hoa_evidence: hoa });
    }
    setNotice("Evidence saved. Run the scan again to apply the current eligibility review.");
  }

  return <div className="space-y-5">
    <Panel className="space-y-4 p-5">
      <h2 className="font-semibold">Licensed property forecast</h2>
      <p className="text-sm text-slate-600">Import a licensed property export only when your contract permits internal underwriting and retention. Market averages and RentCast long-term rent estimates cannot qualify. No vendor API or license is assumed.</p>
      <label className="block text-sm">Normalized forecast export (JSON)
        <input disabled={busy} type="file" accept="application/json,.json" className="mt-2 block w-full text-sm" onChange={e => { const file = e.target.files?.[0]; if (file) void action(() => importFile(file)); e.target.value = ""; }} />
      </label>
      {!forecast && <p className="text-sm">Unavailable: no property forecast attached. Manual scenarios remain research only.</p>}
      {forecast && <div className="space-y-3">
        <p className="text-sm font-semibold">{forecast.status.replaceAll("_", " ")}: {forecast.reason}</p>
        {forecast.forecast && <>
          <p className="text-sm">{forecast.forecast.property.address}</p>
          <p className="text-xs">{forecast.forecast.attribution} · {forecast.forecast.provider} · version {forecast.forecast.data_version}</p>
          <p className="text-xs">As of {forecast.forecast.as_of}; generated {forecast.forecast.generated_at}; imported {forecast.imported_at}; retain through {forecast.forecast.retention_until}.</p>
          <a className="text-sm underline" href={forecast.forecast.source_url} target="_blank" rel="noreferrer">Provider source</a>
          <p className="text-xs">{forecast.qualified_comparable_count} qualified comparables of {forecast.forecast.comparables.length}. {forecast.forecast.methodology}</p>
          <details className="text-xs"><summary className="cursor-pointer">Comparable-property evidence</summary>
            <div className="overflow-auto"><table className="mt-2 w-full text-left"><thead><tr><th>Source</th><th>Type / beds</th><th>Distance</th><th>Observed revenue</th><th>Period / exclusions</th></tr></thead><tbody>
              {forecast.forecast.comparables.map(c => <tr key={c.provider_property_id} className="border-t"><td className="py-2"><a className="underline" href={c.source_url} target="_blank" rel="noreferrer">{c.provider_property_id}</a></td><td>{c.property_type} / {c.bedrooms}</td><td>{c.distance_miles} mi</td><td>{money(c.gross_revenue)}</td><td>{c.period_start}–{c.period_end}; {c.exclusion_reason ?? (c.owner_blocked_nights ? "Owner-blocked nights" : "See qualification rules")}</td></tr>)}
            </tbody></table></div>
          </details>
          <button disabled={busy || forecast.status !== "available"} className="primary-button" onClick={() => {
            if (!forecast.forecast) return;
            const days = Array<number>(12).fill(0);
            for (const m of forecast.forecast.months) {
              const [year, month] = m.month.split("-").map(Number);
              days[month - 1] = new Date(year, month, 0).getDate();
            }
            onDeal({ ...deal, address: forecast.forecast.property.address, forecast_snapshot_id: forecast.snapshot_id,
              revenue_source: "licensed_property_forecast", monthly_calendar_days: days,
              regulatory_gate: "unknown", hoa_gate: "unknown", regulatory_evidence: null, hoa_evidence: null });
            setSubject(forecast.forecast.property);
            setMunicipality(unknownGate); setHoa(unknownGate);
          }}>Attach validated snapshot</button>
        </>}
      </div>}
      {deal.forecast_snapshot_id && <button className="rounded border p-2 text-sm" onClick={() => onDeal({ ...deal, forecast_snapshot_id: null, revenue_source: "assumption", forecast_as_of: null, comparable_count: 0 })}>Return to manual assumptions</button>}
    </Panel>

    <Panel className="space-y-4 p-5">
      <h2 className="font-semibold">Automated acquisition scans</h2>
      <p className="text-sm text-slate-600">Combine live RentCast sale listings with validated STR snapshots. Every candidate needs current written municipality and HOA/deed permission. Only candidates passing those gates and the financial stress screen receive a rank.</p>
      <label className="block text-sm">Saved acquisition search<select disabled={busy} className="mt-1 w-full rounded border p-2" value={selected} onChange={e => void action(() => selectSearch(e.target.value))}><option value="">New search</option>{searches.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Market / ZIP / address<input className="mt-1 w-full rounded border p-2" value={location} onChange={e => setLocation(e.target.value)} /></label>
        <label className="text-sm">Maximum acquisition price<input type="number" min="1" className="mt-1 w-full rounded border p-2" value={maxPrice} onChange={e => setMaxPrice(Number(e.target.value))} /></label>
      </div>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />Include in scheduled scans (requires an operator-installed schedule)</label>
      <div className="flex flex-wrap gap-2">
        <button disabled={busy} className="primary-button" onClick={() => void action(saveSearch)}>{selected ? "Update" : "Save"} search with current scenario assumptions</button>
        <button disabled={busy || !selected} className="rounded border p-2 text-sm" onClick={() => void action(async () => { setRun(await api.scanStrAcquisition(selected)); })}>Scan saved search now</button>
        <button disabled={busy || !selected} className="rounded border p-2 text-sm" onClick={() => void action(async () => { await api.deleteStrAcquisition(selected); setSelected(""); setRun(null); setSearches(await api.strAcquisitions()); })}>Delete search</button>
      </div>
      {run && <div className="space-y-3"><p className="text-sm">{run.status} · {run.scanned_at}. {run.detail} Historical results reflect evidence at scan time; rescan before using them.</p>
        {run.candidates.map(c => <div key={c.listing.id} className="space-y-2 rounded-lg border p-3">
          <p className="font-semibold">{c.rank ? `#${c.rank} · ` : ""}{c.listing.address} · {money(c.listing.price)}</p>
          <p className="text-sm">{c.status.replaceAll("_", " ")} · Forecast: {c.forecast_status.replaceAll("_", " ")}</p>
          <p className="text-xs">{c.provider_attribution ?? c.forecast_reason}{c.forecast_as_of && ` · as of ${c.forecast_as_of}`}</p>
          {c.reasons.map(r => <p key={r} className="text-xs text-slate-600">{r}</p>)}
          {c.underwriting && <p className="text-sm">Cash flow {money(c.underwriting.annual_cash_flow)} · −20% bookings {money(c.underwriting.downside_cash_flow)} · DSCR {c.underwriting.debt_service_coverage?.toFixed(2) ?? "Cash"}</p>}
          <button className="rounded border p-2 text-xs" onClick={() => { setSubject({ address: c.listing.address, property_type: c.listing.property_type, bedrooms: c.listing.bedrooms, bathrooms: c.listing.bathrooms, provider_property_id: c.listing.id }); setMunicipality(c.municipality); setHoa(c.hoa); }}>Review written eligibility</button>
          {c.snapshot_id && <button className="ml-2 rounded border p-2 text-xs" disabled={busy} onClick={() => void action(async () => { setForecast(await api.strForecast(c.snapshot_id!)); })}>Inspect forecast evidence</button>}
        </div>)}
        {run.status === "completed" && run.candidates.length === 0 && <p className="text-sm">No sale listings matched this search. No projections were substituted.</p>}
      </div>}
    </Panel>

    {subject && <Panel className="space-y-3 p-5"><h2 className="font-semibold">Written eligibility: {subject.address}</h2><p className="text-sm">Record a property-specific review and all operating conditions. An expired permission becomes unknown; a prohibition stays blocked. This record is your legal review, not an automated legal determination.</p>
      <div className="grid gap-3 sm:grid-cols-2"><EvidenceForm label="Municipality" value={municipality} onChange={setMunicipality} /><EvidenceForm label="HOA / deed restrictions" value={hoa} onChange={setHoa} /></div>
      <button disabled={busy} className="primary-button" onClick={() => void action(saveGates)}>Save eligibility evidence</button>
    </Panel>}
    {busy && <p role="status" className="text-sm">Working…</p>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </div>;
}
