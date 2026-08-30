"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { formatCurrency, formatPct } from "@/lib/format";

type Inputs = {
  portfolioValue: number;
  costBasisPct: number;
  expectedReturn: number;
  volatility: number;
  maintenanceLtv: number;
  purchasePrice: number;
  downPayment: number;
  monthlyRent: number;
  monthlyExpenses: number;
  appreciation: number;
  capitalGainsTaxRate: number;
  sofrRate: number;
  brokerSpread: number;
};

const defaults: Inputs = {
  portfolioValue: 1_000_000,
  costBasisPct: 0.6,
  expectedReturn: 0.07,
  volatility: 0.28,
  maintenanceLtv: 0.65,
  purchasePrice: 900_000,
  downPayment: 350_000,
  monthlyRent: 5_600,
  monthlyExpenses: 2_300,
  appreciation: 0.03,
  capitalGainsTaxRate: 0.238,
  sofrRate: 0.052,
  brokerSpread: 0.02,
};

const riskHorizons = [12, 36, 60] as const;

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4_294_967_296;
  };
}

function normalSample(random: () => number) {
  const first = Math.max(random(), Number.EPSILON);
  const second = random();
  return Math.sqrt(-2 * Math.log(first)) * Math.cos(2 * Math.PI * second);
}

function estimateMarginRisk(inputs: Inputs) {
  const runs = 4_000;
  const random = seededRandom(42);
  const dangerValue = inputs.downPayment / inputs.maintenanceLtv;
  const breaches = [0, 0, 0];
  const drift = (inputs.expectedReturn - 0.5 * inputs.volatility ** 2) / 12;
  const diffusion = inputs.volatility / Math.sqrt(12);

  for (let run = 0; run < runs; run += 1) {
    let value = inputs.portfolioValue;
    let breached = false;
    let horizonIndex = 0;

    for (let month = 1; month <= riskHorizons.at(-1)!; month += 1) {
      value *= Math.exp(drift + diffusion * normalSample(random));
      breached ||= value <= dangerValue;

      if (month === riskHorizons[horizonIndex]) {
        if (breached) breaches[horizonIndex] += 1;
        horizonIndex += 1;
      }
    }
  }

  return riskHorizons.map((months, index) => ({
    label: `${months / 12}Y`,
    months,
    probability: breaches[index] / runs,
  }));
}

function InputField({
  label,
  value,
  onChange,
  step = 1_000,
  min = 0,
  suffix = "$",
}: Readonly<{
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
  suffix?: "$" | "%";
}>) {
  const shown = suffix === "%" ? Number((value * 100).toFixed(3)) : value;
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-600">
        {label}
        <span className="font-mono text-[11px] text-slate-400">{suffix === "$" ? formatCurrency(value) : `${shown.toFixed(1)}%`}</span>
      </span>
      <input
        aria-label={label}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-900 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        min={suffix === "%" ? min * 100 : min}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(suffix === "%" ? next / 100 : next);
        }}
        step={suffix === "%" ? step * 100 : step}
        type="number"
        value={shown}
      />
    </label>
  );
}

function Metric({ label, value, detail, tone = "slate" }: Readonly<{ label: string; value: string; detail: string; tone?: "slate" | "emerald" | "amber" }>) {
  const tones = {
    slate: "border-slate-200 bg-white",
    emerald: "border-emerald-200 bg-emerald-50/60",
    amber: "border-amber-200 bg-amber-50/60",
  };
  return (
    <div className={`rounded-2xl border p-5 ${tones[tone]}`}>
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">{value}</div>
      <p className="mt-2 text-xs leading-5 text-slate-500">{detail}</p>
    </div>
  );
}

