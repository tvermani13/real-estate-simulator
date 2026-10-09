from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.routes.str_models import Money


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class ForecastProperty(EvidenceModel):
    address: str = Field(min_length=5, max_length=300)
    property_type: str = Field(min_length=2, max_length=40)
    bedrooms: float = Field(ge=0, le=30)
    bathrooms: float = Field(ge=0, le=30)
    provider_property_id: str = Field(min_length=1, max_length=120)


class ForecastMonth(EvidenceModel):
    month: date
    gross_revenue: Money
    adr: Money | None = None
    occupancy: Annotated[float, Field(ge=0, le=1)] | None = None
    available_nights: Annotated[int, Field(ge=0, le=31)] | None = None

    @model_validator(mode="after")
    def consistent_revenue(self) -> "ForecastMonth":
        days = calendar.monthrange(self.month.year, self.month.month)[1]
        if self.month.day != 1:
            raise ValueError("Forecast months must use the first calendar day")
        if self.available_nights is not None and self.available_nights != days:
            raise ValueError("Forecast must cover all calendar nights before personal-use blocks")
        supplied = (self.adr is not None, self.occupancy is not None, self.available_nights is not None)
        if any(supplied) and not all(supplied):
            raise ValueError("ADR, occupancy and available nights must be supplied together")
        if all(supplied):
            expected = self.adr * self.occupancy * self.available_nights
            if abs(expected - self.gross_revenue) > max(1, expected * 0.01):
                raise ValueError("Revenue must equal ADR × occupied nights within 1% rounding tolerance")
        return self


class RentalComparable(EvidenceModel):
    provider_property_id: str = Field(min_length=1, max_length=120)
    source_url: HttpUrl
    property_type: str = Field(min_length=2, max_length=40)
    bedrooms: float = Field(ge=0, le=30)
    bathrooms: float = Field(ge=0, le=30)
    distance_miles: float = Field(ge=0, le=1000)
    period_start: date
    period_end: date
    gross_revenue: Money
    observed_booked_nights: int = Field(ge=0, le=366)
    owner_blocked_nights: int = Field(ge=0, le=366)
    exclusion_reason: str | None = Field(None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def valid_observation(self) -> "RentalComparable":
        days = (self.period_end - self.period_start).days + 1
        if not 330 <= days <= 366:
            raise ValueError("Comparable evidence requires approximately 12 months of observations")
        if self.observed_booked_nights + self.owner_blocked_nights > days:
            raise ValueError("Booked and owner-blocked nights exceed the observation window")
        if self.gross_revenue > 0 and self.observed_booked_nights == 0:
            raise ValueError("Positive comparable revenue requires booked nights")
        return self


class LicensedForecastExport(EvidenceModel):
    """Normalized licensed export. No vendor API contract is assumed."""

    schema_version: Literal[1] = 1
    forecast_kind: Literal["property_specific"]
    provider: str = Field(min_length=2, max_length=80)
    source_url: HttpUrl
    attribution: str = Field(min_length=5, max_length=500)
    license_reference: str = Field(min_length=3, max_length=200)
    licensed_use_attested: Literal[True]
    permitted_use: Literal["internal_underwriting"]
    retention_permitted: Literal[True]
    retention_until: date
    data_version: str = Field(min_length=1, max_length=120)
    property: ForecastProperty
    as_of: date
    generated_at: datetime
    currency: Literal["USD"]
    revenue_basis: Literal["accommodation_only_before_owner_use"]
    methodology: str = Field(min_length=10, max_length=2000)
    months: list[ForecastMonth] = Field(min_length=12, max_length=12)
    comparables: list[RentalComparable] = Field(max_length=100)
    annual_p10: Money | None = None
    annual_p90: Money | None = None

    @model_validator(mode="after")
    def validate_export(self) -> "LicensedForecastExport":
        now = datetime.now(timezone.utc)
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at requires a timezone")
        if self.as_of > now.date() or self.generated_at > now or self.as_of > self.generated_at.date():
            raise ValueError("Evidence dates cannot be in the future or out of order")
        if self.retention_until < self.generated_at.date():
            raise ValueError("Retention must cover the generation date")
        start = self.months[0].month
        for index, item in enumerate(self.months):
            ordinal = start.year * 12 + start.month - 1 + index
            if item.month != date(ordinal // 12, ordinal % 12 + 1, 1):
                raise ValueError("Require 12 consecutive, ordered forecast months")
        ids = [c.provider_property_id for c in self.comparables]
        if len(ids) != len(set(ids)) or self.property.provider_property_id in ids:
            raise ValueError("Comparable IDs must be distinct and exclude the subject property")
        if any(c.period_end > self.as_of for c in self.comparables):
            raise ValueError("Comparable observations cannot postdate the evidence as-of date")
        annual = sum(m.gross_revenue for m in self.months)
        if (self.annual_p10 is not None and self.annual_p10 > annual) or (
            self.annual_p90 is not None and self.annual_p90 < annual
        ):
            raise ValueError("Provider p10/p90 bounds must surround the base forecast")
        return self

    def qualified_comparables(self) -> list[RentalComparable]:
        # Deliberately conservative; market averages and unrelated property classes never qualify.
        return [c for c in self.comparables if not c.exclusion_reason
                and c.property_type.casefold() == self.property.property_type.casefold()
                and abs(c.bedrooms - self.property.bedrooms) <= 1
                and abs(c.bathrooms - self.property.bathrooms) <= 1
                and c.distance_miles <= 25 and c.owner_blocked_nights == 0
                and 0 <= (self.as_of - c.period_end).days <= 90]


ForecastStatus = Literal["available", "unavailable", "stale", "insufficient_evidence", "property_mismatch", "license_expired"]


class ForecastResult(EvidenceModel):
    status: ForecastStatus
    reason: str
    snapshot_id: str | None = None
    imported_at: datetime | None = None
    qualified_comparable_count: int = 0
    forecast: LicensedForecastExport | None = None
