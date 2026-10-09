from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

StrStrategy = Literal["investment", "hybrid"]
RevenueSource = Literal["assumption", "market_average", "licensed_property_forecast", "actual_operations"]
Gate = Literal["unknown", "verified", "blocked"]


class StrDeal(BaseModel):
    name: str = Field("Cabin underwriting", min_length=2, max_length=120)
    address: str = Field("Unspecified property", min_length=2, max_length=300)
    strategy: StrStrategy = "investment"
    property_price: float = Field(350_000, gt=0)
    down_payment_pct: float = Field(0.25, ge=0, le=1)
    mortgage_apr: float = Field(0.08, ge=0, le=0.30)
    loan_term_years: int = Field(30, ge=5, le=40)
    closing_cost_pct: float = Field(0.05, ge=0, le=0.30)
    furnishings: float = Field(25_000, ge=0)
    cash_reserve: float = Field(15_000, ge=0)

    annual_gross_revenue: float = Field(60_000, ge=0)
    revenue_source: RevenueSource = "assumption"
    forecast_as_of: str | None = None
    comparable_count: int = Field(0, ge=0)
    # Optional monthly gross revenue before owner-use blocks. This overrides annual_gross_revenue.
    monthly_gross_revenue: list[float] | None = Field(None, min_length=12, max_length=12)
    owner_nights: int = Field(0, ge=0, le=365)
    owner_nights_by_month: list[int] | None = Field(None, min_length=12, max_length=12)

    property_tax_annual: float = Field(6_000, ge=0)
    insurance_annual: float = Field(3_600, ge=0)
    utilities_annual: float = Field(4_800, ge=0)
    property_services_annual: float = Field(2_500, ge=0)
    repairs_capex_annual: float = Field(5_000, ge=0)
    management_pct: float = Field(0.20, ge=0, le=1)
    platform_pct: float = Field(0.08, ge=0, le=1)
    turnovers_pct: float = Field(0.12, ge=0, le=1)

    regulatory_gate: Gate = "unknown"
    hoa_gate: Gate = "unknown"
    refinance_after_months: int = Field(24, ge=1, le=480)
    refinance_apr: float = Field(0.055, ge=0, le=0.30)
    refinance_fees: float = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_deal(self) -> "StrDeal":
        if self.management_pct + self.platform_pct + self.turnovers_pct >= 1:
            raise ValueError("Combined variable expense rates must be less than 100%")
        if self.refinance_after_months >= self.loan_term_years * 12:
            raise ValueError("Refinance must occur before the loan matures")
        if self.owner_nights_by_month is not None:
            days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
            if any(n > d for n, d in zip(self.owner_nights_by_month, days)):
                raise ValueError("Owner nights cannot exceed calendar days in a month")
            if self.strategy == "hybrid" and sum(self.owner_nights_by_month) != self.owner_nights:
                raise ValueError("Sum of monthly owner nights must equal owner_nights")
        if self.strategy == "investment" and self.owner_nights:
            raise ValueError("Use hybrid strategy to model personal nights")
        return self


class StrUnderwriting(BaseModel):
    annual_gross_before_owner_use: float
    foregone_owner_revenue: float
    annual_gross_after_owner_use: float
    annual_fixed_operating_costs: float
    annual_variable_operating_costs: float
    annual_noi: float
    annual_debt_service: float
    annual_cash_flow: float
    downside_cash_flow: float
    upside_cash_flow: float
    debt_service_coverage: float | None
    cap_rate: float
    cash_on_cash: float
    capital_required_including_reserves: float
    break_even_gross_before_owner_use: float
    future_refinanced_annual_cash_flow: float
    refinance_annual_payment_savings: float
    refinance_cost_payback_years: float | None
    screening_status: Literal["blocked", "research_only", "meets_financial_screen", "below_financial_screen"]
    warnings: list[str]


class StrScenarioCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    deal: StrDeal


class StrScenarioOut(StrScenarioCreate):
    id: str
    created_at: str
    updated_at: str
