from __future__ import annotations

import math
from datetime import date, timedelta
from uuid import uuid4

from fastapi import HTTPException

from app.core.auth import isoformat, utc_now
from app.core.config import settings
from app.core.database import connection, json_dumps, json_loads
from app.engine.str_underwriting import analyze_str
from app.routes.product_models import PropertyListing
from app.routes.str_acquisition_models import AcquisitionCandidate, AcquisitionRun, AcquisitionSearchCreate, PropertyEligibility
from app.routes.str_forecast_models import ForecastProperty
from app.routes.str_models import StrDeal
from app.services.property_providers import PropertyProviderError, RentCastPropertyProvider
from app.services.str_forecasts import apply_forecast, get_str_forecast_provider, property_key, purge_expired_evidence


def eligibility_for(user_id: str, subject: ForecastProperty) -> PropertyEligibility:
    with connection() as db:
        row = db.execute("SELECT evidence_json FROM str_eligibility WHERE user_id=? AND property_key=?",
                         (user_id, property_key(subject.address))).fetchone()
    if row:
        record = PropertyEligibility.model_validate(json_loads(row["evidence_json"]))
        if (record.property.property_type.casefold() == subject.property_type.casefold()
                and record.property.bedrooms == subject.bedrooms and record.property.bathrooms == subject.bathrooms):
            return record
    return PropertyEligibility(property=subject)


def _eligible_listing(listing: PropertyListing, search: AcquisitionSearchCreate) -> bool:
    c = search.criteria
    return (listing.provider == "rentcast" and math.isfinite(listing.price) and listing.price > 0
            and listing.price <= 1_000_000_000 and listing.bedrooms <= 30 and listing.bathrooms <= 30
            and math.isfinite(listing.hoa_monthly) and listing.hoa_monthly >= 0
            and listing.hoa_monthly * 12 <= 1_000_000_000
            and listing.bedrooms >= c.min_bedrooms and listing.bathrooms >= c.min_bathrooms
            and (c.min_price is None or listing.price >= c.min_price)
            and (c.max_price is None or listing.price <= c.max_price)
            and (not c.property_types or listing.property_type in c.property_types)
            and (c.max_days_on_market is None or (listing.days_on_market is not None and listing.days_on_market <= c.max_days_on_market)))


