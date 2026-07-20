"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  AreaChart,
} from "recharts";

import { Field } from "@/components/Field";
import { InstructionsModal } from "@/components/InstructionsModal";
import { AuthScreen } from "@/components/AuthScreen";
import { DiscoverWorkspace } from "@/components/DiscoverWorkspace";
import { OverviewWorkspace } from "@/components/OverviewWorkspace";
import { ProfileWorkspace } from "@/components/ProfileWorkspace";
import { AppHeader, LoadingBlock, type Workspace } from "@/components/ProductUI";
import { ApiError, api, type MacroResponse, type RiskResponse, type SavedSimulation, type ScenarioAResponse, type ScenarioBResponse, type User } from "@/lib/api";
import { clamp, formatCurrency, formatPct } from "@/lib/format";
import { useElementSize } from "@/lib/useElementSize";

function Card({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm">
      <div className="border-b border-zinc-200 px-4 py-3">
        <div className="text-sm font-semibold text-zinc-900">{title}</div>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function badgeToneClass(tone: "green" | "yellow" | "red" | "zinc") {
  switch (tone) {
    case "green":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "yellow":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "red":
      return "bg-rose-50 text-rose-700 border-rose-200";
    case "zinc":
      return "bg-zinc-50 text-zinc-700 border-zinc-200";
  }
}

function Badge({
  tone,
  children,
}: Readonly<{ tone: "green" | "yellow" | "red" | "zinc"; children: React.ReactNode }>) {
  const cls = badgeToneClass(tone);
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {children}
    </span>
  );
}

export default function Home() {
  const [sessionUser, setSessionUser] = useState<User | null | undefined>(undefined);
  const [workspace, setWorkspace] = useState<Workspace>("overview");
  const [macro, setMacro] = useState<MacroResponse | null>(null);
  const [macroErr, setMacroErr] = useState<string | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);

  // Inputs (sane defaults so UI renders immediately).
  const [portfolioValue, setPortfolioValue] = useState(1_000_000);
  const [costBasisPct, setCostBasisPct] = useState(0.6);
  const [volAnnual, setVolAnnual] = useState(0.22);
  const [muAnnual, setMuAnnual] = useState(0.07);
  const [maintenanceLtvMax, setMaintenanceLtvMax] = useState(0.7);

  const [purchasePrice, setPurchasePrice] = useState(700_000);
  const [downPayment, setDownPayment] = useState(140_000);
  const [rent, setRent] = useState(4_200);
  const [opex, setOpex] = useState(1_800);
  const [appreciation, setAppreciation] = useState(0.03);

  const [capGainsTaxRate, setCapGainsTaxRate] = useState(0.238);
  const [brokerSpread, setBrokerSpread] = useState(0.02);
  const [rateShockBps, setRateShockBps] = useState(0);
  const [simulationName, setSimulationName] = useState("My property model");
  const [savedSimulations, setSavedSimulations] = useState<SavedSimulation[]>([]);
  const [simulationMessage, setSimulationMessage] = useState<string | null>(null);

  const loanAmount = downPayment;
  const sofr = macro?.sofr.value ?? 0.05;
  const shockedSofr = sofr + rateShockBps / 10000;

  const reqCommon = useMemo(
    () => ({
      portfolio: {
        total_portfolio_value: portfolioValue,
        weighted_average_cost_basis_pct: clamp(costBasisPct, 0, 1),
        historical_volatility_annual: Math.max(0, volAnnual),
        expected_equity_return_annual: muAnnual,
        broker_maintenance_requirement_ltv_max: clamp(maintenanceLtvMax, 0.01, 0.99),
      },
      deal: {
        property_purchase_price: purchasePrice,
        down_payment_required: downPayment,
        expected_monthly_rent: rent,
        operating_expenses: opex,
        expected_annual_appreciation: appreciation,
      },
    }),
    [portfolioValue, costBasisPct, volAnnual, muAnnual, maintenanceLtvMax, purchasePrice, downPayment, rent, opex, appreciation],
  );

  const [a, setA] = useState<ScenarioAResponse | null>(null);
  const [b, setB] = useState<ScenarioBResponse | null>(null);
  const [risk, setRisk] = useState<RiskResponse | null>(null);
  const [calcErr, setCalcErr] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    api.me()
      .then((result) => setSessionUser(result.user))
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.status === 401) setSessionUser(null);
        else setSessionUser(null);
      });
  }, []);

  useEffect(() => {
    if (!sessionUser) return;
    let cancelled = false;
    api
      .macro()
      .then((m) => {
        if (cancelled) return;
        setMacro(m);
        setMacroErr(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setMacroErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionUser]);

  useEffect(() => {
    if (!sessionUser || workspace !== "simulator") return;
    api.simulations().then(setSavedSimulations).catch(() => setSavedSimulations([]));
  }, [sessionUser, workspace]);

  async function recalc() {
    if (!sessionUser) return;
    setIsLoading(true);
    setCalcErr(null);
    try {
      const [ar, br, rr] = await Promise.all([
        api.scenarioA({ ...reqCommon, capital_gains_tax_rate: capGainsTaxRate }),
        api.scenarioB({
          ...reqCommon,
          loan_amount: loanAmount,
          sofr_rate: shockedSofr,
          broker_spread: brokerSpread,
        }),
        api.risk({
          portfolio_value: portfolioValue,
          loan_amount: loanAmount,
          maintenance_ltv_max: maintenanceLtvMax,
          mu_annual: muAnnual,
          sigma_annual: volAnnual,
          horizons_months: [12, 36, 60],
          runs: 10_000,
        }),
      ]);
      setA(ar);
      setB(br);
      setRisk(rr);
    } catch (e: unknown) {
      setCalcErr(e instanceof Error ? e.message : String(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!sessionUser) return;
    void recalc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionUser, reqCommon, capGainsTaxRate, brokerSpread, rateShockBps]);

  async function logout() {
    await api.logout().catch(() => undefined);
    setSessionUser(null);
    setWorkspace("overview");
  }

  async function saveCurrentSimulation() {
    setSimulationMessage(null);
    const saved = await api.saveSimulation({
      name: simulationName,
      inputs: {
        portfolioValue, costBasisPct, volAnnual, muAnnual, maintenanceLtvMax,
        purchasePrice, downPayment, rent, opex, appreciation,
        capGainsTaxRate, brokerSpread, rateShockBps,
      },
    });
    setSavedSimulations((current) => [saved, ...current]);
    setSimulationMessage("Model saved");
  }

  function loadSimulation(saved: SavedSimulation) {
    const value = saved.inputs;
    setPortfolioValue(value.portfolioValue ?? portfolioValue);
    setCostBasisPct(value.costBasisPct ?? costBasisPct);
    setVolAnnual(value.volAnnual ?? volAnnual);
    setMuAnnual(value.muAnnual ?? muAnnual);
    setMaintenanceLtvMax(value.maintenanceLtvMax ?? maintenanceLtvMax);
    setPurchasePrice(value.purchasePrice ?? purchasePrice);
    setDownPayment(value.downPayment ?? downPayment);
    setRent(value.rent ?? rent);
    setOpex(value.opex ?? opex);
    setAppreciation(value.appreciation ?? appreciation);
    setCapGainsTaxRate(value.capGainsTaxRate ?? capGainsTaxRate);
    setBrokerSpread(value.brokerSpread ?? brokerSpread);
    setRateShockBps(value.rateShockBps ?? rateShockBps);
    setSimulationName(saved.name);
    setSimulationMessage(`Loaded ${saved.name}`);
  }

  const baseAnnualRate = (b?.base.annual_rate ?? (shockedSofr + brokerSpread));
  const baseNetCashflow = b?.base.net_cashflow_monthly ?? (rent - opex - loanAmount * baseAnnualRate / 12);
  const spreadTone = (() => {
    if (baseNetCashflow > 200) return "green" as const;
    if (baseNetCashflow >= 0) return "yellow" as const;
    return "red" as const;
  })();

  const ltvNow = loanAmount / portfolioValue;
  const ltvLineData = [
    { name: "Now", ltv: ltvNow, max: maintenanceLtvMax },
  ];

  const ltvChart = useElementSize<HTMLDivElement>();
  const distChart = useElementSize<HTMLDivElement>();
  const projChart = useElementSize<HTMLDivElement>();

  const endingDistribution = useMemo(() => {
    const values = risk?.results?.[0]?.ending_values ?? [];
    if (values.length === 0) return [];
    const sorted = [...values].sort((x, y) => x - y);
    const buckets = 30;
    const min = sorted.at(0) ?? 0;
    const max = sorted.at(-1) ?? 0;
    const width = (max - min) / buckets || 1;
    const counts = Array.from({ length: buckets }, (_, i) => ({
      bucket: i,
      x: min + (i + 0.5) * width,
      count: 0,
    }));
    for (const v of sorted) {
      const idx = Math.min(buckets - 1, Math.max(0, Math.floor((v - min) / width)));
      counts[idx].count += 1;
    }
    return counts.map((d) => ({ x: d.x, count: d.count / sorted.length }));
  }, [risk]);

  const projection = useMemo(() => {
    // simple 10y projection: equities compound at mu; property compounds at appreciation; SBLOC is interest-only cashflow drag
    const years = Array.from({ length: 11 }, (_, i) => i);
    const grossSold = a?.gross_sale_required ?? downPayment;
    const equityStartDoNothing = portfolioValue;
    const equityStartSell = portfolioValue - grossSold;
    const equityStartSbloc = portfolioValue;

    const prop0 = purchasePrice;
    const loan = loanAmount;
    const annualRate = baseAnnualRate;
    const noiAnnual = (rent - opex) * 12;
    const interestAnnual = loan * annualRate;
    const netCashflowAnnual = noiAnnual - interestAnnual;

    return years.map((y) => {
      const eqDo = equityStartDoNothing * (1 + muAnnual) ** y;
      const eqSell = equityStartSell * (1 + muAnnual) ** y;
      const eqSbloc = equityStartSbloc * (1 + muAnnual) ** y;
      const prop = prop0 * (1 + appreciation) ** y;
      const cumCash = netCashflowAnnual * y;
      return {
        year: y,
        do_nothing: eqDo,
        sell_stocks: eqSell + prop,
        sbloc: eqSbloc + prop + cumCash - loan,
      };
    });
  }, [a, downPayment, portfolioValue, purchasePrice, loanAmount, baseAnnualRate, rent, opex, muAnnual, appreciation]);

  if (sessionUser === undefined) return <main className="min-h-screen bg-[#f7f8f5]"><LoadingBlock label="Opening your workspace…" /></main>;
  if (sessionUser === null) return <AuthScreen onAuthenticated={setSessionUser} />;
  if (workspace === "overview") return <div className="min-h-screen bg-[#f7f8f5]"><AppHeader user={sessionUser} active={workspace} onNavigate={setWorkspace} onLogout={() => void logout()} /><OverviewWorkspace onNavigate={setWorkspace} /></div>;
  if (workspace === "profile") return <div className="min-h-screen bg-[#f7f8f5]"><AppHeader user={sessionUser} active={workspace} onNavigate={setWorkspace} onLogout={() => void logout()} /><ProfileWorkspace /></div>;
  if (workspace === "discover") return <div className="min-h-screen bg-[#f7f8f5]"><AppHeader user={sessionUser} active={workspace} onNavigate={setWorkspace} onLogout={() => void logout()} /><DiscoverWorkspace user={sessionUser} /></div>;

  return (
    <div className="min-h-screen bg-zinc-50">
      <AppHeader user={sessionUser} active={workspace} onNavigate={setWorkspace} onLogout={() => void logout()} />
      <InstructionsModal open={showInstructions} onClose={() => setShowInstructions(false)} />
      <div className="border-b border-zinc-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-zinc-950">SBLOC & Real Estate Dashboard</div>
            <div className="text-xs text-zinc-500">Sell equities vs borrow against portfolio (cashflow + risk)</div>
          </div>
          <div className="flex items-center gap-3">
            <button
              className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-zinc-50"
              onClick={() => setShowInstructions(true)}
            >
              How to use
            </button>
            {macroErr ? <Badge tone="red">Macro error</Badge> : <Badge tone="zinc">Macro: {macro?.source ?? "…"}</Badge>}
            <div className="text-xs text-zinc-700">
              SOFR: <span className="font-semibold">{macro?.sofr.value ? formatPct(macro.sofr.value, 2) : "—"}</span>
            </div>
            <div className="text-xs text-zinc-700">
              EFFR: <span className="font-semibold">{macro?.effr.value ? formatPct(macro.effr.value, 2) : "—"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-6">
        <div className="space-y-4">
          <Card title="Saved models">
            <div className="space-y-3">
              <div className="flex gap-2">
                <input className="min-w-0 flex-1 rounded-md border border-zinc-200 px-3 py-2 text-xs" value={simulationName} onChange={(event) => setSimulationName(event.target.value)} />
                <button className="rounded-md bg-zinc-900 px-3 py-2 text-xs font-semibold text-white" onClick={() => void saveCurrentSimulation()}>Save</button>
              </div>
              {simulationMessage ? <div className="text-xs text-emerald-700">{simulationMessage}</div> : null}
              {savedSimulations.length ? (
                <div className="space-y-1.5">
                  {savedSimulations.slice(0, 5).map((saved) => (
                    <button key={saved.id} className="flex w-full items-center justify-between rounded-md border border-zinc-200 px-3 py-2 text-left text-xs hover:bg-zinc-50" onClick={() => loadSimulation(saved)}>
                      <span className="truncate font-medium text-zinc-800">{saved.name}</span>
                      <span className="text-[10px] text-zinc-400">Load</span>
                    </button>
                  ))}
                </div>
              ) : <div className="text-xs leading-5 text-zinc-500">Save these portfolio, deal, and stress-test inputs to revisit them later.</div>}
            </div>
          </Card>
          <Card title="Portfolio inputs">
            <div className="grid grid-cols-1 gap-3">
              <Field label="Total portfolio value ($)" value={portfolioValue} step={1000} min={1} onChange={setPortfolioValue} />
              <Field label="Weighted avg cost basis (0-1)" value={costBasisPct} step={0.01} min={0} max={1} onChange={setCostBasisPct} />
              <Field label="Volatility (annual, 0-1)" value={volAnnual} step={0.01} min={0} max={2} onChange={setVolAnnual} />
              <Field label="Expected equity return (annual, 0-1)" value={muAnnual} step={0.01} min={-1} max={2} onChange={setMuAnnual} />
              <Field label="Maintenance LTV max (0-1)" value={maintenanceLtvMax} step={0.01} min={0.1} max={0.95} onChange={setMaintenanceLtvMax} />
            </div>
          </Card>

          <Card title="Deal inputs">
            <div className="grid grid-cols-1 gap-3">
              <Field label="Purchase price ($)" value={purchasePrice} step={1000} min={1} onChange={setPurchasePrice} />
              <Field label="Down payment ($)" value={downPayment} step={1000} min={0} onChange={setDownPayment} />
              <Field label="Rent (monthly $)" value={rent} step={50} min={0} onChange={setRent} />
              <Field label="Operating expenses (monthly $)" value={opex} step={50} min={0} onChange={setOpex} />
              <Field label="Appreciation (annual, 0-1)" value={appreciation} step={0.005} min={-1} max={1} onChange={setAppreciation} />
            </div>
          </Card>

          <Card title="Scenario settings">
            <div className="grid grid-cols-1 gap-3">
              <Field label="Capital gains tax rate (0-1)" value={capGainsTaxRate} step={0.001} min={0} max={0.6} onChange={setCapGainsTaxRate} />
              <Field label="Broker spread (annual, 0-1)" value={brokerSpread} step={0.001} min={0} max={0.5} onChange={setBrokerSpread} />
              <label className="flex flex-col gap-1">
                <div className="text-xs font-medium text-zinc-600">SOFR shock (bps): {rateShockBps}bps</div>
                <input
                  className="w-full"
                  type="range"
                  min={0}
                  max={300}
                  step={25}
                  value={rateShockBps}
                  onChange={(e) => setRateShockBps(Number(e.currentTarget.value))}
                />
                <div className="text-xs text-zinc-500">
                  Effective SOFR: <span className="font-semibold">{formatPct(shockedSofr, 2)}</span>
                </div>
              </label>
            </div>
          </Card>
        </div>

        <div className="space-y-6 min-w-0">
          {calcErr ? (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{calcErr}</div>
          ) : null}

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <Card title="Deal matrix (cashflow spread)">
              <div className="flex items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="text-xs text-zinc-500">Loan amount (assumed = down payment)</div>
                  <div className="text-lg font-semibold text-zinc-950">{formatCurrency(loanAmount)}</div>
                </div>
                <Badge tone={spreadTone}>
                  {baseNetCashflow >= 0 ? "Cashflow positive" : "Cashflow negative"}
                </Badge>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg bg-zinc-50 p-3">
                  <div className="text-xs text-zinc-500">NOI (monthly)</div>
                  <div className="font-semibold text-zinc-950">{formatCurrency((rent - opex))}</div>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <div className="text-xs text-zinc-500">Interest (monthly)</div>
                  <div className="font-semibold text-zinc-950">{formatCurrency(b?.base.monthly_interest_payment ?? loanAmount * baseAnnualRate / 12)}</div>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3 col-span-2">
                  <div className="text-xs text-zinc-500">Net cashflow (monthly)</div>
                  <div className="text-xl font-semibold text-zinc-950">{formatCurrency(baseNetCashflow)}</div>
                </div>
              </div>
              <div className="mt-4 text-xs text-zinc-500">
                Rate: <span className="font-semibold">{formatPct(baseAnnualRate, 2)}</span> (SOFR {formatPct(shockedSofr, 2)} + spread {formatPct(brokerSpread, 2)})
              </div>
              <div className="mt-4">
                <div className="text-xs font-medium text-zinc-600 mb-2">Stress test (+100/+200/+300 bps SOFR)</div>
                <div className="space-y-2">
                  {(b?.stressed ?? []).map((row) => (
                    <div
                      key={`${row.sofr_rate}-${row.annual_rate}-${row.monthly_interest_payment}`}
                      className="flex items-center justify-between rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm"
                    >
                      <div className="text-zinc-700">SOFR {formatPct(row.sofr_rate, 2)}</div>
                      <div className="text-zinc-500">Net {formatCurrency(row.net_cashflow_monthly)}</div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            <Card title="Scenario A (sell stock) tax drag">
              <div className="grid grid-cols-1 gap-3 text-sm">
                <div className="rounded-lg bg-zinc-50 p-3">
                  <div className="text-xs text-zinc-500">Gross sale required</div>
                  <div className="text-lg font-semibold text-zinc-950">{formatCurrency(a?.gross_sale_required ?? 0)}</div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg bg-zinc-50 p-3">
                    <div className="text-xs text-zinc-500">Cap gains tax paid</div>
                    <div className="font-semibold text-zinc-950">{formatCurrency(a?.capital_gains_tax_paid ?? 0)}</div>
                  </div>
                  <div className="rounded-lg bg-zinc-50 p-3">
                    <div className="text-xs text-zinc-500">Gains realized</div>
                    <div className="font-semibold text-zinc-950">{formatCurrency(a?.estimated_capital_gains_realized ?? 0)}</div>
                  </div>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <div className="text-xs text-zinc-500">10Y opportunity cost (lost growth)</div>
                  <div className="text-lg font-semibold text-zinc-950">{formatCurrency(a?.ten_year_opportunity_cost ?? 0)}</div>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <Card title="Risk & stress testing (Monte Carlo)">
              <div className="flex items-center justify-between">
                <div className="text-sm text-zinc-700">
                  Current LTV: <span className="font-semibold">{formatPct(ltvNow, 2)}</span>
                </div>
                <div className="text-sm text-zinc-700">
                  Danger portfolio value:{" "}
                  <span className="font-semibold">{formatCurrency(risk?.danger_portfolio_value ?? 0)}</span>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {(risk?.results ?? []).map((r) => (
                  <div key={r.horizon_months} className="rounded-lg bg-zinc-50 p-3">
                    <div className="text-xs text-zinc-500">{r.horizon_months} mo breach prob</div>
                    <div className="text-lg font-semibold text-zinc-950">{formatPct(r.breach_probability, 2)}</div>
                  </div>
                ))}
              </div>
              <div ref={ltvChart.ref} className="mt-4 h-44 w-full min-w-0">
                {ltvChart.width > 0 && ltvChart.height > 0 ? (
                  <LineChart width={ltvChart.width} height={ltvChart.height} data={ltvLineData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis
                      tickFormatter={(v) => `${Math.round(v * 100)}%`}
                      domain={[0, Math.max(0.9, maintenanceLtvMax + 0.05)]}
                    />
                    <Tooltip formatter={(v) => formatPct(Number(v), 2)} />
                    <Legend />
                    <Line type="monotone" dataKey="ltv" stroke="#18181b" name="LTV" />
                    <Line type="monotone" dataKey="max" stroke="#e11d48" name="Maintenance max" />
                  </LineChart>
                ) : null}
              </div>
              <div className="mt-4 h-44 w-full min-w-0">
                <div className="text-xs font-medium text-zinc-600 mb-2">12-month ending portfolio distribution (approx)</div>
                <div ref={distChart.ref} className="h-full w-full min-w-0">
                  {distChart.width > 0 && distChart.height > 0 ? (
                    <AreaChart width={distChart.width} height={distChart.height} data={endingDistribution}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="x" tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} />
                      <YAxis tickFormatter={(v) => `${Math.round(Number(v) * 100)}%`} />
                      <Tooltip
                        formatter={(v, name) => {
                          if (name === "count") return [`${(Number(v) * 100).toFixed(2)}%`, "prob"];
                          return [String(v), String(name)];
                        }}
                        labelFormatter={(l) => `Value ~ ${formatCurrency(Number(l))}`}
                      />
                      <Area type="monotone" dataKey="count" stroke="#2563eb" fill="#93c5fd" name="prob" />
                    </AreaChart>
                  ) : null}
                </div>
              </div>
            </Card>

            <Card title="10-year net wealth projection (simplified)">
              <div className="text-xs text-zinc-500 mb-2">
                Uses your equity return + appreciation; SBLOC scenario includes interest-only spread as cash drag/boost.
              </div>
              <div ref={projChart.ref} className="h-[360px] w-full min-w-0">
                {projChart.width > 0 && projChart.height > 0 ? (
                  <LineChart width={projChart.width} height={projChart.height} data={projection}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="year" />
                    <YAxis tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} />
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                    <Legend />
                    <Line type="monotone" dataKey="do_nothing" stroke="#18181b" name="Do nothing" dot={false} />
                    <Line type="monotone" dataKey="sell_stocks" stroke="#0ea5e9" name="Sell stocks + RE" dot={false} />
                    <Line type="monotone" dataKey="sbloc" stroke="#16a34a" name="SBLOC + RE" dot={false} />
                  </LineChart>
                ) : null}
              </div>
            </Card>
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs text-zinc-500">
              {isLoading ? "Recalculating…" : "Up to date"}
            </div>
            <button
              className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
              onClick={() => void recalc()}
              disabled={isLoading}
            >
              Recalculate
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
