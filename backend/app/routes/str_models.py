from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StrStrategy = Literal["investment", "hybrid"]
RevenueSource = Literal["assumption", "market_average", "licensed_property_forecast", "actual_operations"]
Gate = Literal["unknown", "verified", "blocked"]
Money = Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]


class GateEvidence(BaseModel):
    """User-reviewed written evidence, not an automated legal determination."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Gate = "unknown"
    document_reference: str | None = Field(None, min_length=3, max_length=500)
    authority: str | None = Field(None, min_length=2, max_length=120)
    checked_on: date | None = None
    valid_until: date | None = None
    notes: str = Field("", max_length=1000)

    @model_validator(mode="after")
    def validate_evidence(self) -> "GateEvidence":
        if self.status != "unknown":
            if not all((self.document_reference, self.authority, self.checked_on, self.valid_until)):
                raise ValueError("Decided eligibility needs written evidence, authority and validity dates")
            if self.checked_on > date.today() or self.valid_until < self.checked_on:
                raise ValueError("Invalid eligibility evidence dates")
        return self

    def current_status(self, today: date | None = None) -> Gate:
        # A prohibition never becomes permission merely because its review expired.
        if self.status == "blocked":
            return "blocked"
        if self.status == "verified" and self.valid_until and self.valid_until >= (today or date.today()):
            return "verified"
        return "unknown"


class StrDeal(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field("Cabin underwriting", min_length=2, max_length=120)
    address: str = Field("Unspecified property", min_length=2, max_length=300)
    strategy: StrStrategy = "investment"
    property_price: float = Field(350_000, gt=0, le=1_000_000_000)
    down_payment_pct: float = Field(0.25, ge=0, le=1)
    mortgage_apr: float = Field(0.08, ge=0, le=0.30)
    loan_term_years: int = Field(30, ge=5, le=40)
    closing_cost_pct: float = Field(0.05, ge=0, le=0.30)
    furnishings: Money = 25_000
    cash_reserve: Money = 15_000

    annual_gross_revenue: Money = 60_000
    revenue_source: RevenueSource = "assumption"
    forecast_as_of: date | None = None
    forecast_snapshot_id: str | None = Field(None, max_length=80)
    comparable_count: int = Field(0, ge=0)
    # Optional monthly gross revenue before owner-use blocks. This overrides annual_gross_revenue.
    monthly_gross_revenue: list[Money] | None = Field(None, min_length=12, max_length=12)
    owner_nights: int = Field(0, ge=0, le=366)
    owner_nights_by_month: list[Annotated[int, Field(ge=0)]] | None = Field(None, min_length=12, max_length=12)
    monthly_calendar_days: list[Annotated[int, Field(ge=28, le=31)]] | None = Field(None, min_length=12, max_length=12)

    property_tax_annual: Money = 6_000
    insurance_annual: Money = 3_600
    utilities_annual: Money = 4_800
    property_services_annual: Money = 2_500
    repairs_capex_annual: Money = 5_000
    hoa_annual: Money = 0
    management_pct: float = Field(0.20, ge=0, le=1)
    platform_pct: float = Field(0.08, ge=0, le=1)
    turnovers_pct: float = Field(0.12, ge=0, le=1)

    regulatory_gate: Gate = "unknown"
    hoa_gate: Gate = "unknown"
    regulatory_evidence: GateEvidence | None = None
    hoa_evidence: GateEvidence | None = None
    refinance_after_months: int = Field(24, ge=1, le=480)
    refinance_apr: float = Field(0.055, ge=0, le=0.30)
    refinance_fees: Money = 0

    @model_validator(mode="after")
    def validate_deal(self) -> "StrDeal":
        if self.management_pct + self.platform_pct + self.turnovers_pct >= 1:
            raise ValueError("Combined variable expense rates must be less than 100%")
        if self.refinance_after_months >= self.loan_term_years * 12:
            raise ValueError("Refinance must occur before the loan matures")
        days = self.monthly_calendar_days or (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        if any(d != expected and not (index == 1 and d == 29)
               for index, (d, expected) in enumerate(zip(days, (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)))):
            raise ValueError("Calendar month lengths must match January–December, with optional leap February")
        if self.owner_nights > sum(days):
            raise ValueError("Owner nights exceed the modeled calendar year")
        if self.owner_nights_by_month is not None:
            if any(n > d for n, d in zip(self.owner_nights_by_month, days)):
                raise ValueError("Owner nights cannot exceed calendar days in a month")
            if sum(self.owner_nights_by_month) != self.owner_nights:
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
    cash_on_cash: float | None
    capital_required_including_reserves: float
    break_even_gross_before_owner_use: float | None
    refinance_remaining_principal: float
    refinance_remaining_term_months: int
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