async def scan_acquisitions(search_id: str, user: dict[str, str]) -> AcquisitionRun:
    purge_expired_evidence()
    token, now = str(uuid4()), utc_now()
    with connection() as db:
        row = db.execute("SELECT * FROM str_acquisition_searches WHERE id=? AND user_id=?", (search_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "STR acquisition search not found")
        search = AcquisitionSearchCreate.model_validate(json_loads(row["request_json"]))
        cursor = db.execute(
            """INSERT INTO str_acquisition_leases(search_id,lease_token,expires_at) VALUES(?,?,?)
               ON CONFLICT(search_id) DO UPDATE SET lease_token=excluded.lease_token, expires_at=excluded.expires_at
               WHERE str_acquisition_leases.expires_at <= ?""",
            (search_id, token, isoformat(now + timedelta(minutes=settings.scan_lease_minutes)), isoformat(now)),
        )
        if not cursor.rowcount:
            raise HTTPException(409, "An acquisition scan is already running")
    try:
        run = AcquisitionRun(id=str(uuid4()), search_id=search_id, scanned_at=isoformat(now),
                             status="completed", detail="Screening is research, not purchase approval.", candidates=[])
        retention = now.date() + timedelta(days=365)
        if settings.property_provider.lower() != "rentcast" or not settings.rentcast_api_key:
            run.status, run.detail = "unavailable", "RentCast sale-listing access is unavailable; no demo acquisition recommendations generated."
        else:
            provider = RentCastPropertyProvider(settings.rentcast_api_key)
            # Sales only. Long-term rental comps must never supply STR income assumptions.
            criteria = search.criteria.model_copy(update={"purpose": "primary"})
            try:
                listings = await provider.sale_listings(criteria)
            except PropertyProviderError:
                listings = []
                run.status, run.detail = "unavailable", "RentCast sale listings could not be retrieved; retry after checking provider access."
            seen: set[str] = set()
            for listing in listings:
                key = property_key(listing.address)
                if key in seen or not _eligible_listing(listing, search):
                    continue
                seen.add(key)
                subject = ForecastProperty(address=listing.address, property_type=listing.property_type,
                                           bedrooms=listing.bedrooms, bathrooms=listing.bathrooms,
                                           provider_property_id=listing.id)
                eligibility = eligibility_for(user["id"], subject)
                forecast = await get_str_forecast_provider().forecast(subject, user["id"])
                legal = (eligibility.municipality.current_status(), eligibility.hoa.current_status())
                candidate = AcquisitionCandidate(
                    listing=listing.model_copy(update={"estimated_rent": None, "rent_estimate_source": None}),
                    forecast_status=forecast.status, forecast_reason=forecast.reason,
                    snapshot_id=forecast.snapshot_id, municipality=eligibility.municipality, hoa=eligibility.hoa,
                    status="research_only", reasons=[],
                )
                if forecast.forecast:
                    retention = min(retention, forecast.forecast.retention_until)
                    candidate.provider_attribution = forecast.forecast.attribution
                    candidate.forecast_as_of = forecast.forecast.as_of.isoformat()
                if "blocked" in legal:
                    candidate.status = "blocked"
                    candidate.reasons.append("Municipality or HOA/deed evidence prohibits STR use.")
                elif legal != ("verified", "verified"):
                    candidate.reasons.append("Current written municipality and HOA/deed eligibility are required.")
                if forecast.status != "available":
                    candidate.reasons.append(forecast.reason)
                else:
                    payload = search.deal_template.model_dump()
                    payload.update(address=listing.address, property_price=listing.price,
                                   hoa_annual=listing.hoa_monthly * 12,
                                   regulatory_gate=legal[0], hoa_gate=legal[1],
                                   regulatory_evidence=eligibility.municipality, hoa_evidence=eligibility.hoa)
                    deal = apply_forecast(StrDeal.model_validate(payload), forecast)
                    candidate.underwriting = analyze_str(deal, forecast_verified=True)
                    candidate.status = candidate.underwriting.screening_status
                    c, out = search.criteria, candidate.underwriting
                    additional_screen = (
                        (c.min_cap_rate is None or out.cap_rate >= c.min_cap_rate)
                        and (c.min_dscr is None or out.debt_service_coverage is None or out.debt_service_coverage >= c.min_dscr)
                        and (c.min_cash_on_cash is None or (out.cash_on_cash is not None and out.cash_on_cash >= c.min_cash_on_cash))
                        and (c.min_monthly_cashflow is None or out.annual_cash_flow / 12 >= c.min_monthly_cashflow)
                    )
                    if candidate.status == "meets_financial_screen" and not additional_screen:
                        candidate.status = "below_financial_screen"
                        candidate.reasons.append("Does not meet the additional return thresholds saved for this search.")
                    if candidate.status == "below_financial_screen":
                        candidate.reasons.append("Requires DSCR ≥1.25, cash-on-cash ≥8%, and nonnegative cash flow under a 20% revenue decline.")
                run.candidates.append(candidate)
            qualified = [c for c in run.candidates if c.status == "meets_financial_screen"]
            qualified.sort(key=lambda c: c.underwriting.downside_cash_flow, reverse=True)
            for rank, candidate in enumerate(qualified, 1):
                candidate.rank = rank
            run.candidates.sort(key=lambda c: (c.rank is None, c.rank or 0, c.listing.address))
        with connection() as db:
            db.execute(
                "INSERT INTO str_acquisition_runs(id,search_id,user_id,result_json,retention_until,created_at) VALUES(?,?,?,?,?,?)",
                (run.id, search_id, user["id"], json_dumps(run.model_dump(mode="json")), retention.isoformat(), run.scanned_at),
            )
            db.execute("UPDATE str_acquisition_searches SET last_scanned_at=? WHERE id=? AND user_id=?",
                       (run.scanned_at, search_id, user["id"]))
        return run
    finally:
        with connection() as db:
            db.execute("DELETE FROM str_acquisition_leases WHERE search_id=? AND lease_token=?", (search_id, token))
