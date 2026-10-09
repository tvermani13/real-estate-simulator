from __future__ import annotations

from pydantic import ConfigDict, Field

from app.routes.product_models import PropertyListing, SearchCriteria
from app.routes.str_forecast_models import EvidenceModel, ForecastProperty, ForecastResult
from app.routes.str_models import GateEvidence, StrDeal, StrUnderwriting


class PropertyEligibility(EvidenceModel):
    property: ForecastProperty
    municipality: GateEvidence = Field(default_factory=GateEvidence)
    hoa: GateEvidence = Field(default_factory=GateEvidence)


class AcquisitionCriteria(SearchCriteria):
    model_config = ConfigDict(allow_inf_nan=False)


class AcquisitionSearchCreate(EvidenceModel):
    name: str = Field(min_length=2, max_length=100)
    criteria: AcquisitionCriteria = Field(default_factory=AcquisitionCriteria)
    deal_template: StrDeal = Field(default_factory=StrDeal)
    enabled: bool = False


class AcquisitionSearchOut(AcquisitionSearchCreate):
    id: str
    created_at: str
    updated_at: str
    last_scanned_at: str | None = None


class AcquisitionCandidate(EvidenceModel):
    listing: PropertyListing
    forecast_status: str
    forecast_reason: str
    snapshot_id: str | None = None
    provider_attribution: str | None = None
    forecast_as_of: str | None = None
    municipality: GateEvidence = Field(default_factory=GateEvidence)
    hoa: GateEvidence = Field(default_factory=GateEvidence)
    status: str
    reasons: list[str]
    underwriting: StrUnderwriting | None = None
    rank: int | None = None


class AcquisitionRun(EvidenceModel):
    id: str
    search_id: str
    scanned_at: str
    status: str
    detail: str
    candidates: list[AcquisitionCandidate]
