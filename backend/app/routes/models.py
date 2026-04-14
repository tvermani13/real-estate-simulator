from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioInputs(BaseModel):
    total_portfolio_value: float = Field(..., gt=0)
    weighted_average_cost_basis_pct: float = Field(..., ge=0, le=1)
    historical_volatility_annual: float = Field(..., ge=0)
    expected_equity_return_annual: float = Field(0.07, ge=-1, le=5)
    broker_maintenance_requirement_ltv_max: float = Field(0.7, gt=0, lt=1)


class DealInputs(BaseModel):
    property_purchase_price: float = Field(..., gt=0)
    down_payment_required: float = Field(..., ge=0)
    expected_monthly_rent: float = Field(..., ge=0)
    operating_expenses: float = Field(..., ge=0)
    expected_annual_appreciation: float = Field(0.03, ge=-1, le=5)


class ScenarioARequest(BaseModel):
    portfolio: PortfolioInputs
    deal: DealInputs
    capital_gains_tax_rate: float = Field(0.238, ge=0, lt=1)


class ScenarioAResponse(BaseModel):
    gross_sale_required: float
    capital_gains_tax_paid: float
    estimated_capital_gains_realized: float
    ten_year_opportunity_cost: float


class ScenarioBRequest(BaseModel):
    portfolio: PortfolioInputs
    deal: DealInputs
    loan_amount: float = Field(..., ge=0)
    sofr_rate: float = Field(..., ge=-0.05, le=1)
    broker_spread: float = Field(0.02, ge=0, le=0.5)


class StressRow(BaseModel):
    sofr_rate: float
    annual_rate: float
    monthly_interest_payment: float
    net_cashflow_monthly: float


class ScenarioBResponse(BaseModel):
    base: StressRow
    stressed: list[StressRow]


class RiskRequest(BaseModel):
    portfolio_value: float = Field(..., gt=0)
    loan_amount: float = Field(..., ge=0)
    maintenance_ltv_max: float = Field(0.7, gt=0, lt=1)
    mu_annual: float = Field(0.07, ge=-1, le=5)
    sigma_annual: float = Field(..., ge=0)
    horizons_months: list[int] = Field(default_factory=lambda: [12, 36, 60])
    runs: int = Field(10_000, ge=100, le=200_000)


class RiskHorizonResult(BaseModel):
    horizon_months: int
    breach_probability: float
    breach_count: int
    runs: int
    ending_values: list[float]


class RiskResponse(BaseModel):
    danger_portfolio_value: float
    results: list[RiskHorizonResult]

