from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RiskTolerance = Literal["conservative", "balanced", "growth"]
PropertyPurpose = Literal["primary", "investment"]


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    user: UserOut


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one letter and one number")
        return value


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class FinancialProfile(BaseModel):
    annual_gross_income: float = Field(180_000, ge=0, le=100_000_000)
    monthly_take_home_income: float = Field(10_500, ge=0, le=10_000_000)
    monthly_debt_payments: float = Field(700, ge=0, le=10_000_000)
    monthly_living_expenses: float = Field(4_500, ge=0, le=10_000_000)
    liquid_cash: float = Field(160_000, ge=0, le=1_000_000_000)
    taxable_investments: float = Field(350_000, ge=0, le=10_000_000_000)
    retirement_assets: float = Field(200_000, ge=0, le=10_000_000_000)
    other_assets: float = Field(0, ge=0, le=10_000_000_000)
    total_liabilities: float = Field(25_000, ge=0, le=10_000_000_000)
    credit_score: int = Field(760, ge=300, le=850)
    risk_tolerance: RiskTolerance = "balanced"
    reserve_months: int = Field(6, ge=1, le=36)
    primary_down_payment_pct: float = Field(0.20, ge=0.03, le=1)
    investment_down_payment_pct: float = Field(0.25, ge=0.10, le=1)
    mortgage_rate: float = Field(0.065, ge=0, le=0.30)
    mortgage_term_years: int = Field(30, ge=5, le=40)
    property_tax_rate: float = Field(0.012, ge=0, le=0.10)
    home_insurance_rate: float = Field(0.0045, ge=0, le=0.10)
    closing_cost_rate: float = Field(0.03, ge=0, le=0.15)
    primary_hoa_monthly: float = Field(0, ge=0, le=20_000)
    investment_vacancy_rate: float = Field(0.05, ge=0, le=0.50)
    investment_management_rate: float = Field(0.08, ge=0, le=0.50)
    investment_maintenance_rate: float = Field(0.08, ge=0, le=0.50)
    investment_capex_rate: float = Field(0.05, ge=0, le=0.50)
    min_dscr: float = Field(1.20, ge=0, le=5)
    min_cash_on_cash: float = Field(0.06, ge=-1, le=2)
    min_monthly_cashflow: float = Field(200, ge=-100_000, le=1_000_000)


class PurchaseRange(BaseModel):
    purpose: PropertyPurpose
    comfortable_min: float
    comfortable_max: float
    stretch_max: float
    payment_limited_max: float | None
    cash_limited_max: float
    monthly_payment_budget: float | None
    capital_available: float
    down_payment_pct: float
    explanation: str


class AffordabilityResponse(BaseModel):
    net_worth: float
    liquid_net_worth: float
    required_reserves: float
    investable_cash: float
    current_back_end_dti: float
    primary: PurchaseRange
    investment: PurchaseRange
    assumptions: list[str]


class SearchCriteria(BaseModel):
    purpose: PropertyPurpose = "primary"
    location: str = Field("Fairfield County, CT", min_length=2, max_length=120)
    radius_miles: float = Field(20, ge=1, le=100)
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, gt=0)
    min_bedrooms: float = Field(2, ge=0, le=30)
    min_bathrooms: float = Field(1, ge=0, le=30)
    property_types: list[str] = Field(default_factory=lambda: ["Single Family", "Condo", "Townhouse"])
    max_days_on_market: int | None = Field(90, ge=1, le=10_000)
    down_payment_pct: float | None = Field(None, ge=0.03, le=1)
    min_match_score: float = Field(65, ge=0, le=100)
    min_cap_rate: float | None = Field(None, ge=-1, le=2)
    min_dscr: float | None = Field(None, ge=0, le=10)
    min_cash_on_cash: float | None = Field(None, ge=-2, le=10)
    min_monthly_cashflow: float | None = Field(None, ge=-1_000_000, le=1_000_000)

    @model_validator(mode="after")
    def validate_price_range(self) -> "SearchCriteria":
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must not exceed max_price")
        return self


class SavedSearchCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    criteria: SearchCriteria
    notifications_enabled: bool = False
    notification_email: str | None = Field(None, max_length=254)

    @model_validator(mode="after")
    def validate_notifications(self) -> "SavedSearchCreate":
        if self.notifications_enabled and not self.notification_email:
            raise ValueError("A notification email is required when notifications are enabled")
        return self


class SavedSearchOut(SavedSearchCreate):
    id: str
    created_at: str
    updated_at: str
    last_scanned_at: str | None = None


class PropertyListing(BaseModel):
    id: str
    provider: str
    address: str
    city: str
    state: str
    zip_code: str | None = None
    price: float
    bedrooms: float
    bathrooms: float
    square_feet: float | None = None
    property_type: str
    year_built: int | None = None
    hoa_monthly: float = 0
    days_on_market: int | None = None
    listed_date: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    estimated_rent: float | None = None
    rent_estimate_source: str | None = None
    source_url: str | None = None


class PropertyMetrics(BaseModel):
    monthly_principal_interest: float
    monthly_taxes: float
    monthly_insurance: float
    total_monthly_housing_cost: float
    cash_required: float
    projected_monthly_rent: float | None = None
    noi_monthly: float | None = None
    monthly_cashflow: float | None = None
    cap_rate: float | None = None
    cash_on_cash: float | None = None
    dscr: float | None = None


class PropertyMatch(BaseModel):
    listing: PropertyListing
    metrics: PropertyMetrics
    score: float
    verdict: Literal["strong", "possible", "outside_range"]
    reasons: list[str]
    warnings: list[str]
    is_new: bool = False


class ScanResponse(BaseModel):
    search: SavedSearchOut
    provider: str
    provider_mode: Literal["demo", "live"]
    scanned_at: str
    total_scanned: int
    matches: list[PropertyMatch]
    new_match_count: int
    notification_status: str


class SavedSimulationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    inputs: dict[str, float]


class SavedSimulationOut(SavedSimulationCreate):
    id: str
    created_at: str
    updated_at: str


class ErrorResponse(BaseModel):
    detail: str


class ProviderStatus(BaseModel):
    provider: str
    mode: Literal["demo", "live"]
    configured: bool
    detail: str
    capabilities: list[str]


JsonObject = dict[str, Any]
