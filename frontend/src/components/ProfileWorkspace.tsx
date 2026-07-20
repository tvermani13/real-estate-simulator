"use client";

import { useEffect, useState } from "react";

import { api, type AffordabilityResponse, type FinancialProfile } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { ErrorNotice, LoadingBlock, Panel, Pill, WorkspaceIntro } from "@/components/ProductUI";

type NumericKey = { [K in keyof FinancialProfile]: FinancialProfile[K] extends number ? K : never }[keyof FinancialProfile];

export function ProfileWorkspace() {
  const [profile, setProfile] = useState<FinancialProfile | null>(null);
  const [plan, setPlan] = useState<AffordabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.profile(), api.affordability()])
      .then(([nextProfile, nextPlan]) => { setProfile(nextProfile); setPlan(nextPlan); })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setLoading(false));
  }, []);

  function updateNumber(key: NumericKey, value: number) {
    setProfile((current) => current ? { ...current, [key]: Number.isFinite(value) ? value : 0 } : current);
    setMessage(null);
  }

  async function save() {
    if (!profile) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api.saveProfile(profile);
      setPlan(await api.affordability());
      setMessage("Financial profile saved. Your ranges and property scores are updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading your financial profile…" />;
  if (!profile) return <main className="mx-auto max-w-5xl px-4 py-10"><ErrorNotice>{error ?? "Profile unavailable"}</ErrorNotice></main>;

  return (
    <main className="mx-auto max-w-[1240px] px-4 py-8 lg:px-8 lg:py-10">
      <WorkspaceIntro
        eyebrow="Financial foundation"
        title="Tell us what the property has to fit around."
        description="Use current, household-level numbers. We hold back an emergency reserve first, then test payment capacity and upfront cash separately."
        action={<button className="primary-button" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save and recalculate"}</button>}
      />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {error ? <ErrorNotice>{error}</ErrorNotice> : null}
          {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{message}</div> : null}

          <FormSection index="01" title="Income and monthly obligations" description="Use gross income for lender-style debt ratios and take-home income for your practical comfort limit.">
            <MoneyInput label="Annual gross household income" value={profile.annual_gross_income} onChange={(value) => updateNumber("annual_gross_income", value)} />
            <MoneyInput label="Monthly take-home income" value={profile.monthly_take_home_income} onChange={(value) => updateNumber("monthly_take_home_income", value)} />
            <MoneyInput label="Monthly debt payments" value={profile.monthly_debt_payments} onChange={(value) => updateNumber("monthly_debt_payments", value)} hint="Car, student, card, personal and other required debt" />
            <MoneyInput label="Monthly living expenses" value={profile.monthly_living_expenses} onChange={(value) => updateNumber("monthly_living_expenses", value)} hint="Excluding a future mortgage; include normal household spend" />
          </FormSection>

          <FormSection index="02" title="Assets, liquidity and liabilities" description="Liquid cash funds the purchase and protects you from forced selling. Investments still count toward net worth but are not assumed spendable.">
            <MoneyInput label="Cash and cash equivalents" value={profile.liquid_cash} onChange={(value) => updateNumber("liquid_cash", value)} />
            <MoneyInput label="Taxable investments" value={profile.taxable_investments} onChange={(value) => updateNumber("taxable_investments", value)} />
            <MoneyInput label="Retirement assets" value={profile.retirement_assets} onChange={(value) => updateNumber("retirement_assets", value)} />
            <MoneyInput label="Other assets" value={profile.other_assets} onChange={(value) => updateNumber("other_assets", value)} />
            <MoneyInput label="Total liabilities" value={profile.total_liabilities} onChange={(value) => updateNumber("total_liabilities", value)} />
            <NumberInput label="Credit score" value={profile.credit_score} min={300} max={850} step={1} onChange={(value) => updateNumber("credit_score", Math.round(value))} />
          </FormSection>

          <FormSection index="03" title="Risk and financing guardrails" description="These assumptions drive both the range calculator and every property score.">
            <div className="col-span-full">
              <div className="mb-2 text-xs font-semibold text-slate-700">Risk tolerance</div>
              <div className="grid gap-2 sm:grid-cols-3">
                {([
                  ["conservative", "Conservative", "More cash held back, lower debt ratios"],
                  ["balanced", "Balanced", "Middle-of-the-road payment and liquidity limits"],
                  ["growth", "Growth", "More capital deployed, higher payment ceiling"],
                ] as const).map(([value, title, copy]) => (
                  <button key={value} type="button" onClick={() => setProfile({ ...profile, risk_tolerance: value })} className={`rounded-xl border p-3 text-left transition ${profile.risk_tolerance === value ? "border-[#2d6a4f] bg-[#eff6f1] ring-1 ring-[#2d6a4f]" : "border-slate-200 hover:border-slate-300"}`}>
                    <div className="text-xs font-semibold text-slate-900">{title}</div>
                    <div className="mt-1 text-[10px] leading-4 text-slate-500">{copy}</div>
                  </button>
                ))}
              </div>
            </div>
            <NumberInput label="Emergency reserve (months)" value={profile.reserve_months} min={1} max={36} step={1} onChange={(value) => updateNumber("reserve_months", Math.round(value))} />
            <PercentInput label="Primary down payment" value={profile.primary_down_payment_pct} onChange={(value) => updateNumber("primary_down_payment_pct", value)} />
            <PercentInput label="Investment down payment" value={profile.investment_down_payment_pct} onChange={(value) => updateNumber("investment_down_payment_pct", value)} />
            <PercentInput label="Mortgage rate" value={profile.mortgage_rate} onChange={(value) => updateNumber("mortgage_rate", value)} />
            <NumberInput label="Mortgage term (years)" value={profile.mortgage_term_years} min={5} max={40} step={5} onChange={(value) => updateNumber("mortgage_term_years", Math.round(value))} />
            <PercentInput label="Property tax (annual)" value={profile.property_tax_rate} onChange={(value) => updateNumber("property_tax_rate", value)} />
            <PercentInput label="Home insurance (annual)" value={profile.home_insurance_rate} onChange={(value) => updateNumber("home_insurance_rate", value)} />
            <PercentInput label="Closing costs" value={profile.closing_cost_rate} onChange={(value) => updateNumber("closing_cost_rate", value)} />
            <MoneyInput label="Primary-home HOA (monthly)" value={profile.primary_hoa_monthly} onChange={(value) => updateNumber("primary_hoa_monthly", value)} />
          </FormSection>

          <FormSection index="04" title="Rental investment thresholds" description="Listings need to clear these operating assumptions before they are called a match.">
            <PercentInput label="Vacancy allowance" value={profile.investment_vacancy_rate} onChange={(value) => updateNumber("investment_vacancy_rate", value)} />
            <PercentInput label="Management allowance" value={profile.investment_management_rate} onChange={(value) => updateNumber("investment_management_rate", value)} />
            <PercentInput label="Maintenance allowance" value={profile.investment_maintenance_rate} onChange={(value) => updateNumber("investment_maintenance_rate", value)} />
            <PercentInput label="Capital expenditure allowance" value={profile.investment_capex_rate} onChange={(value) => updateNumber("investment_capex_rate", value)} />
            <NumberInput label="Minimum DSCR" value={profile.min_dscr} min={0} max={5} step={0.05} onChange={(value) => updateNumber("min_dscr", value)} />
            <PercentInput label="Minimum cash-on-cash return" value={profile.min_cash_on_cash} onChange={(value) => updateNumber("min_cash_on_cash", value)} />
            <MoneyInput label="Minimum monthly cash flow" value={profile.min_monthly_cashflow} onChange={(value) => updateNumber("min_monthly_cashflow", value)} />
          </FormSection>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <Panel className="overflow-hidden">
            <div className="bg-[#12372a] p-5 text-white">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-100/70">Live range preview</div>
              <div className="mt-4 text-xs text-emerald-50/70">Save to refresh calculations</div>
            </div>
            <div className="space-y-5 p-5">
              <RangeSummary label="Primary residence" value={plan?.primary.comfortable_max} stretch={plan?.primary.stretch_max} />
              <RangeSummary label="Rental investment" value={plan?.investment.comfortable_max} stretch={plan?.investment.stretch_max} />
              <div className="border-t border-slate-100 pt-4">
                <div className="flex items-center justify-between text-xs"><span className="text-slate-500">Protected reserves</span><strong className="text-slate-900">{formatCurrency(plan?.required_reserves ?? 0)}</strong></div>
                <div className="mt-3 flex items-center justify-between text-xs"><span className="text-slate-500">Cash after reserves</span><strong className="text-slate-900">{formatCurrency(plan?.investable_cash ?? 0)}</strong></div>
              </div>
              <Pill tone="neutral">Planning estimate · not pre-approval</Pill>
            </div>
          </Panel>
        </aside>
      </div>
    </main>
  );
}

function FormSection({ index, title, description, children }: Readonly<{ index: string; title: string; description: string; children: React.ReactNode }>) {
  return (
    <Panel className="overflow-hidden">
      <div className="flex gap-4 border-b border-slate-200 px-5 py-4">
        <span className="pt-0.5 text-[10px] font-bold text-[#2d6a4f]">{index}</span>
        <div><h2 className="text-sm font-semibold text-slate-950">{title}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{description}</p></div>
      </div>
      <div className="grid gap-4 p-5 sm:grid-cols-2">{children}</div>
    </Panel>
  );
}

function MoneyInput({ label, value, onChange, hint }: Readonly<{ label: string; value: number; onChange: (value: number) => void; hint?: string }>) {
  return <NumberInput label={label} value={value} step={100} prefix="$" onChange={onChange} hint={hint} />;
}

function PercentInput({ label, value, onChange }: Readonly<{ label: string; value: number; onChange: (value: number) => void }>) {
  const displayValue = Math.round(value * 10_000) / 100;
  return <NumberInput label={label} value={displayValue} step={0.1} suffix="%" onChange={(next) => onChange(next / 100)} />;
}

function NumberInput({ label, value, onChange, step = 1, min = 0, max, prefix, suffix, hint }: Readonly<{ label: string; value: number; onChange: (value: number) => void; step?: number; min?: number; max?: number; prefix?: string; suffix?: string; hint?: string }>) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-700">{label}</span>
      <span className="relative block">
        {prefix ? <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">{prefix}</span> : null}
        <input className={`product-input ${prefix ? "pl-7" : ""} ${suffix ? "pr-8" : ""}`} type="number" value={value} step={step} min={min} max={max} onChange={(event) => onChange(Number(event.target.value))} />
        {suffix ? <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">{suffix}</span> : null}
      </span>
      {hint ? <span className="mt-1 block text-[10px] leading-4 text-slate-400">{hint}</span> : null}
    </label>
  );
}

function RangeSummary({ label, value, stretch }: Readonly<{ label: string; value?: number; stretch?: number }>) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-[-0.035em] text-slate-950">{formatCurrency(value ?? 0)}</div>
      <div className="mt-1 text-[10px] text-slate-400">Comfortable max · stretch to {formatCurrency(stretch ?? 0)}</div>
    </div>
  );
}
