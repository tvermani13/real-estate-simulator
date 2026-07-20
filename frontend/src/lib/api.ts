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
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: string | Array<{ msg?: string }> };
      detail = typeof parsed.detail === "string"
        ? parsed.detail
        : parsed.detail?.map((item) => item.msg).filter(Boolean).join(". ") ?? text;
    } catch {
      // Keep the response text when an upstream does not return JSON.
    }
    throw new ApiError(res.status, detail || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export type User = {
  id: string;
  name: string;
  email: string;
  created_at: string;
};

export type FinancialProfile = {
  annual_gross_income: number;
  monthly_take_home_income: number;
  monthly_debt_payments: number;
  monthly_living_expenses: number;
  liquid_cash: number;
  taxable_investments: number;
  retirement_assets: number;
  other_assets: number;
  total_liabilities: number;
  credit_score: number;
  risk_tolerance: "conservative" | "balanced" | "growth";
  reserve_months: number;
  primary_down_payment_pct: number;
  investment_down_payment_pct: number;
  mortgage_rate: number;
  mortgage_term_years: number;
  property_tax_rate: number;
  home_insurance_rate: number;
  closing_cost_rate: number;
  primary_hoa_monthly: number;
  investment_vacancy_rate: number;
  investment_management_rate: number;
  investment_maintenance_rate: number;
  investment_capex_rate: number;
  min_dscr: number;
  min_cash_on_cash: number;
  min_monthly_cashflow: number;
};

export type PurchaseRange = {
  purpose: "primary" | "investment";
  comfortable_min: number;
  comfortable_max: number;
  stretch_max: number;
  payment_limited_max: number | null;
  cash_limited_max: number;
  monthly_payment_budget: number | null;
  capital_available: number;
  down_payment_pct: number;
  explanation: string;
};

export type AffordabilityResponse = {
  net_worth: number;
  liquid_net_worth: number;
  required_reserves: number;
  investable_cash: number;
  current_back_end_dti: number;
  primary: PurchaseRange;
  investment: PurchaseRange;
  assumptions: string[];
};

export type SearchCriteria = {
  purpose: "primary" | "investment";
  location: string;
  radius_miles: number;
  min_price: number | null;
  max_price: number | null;
  min_bedrooms: number;
  min_bathrooms: number;
  property_types: string[];
  max_days_on_market: number | null;
  down_payment_pct: number | null;
  min_match_score: number;
  min_cap_rate: number | null;
  min_dscr: number | null;
  min_cash_on_cash: number | null;
  min_monthly_cashflow: number | null;
};

export type SavedSearch = {
  id: string;
  name: string;
  criteria: SearchCriteria;
  notifications_enabled: boolean;
  notification_email: string | null;
  created_at: string;
  updated_at: string;
  last_scanned_at: string | null;
};

export type PropertyListing = {
  id: string;
  provider: string;
  address: string;
  city: string;
  state: string;
  zip_code: string | null;
  price: number;
  bedrooms: number;
  bathrooms: number;
  square_feet: number | null;
  property_type: string;
  year_built: number | null;
  hoa_monthly: number;
  days_on_market: number | null;
  listed_date: string | null;
  latitude: number | null;
  longitude: number | null;
  estimated_rent: number | null;
  rent_estimate_source: string | null;
  source_url: string | null;
};

export type PropertyMatch = {
  listing: PropertyListing;
  metrics: {
    monthly_principal_interest: number;
    monthly_taxes: number;
    monthly_insurance: number;
    total_monthly_housing_cost: number;
    cash_required: number;
    projected_monthly_rent: number | null;
    noi_monthly: number | null;
    monthly_cashflow: number | null;
    cap_rate: number | null;
    cash_on_cash: number | null;
    dscr: number | null;
  };
  score: number;
  verdict: "strong" | "possible" | "outside_range";
  reasons: string[];
  warnings: string[];
  is_new: boolean;
};

export type ScanResponse = {
  search: SavedSearch;
  provider: string;
  provider_mode: "demo" | "live";
  scanned_at: string;
  total_scanned: number;
  matches: PropertyMatch[];
  new_match_count: number;
  notification_status: string;
};

export type ProviderStatus = {
  provider: string;
  mode: "demo" | "live";
  configured: boolean;
  detail: string;
  capabilities: string[];
};

export type SavedSimulation = {
  id: string;
  name: string;
  inputs: Record<string, number>;
  created_at: string;
  updated_at: string;
};

export const api = {
  me: () => apiFetch<{ user: User }>("/api/auth/me", { method: "GET" }),
  login: (body: { email: string; password: string }) =>
    apiFetch<{ user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  register: (body: { name: string; email: string; password: string }) =>
    apiFetch<{ user: User }>("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  logout: () => apiFetch<void>("/api/auth/logout", { method: "POST" }),
  profile: () => apiFetch<FinancialProfile>("/api/profile", { method: "GET" }),
  saveProfile: (body: FinancialProfile) =>
    apiFetch<FinancialProfile>("/api/profile", { method: "PUT", body: JSON.stringify(body) }),
  affordability: () => apiFetch<AffordabilityResponse>("/api/affordability", { method: "GET" }),
  providerStatus: () => apiFetch<ProviderStatus>("/api/property-provider", { method: "GET" }),
  searches: () => apiFetch<SavedSearch[]>("/api/searches", { method: "GET" }),
  createSearch: (body: Omit<SavedSearch, "id" | "created_at" | "updated_at" | "last_scanned_at">) =>
    apiFetch<SavedSearch>("/api/searches", { method: "POST", body: JSON.stringify(body) }),
  deleteSearch: (id: string) => apiFetch<void>(`/api/searches/${id}`, { method: "DELETE" }),
  scanSearch: (id: string) => apiFetch<ScanResponse>(`/api/searches/${id}/scan`, { method: "POST" }),
  savedMatches: (id: string) => apiFetch<PropertyMatch[]>(`/api/searches/${id}/matches`, { method: "GET" }),
  simulations: () => apiFetch<SavedSimulation[]>("/api/simulations", { method: "GET" }),
  saveSimulation: (body: { name: string; inputs: Record<string, number> }) =>
    apiFetch<SavedSimulation>("/api/simulations", { method: "POST", body: JSON.stringify(body) }),
  deleteSimulation: (id: string) => apiFetch<void>(`/api/simulations/${id}`, { method: "DELETE" }),
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
