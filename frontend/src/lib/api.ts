export type MacroResponse = {
  sofr: { series_id: string; date: string | null; value: number | null };
  effr: { series_id: string; date: string | null; value: number | null };
  source: "fred" | "fallback";
};

export type ScenarioARequest = {
  portfolio: {
    total_portfolio_value: number;
    weighted_average_cost_basis_pct: number;
    historical_volatility_annual: number;
    expected_equity_return_annual: number;
    broker_maintenance_requirement_ltv_max: number;
  };
  deal: {
    property_purchase_price: number;
    down_payment_required: number;
    expected_monthly_rent: number;
    operating_expenses: number;
    expected_annual_appreciation: number;
  };
  capital_gains_tax_rate: number;
};

export type ScenarioAResponse = {
  gross_sale_required: number;
  capital_gains_tax_paid: number;
  estimated_capital_gains_realized: number;
  ten_year_opportunity_cost: number;
};

export type ScenarioBRequest = {
  portfolio: ScenarioARequest["portfolio"];
  deal: ScenarioARequest["deal"];
  loan_amount: number;
  sofr_rate: number;
  broker_spread: number;
};

export type ScenarioBResponse = {
  base: {
    sofr_rate: number;
    annual_rate: number;
    monthly_interest_payment: number;
    net_cashflow_monthly: number;
  };
  stressed: Array<ScenarioBResponse["base"]>;
};

export type RiskRequest = {
  portfolio_value: number;
  loan_amount: number;
  maintenance_ltv_max: number;
  mu_annual: number;
  sigma_annual: number;
  horizons_months: number[];
  runs: number;
};

export type RiskResponse = {
  danger_portfolio_value: number;
  results: Array<{
    horizon_months: number;
    breach_probability: number;
    breach_count: number;
    runs: number;
    ending_values: number[];
  }>;
};

function baseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${baseUrl()}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? undefined) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText}: ${text}`.trim());
  }
  return (await res.json()) as T;
}

export const api = {
  macro: () => apiFetch<MacroResponse>("/api/macro", { method: "GET" }),
  scenarioA: (body: ScenarioARequest) =>
    apiFetch<ScenarioAResponse>("/api/scenario-a", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  scenarioB: (body: ScenarioBRequest) =>
    apiFetch<ScenarioBResponse>("/api/scenario-b", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  risk: (body: RiskRequest) =>
    apiFetch<RiskResponse>("/api/risk", { method: "POST", body: JSON.stringify(body) }),
};