export default function HearthlineDemoPage() {
  const [inputs, setInputs] = useState(defaults);
  const update = <Key extends keyof Inputs>(key: Key, value: Inputs[Key]) => setInputs((current) => ({ ...current, [key]: value }));

  const model = useMemo(() => {
    const gainsFraction = 1 - inputs.costBasisPct;
    const keepRate = 1 - inputs.capitalGainsTaxRate * gainsFraction;
    const grossSale = inputs.downPayment / keepRate;
    const gainsRealized = grossSale * gainsFraction;
    const taxPaid = gainsRealized * inputs.capitalGainsTaxRate;
    const opportunityCost = grossSale * ((1 + inputs.expectedReturn) ** 10 - 1);
    const annualRate = inputs.sofrRate + inputs.brokerSpread;
    const monthlyInterest = inputs.downPayment * annualRate / 12;
    const monthlyNoi = inputs.monthlyRent - inputs.monthlyExpenses;
    const monthlySpread = monthlyNoi - monthlyInterest;
    const dangerValue = inputs.downPayment / inputs.maintenanceLtv;
    const drawdownToCall = 1 - dangerValue / inputs.portfolioValue;
    const risk = estimateMarginRisk(inputs);
    const projection = Array.from({ length: 11 }, (_, year) => {
      const equityGrowth = (1 + inputs.expectedReturn) ** year;
      const propertyGrowth = inputs.purchasePrice * (1 + inputs.appreciation) ** year;
      return {
        year,
        sell: (inputs.portfolioValue - grossSale) * equityGrowth + propertyGrowth,
        sbloc: inputs.portfolioValue * equityGrowth + propertyGrowth - inputs.downPayment + monthlySpread * 12 * year,
      };
    });
    const stress = [0, 100, 200, 300].map((shockBps) => {
      const rate = annualRate + shockBps / 10_000;
      const interest = inputs.downPayment * rate / 12;
      return { shockBps, rate, interest, spread: monthlyNoi - interest };
    });

    return { grossSale, taxPaid, opportunityCost, annualRate, monthlyInterest, monthlyNoi, monthlySpread, dangerValue, drawdownToCall, risk, projection, stress };
  }, [inputs]);

  const fiveYearRisk = model.risk.at(-1)?.probability ?? 0;
  const spreadPositive = model.monthlySpread >= 0;
  const projectionChart = useMemo(() => {
    const values = model.projection.flatMap((point) => [point.sell, point.sbloc]);
    const minimum = Math.min(...values) * 0.94;
    const maximum = Math.max(...values) * 1.03;
    const x = (year: number) => 64 + year * 70;
    const y = (value: number) => 276 - ((value - minimum) / (maximum - minimum)) * 236;
    const points = (key: "sell" | "sbloc") => model.projection.map((point) => `${x(point.year)},${y(point[key])}`).join(" ");
    const ticks = Array.from({ length: 5 }, (_, index) => {
      const value = minimum + ((maximum - minimum) * index) / 4;
      return { value, y: y(value) };
    });
    return { points, ticks };
  }, [model.projection]);

  return (
    <main className="min-h-screen bg-[#f6f8f5] text-slate-950">
      <header className="border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <Link className="flex items-center gap-3" href="/">
            <span className="grid size-10 place-items-center rounded-xl bg-[#12372a] text-sm font-bold text-white">H</span>
            <span>
              <span className="block text-sm font-semibold">Hearthline</span>
              <span className="block text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">Sell vs SBLOC</span>
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] font-semibold text-emerald-800 sm:inline-flex">Synthetic public demo</span>
            <Link className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:border-slate-300" href="/">Open full app</Link>
          </div>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-[radial-gradient(circle_at_top_right,_#dceee2,_transparent_42%)]">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:px-6 lg:grid-cols-[1.25fr_.75fr] lg:px-8 lg:py-16">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-[#2d6a4f]">Interactive decision model</div>
            <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.045em] sm:text-5xl lg:text-6xl">Sell stock or borrow against it?</h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">Compare tax drag and lost compounding against SBLOC interest, property cash flow, rate stress, and simulated margin-call risk.</p>
          </div>
          <div className="rounded-3xl border border-emerald-200 bg-white/80 p-6 shadow-[0_24px_70px_-45px_rgba(18,55,42,.55)]">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">Current read</div>
            <p className="mt-3 text-xl font-semibold leading-8">The SBLOC preserves invested capital and the property covers interest in the base case.</p>
            <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
              <div><div className="text-slate-400">Monthly spread</div><div className={`mt-1 font-semibold ${spreadPositive ? "text-emerald-700" : "text-rose-700"}`}>{formatCurrency(model.monthlySpread)}</div></div>
              <div><div className="text-slate-400">5-year breach risk</div><div className="mt-1 font-semibold text-slate-900">{formatPct(fiveYearRisk, 1)}</div></div>
            </div>
            <p className="mt-5 text-[11px] leading-5 text-slate-500">Illustrative assumptions only. This demo makes no recommendation and does not use personal or live account data.</p>
          </div>
        </div>
      </section>

      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[340px_1fr] lg:px-8">
        <aside className="h-fit rounded-3xl border border-slate-200 bg-white p-5 shadow-sm lg:sticky lg:top-5">
          <div className="flex items-center justify-between">
            <div><div className="text-sm font-semibold">Model assumptions</div><div className="mt-1 text-xs text-slate-500">Edit any value; results update locally.</div></div>
            <button className="text-xs font-semibold text-emerald-700 hover:text-emerald-900" onClick={() => setInputs(defaults)}>Reset</button>
          </div>
          <div className="mt-6 space-y-4">
            <InputField label="Taxable portfolio" value={inputs.portfolioValue} onChange={(value) => update("portfolioValue", value)} />
            <InputField label="Cost basis" value={inputs.costBasisPct} onChange={(value) => update("costBasisPct", value)} step={0.01} suffix="%" />
            <InputField label="Expected equity return" value={inputs.expectedReturn} onChange={(value) => update("expectedReturn", value)} step={0.005} suffix="%" />
            <InputField label="Annual volatility" value={inputs.volatility} onChange={(value) => update("volatility", value)} step={0.01} suffix="%" />
            <InputField label="Maintenance LTV" value={inputs.maintenanceLtv} onChange={(value) => update("maintenanceLtv", value)} step={0.01} min={0.01} suffix="%" />
            <div className="border-t border-slate-100 pt-4" />
            <InputField label="Property price" value={inputs.purchasePrice} onChange={(value) => update("purchasePrice", value)} />
            <InputField label="Down payment / SBLOC" value={inputs.downPayment} onChange={(value) => update("downPayment", value)} />
            <InputField label="Monthly rent" value={inputs.monthlyRent} onChange={(value) => update("monthlyRent", value)} step={100} />
            <InputField label="Monthly operating costs" value={inputs.monthlyExpenses} onChange={(value) => update("monthlyExpenses", value)} step={100} />
            <InputField label="SOFR assumption" value={inputs.sofrRate} onChange={(value) => update("sofrRate", value)} step={0.001} suffix="%" />
            <InputField label="Broker spread" value={inputs.brokerSpread} onChange={(value) => update("brokerSpread", value)} step={0.001} suffix="%" />
          </div>
        </aside>

        <div className="space-y-8">
          <section>
            <div className="mb-4"><div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">01 / Tradeoff</div><h2 className="mt-2 text-2xl font-semibold tracking-tight">What each path costs</h2></div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Gross stock sale" value={formatCurrency(model.grossSale)} detail={`${formatCurrency(model.taxPaid)} estimated capital-gains tax to net the down payment.`} tone="amber" />
              <Metric label="Lost 10Y compounding" value={formatCurrency(model.opportunityCost)} detail={`Foregone growth on the gross sale at ${(inputs.expectedReturn * 100).toFixed(1)}% annually.`} />
              <Metric label="SBLOC interest" value={`${formatCurrency(model.monthlyInterest)}/mo`} detail={`${formatPct(model.annualRate, 2)} modeled rate: SOFR plus broker spread.`} />
              <Metric label="Property less interest" value={`${formatCurrency(model.monthlySpread)}/mo`} detail={`${formatCurrency(model.monthlyNoi)} NOI before SBLOC interest.`} tone={spreadPositive ? "emerald" : "amber"} />
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div><div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">02 / Margin call</div><h2 className="mt-2 text-2xl font-semibold tracking-tight">How much drawdown breaks the loan?</h2></div>
              <div className="text-left sm:text-right"><div className="text-xs text-slate-400">Danger portfolio value</div><div className="mt-1 text-xl font-semibold">{formatCurrency(model.dangerValue)}</div></div>
            </div>
            <div className="mt-6 grid gap-6 md:grid-cols-[.8fr_1.2fr]">
              <div className="rounded-2xl bg-slate-950 p-6 text-white">
                <div className="text-xs text-slate-400">Drawdown to maintenance call</div>
                <div className="mt-2 text-5xl font-semibold tracking-[-0.05em]">{formatPct(Math.max(0, model.drawdownToCall), 1)}</div>
                <p className="mt-4 text-xs leading-5 text-slate-400">A breach occurs when loan ÷ portfolio reaches the maintenance LTV. The simulation checks the threshold monthly, not only at the horizon.</p>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {model.risk.map((item) => <div className="rounded-2xl border border-slate-200 p-4" key={item.months}><div className="text-xs font-semibold text-slate-400">{item.label}</div><div className="mt-3 text-2xl font-semibold">{formatPct(item.probability, 1)}</div><div className="mt-2 text-[10px] text-slate-400">4,000 seeded GBM paths</div></div>)}
              </div>
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">03 / Rate stress</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">Does rent still cover the line?</h2>
            <div className="mt-6 overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="border-b border-slate-200 text-[10px] uppercase tracking-[0.16em] text-slate-400"><tr><th className="pb-3 font-semibold">Shock</th><th className="pb-3 font-semibold">All-in rate</th><th className="pb-3 font-semibold">Monthly interest</th><th className="pb-3 text-right font-semibold">NOI less interest</th></tr></thead>
                <tbody>{model.stress.map((row) => <tr className="border-b border-slate-100 last:border-0" key={row.shockBps}><td className="py-4 font-semibold">{row.shockBps === 0 ? "Base" : `+${row.shockBps} bps`}</td><td className="py-4">{formatPct(row.rate, 2)}</td><td className="py-4">{formatCurrency(row.interest)}</td><td className={`py-4 text-right font-semibold ${row.spread >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatCurrency(row.spread)}</td></tr>)}</tbody>
              </table>
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">04 / Long view</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">Simplified ten-year paths</h2>
            <p className="mt-2 text-xs leading-5 text-slate-500">Both paths hold the same appreciating property. The comparison isolates stock-sale drag versus retained equities, outstanding SBLOC principal, and cumulative property cash flow.</p>
            <div className="mt-6 h-[320px] w-full">
              <svg aria-label="Ten-year sell stock versus SBLOC projection" className="h-full w-full" role="img" viewBox="0 0 800 320">
                {projectionChart.ticks.map((tick) => (
                  <g key={tick.value}>
                    <line stroke="#e2e8f0" strokeDasharray="4 5" x1="64" x2="770" y1={tick.y} y2={tick.y} />
                    <text fill="#64748b" fontSize="11" textAnchor="end" x="54" y={tick.y + 4}>${(tick.value / 1_000_000).toFixed(1)}m</text>
                  </g>
                ))}
                {[0, 2, 4, 6, 8, 10].map((year) => <text fill="#64748b" fontSize="11" key={year} textAnchor="middle" x={64 + year * 70} y="302">{year}</text>)}
                <polyline fill="none" points={projectionChart.points("sell")} stroke="#d97706" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
                <polyline fill="none" points={projectionChart.points("sbloc")} stroke="#15803d" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" />
                <g transform="translate(560 12)">
                  <line stroke="#d97706" strokeWidth="3" x1="0" x2="22" y1="7" y2="7" /><text fill="#475569" fontSize="11" x="29" y="11">Sell stock</text>
                  <line stroke="#15803d" strokeWidth="3" x1="104" x2="126" y1="7" y2="7" /><text fill="#475569" fontSize="11" x="133" y="11">Use SBLOC</text>
                </g>
              </svg>
            </div>
          </section>

          <footer className="rounded-2xl border border-slate-200 bg-slate-100/70 p-5 text-xs leading-6 text-slate-500">Synthetic data only. GBM is a simplified market model; it omits jumps, changing collateral eligibility, broker discretion, taxes beyond the modeled sale, mortgage amortization, transaction costs, and liquidity constraints. Hearthline is a planning tool, not financial advice.</footer>
        </div>
      </div>
    </main>
  );
}
