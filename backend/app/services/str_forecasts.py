from __future__ import annotations

import calendar
import hashlib
import sqlite3
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from uuid import uuid4

from app.core.database import connection, json_dumps, json_loads
from app.routes.str_forecast_models import ForecastProperty, ForecastResult, LicensedForecastExport
from app.routes.str_models import StrDeal


def property_key(address: str) -> str:
    # Exact identity after case/spacing normalization; never fuzzy-match a nearby property.
    return " ".join(address.casefold().split())


def purge_expired_evidence(today: date | None = None) -> None:
    day = (today or date.today()).isoformat()
    with connection() as db:
        db.execute("DELETE FROM str_forecast_snapshots WHERE retention_until < ?", (day,))
        db.execute("DELETE FROM str_acquisition_runs WHERE retention_until < ?", (day,))


def assess_snapshot(row: sqlite3.Row, subject: ForecastProperty | None = None) -> ForecastResult:
    forecast = LicensedForecastExport.model_validate(json_loads(row["forecast_json"]))
    count = len(forecast.qualified_comparables())
    today = date.today()
    current_month = date(today.year, today.month, 1)
    start = forecast.months[0].month
    if forecast.retention_until < today:
        return ForecastResult(status="license_expired", reason="Licensed retention period has expired.")
    if subject and (
        property_key(subject.address) != property_key(forecast.property.address)
        or subject.property_type.casefold() != forecast.property.property_type.casefold()
        or subject.bedrooms != forecast.property.bedrooms or subject.bathrooms != forecast.property.bathrooms
    ):
        status, reason = "property_mismatch", "Forecast address or property attributes do not match this listing."
    elif (today - forecast.as_of).days > 90 or start < current_month or (start - current_month).days > 62:
        status, reason = "stale", "Forecast needs current evidence (within 90 days) and a current/upcoming 12-month horizon."
    elif count < 8:
        status, reason = "insufficient_evidence", "Fewer than eight eligible comparable rentals support this property forecast."
    else:
        status, reason = "available", "Licensed property export validated for this property; license and legal review remain user responsibilities."
    return ForecastResult(status=status, reason=reason, snapshot_id=row["id"],
                          imported_at=row["imported_at"], qualified_comparable_count=count, forecast=forecast)


def import_forecast(user_id: str, forecast: LicensedForecastExport) -> ForecastResult:
    if forecast.retention_until < date.today():
        return ForecastResult(status="license_expired", reason="Export retention permission has already expired; nothing stored.")
    purge_expired_evidence()
    payload = json_dumps(forecast.model_dump(mode="json"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute(
            """INSERT INTO str_forecast_snapshots
               (id,user_id,property_key,content_hash,forecast_json,as_of,imported_at,retention_until)
               VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,content_hash) DO NOTHING""",
            (str(uuid4()), user_id, property_key(forecast.property.address), digest, payload,
             forecast.as_of.isoformat(), now, forecast.retention_until.isoformat()),
        )
        row = db.execute("SELECT * FROM str_forecast_snapshots WHERE user_id=? AND content_hash=?",
                         (user_id, digest)).fetchone()
    return assess_snapshot(row)


def snapshot_by_id(user_id: str, snapshot_id: str) -> ForecastResult | None:
    purge_expired_evidence()
    with connection() as db:
        row = db.execute("SELECT * FROM str_forecast_snapshots WHERE id=? AND user_id=?",
                         (snapshot_id, user_id)).fetchone()
    return assess_snapshot(row) if row else None


class StrForecastProvider(ABC):
    """Adapters return evidence or an explicit unavailable state; never market-average fallbacks."""

    @abstractmethod
    async def forecast(self, subject: ForecastProperty, user_id: str) -> ForecastResult:
        raise NotImplementedError


class LicensedExportForecastProvider(StrForecastProvider):
    async def forecast(self, subject: ForecastProperty, user_id: str) -> ForecastResult:
        purge_expired_evidence()
        with connection() as db:
            row = db.execute(
                """SELECT * FROM str_forecast_snapshots WHERE user_id=? AND property_key=?
                   ORDER BY as_of DESC, imported_at DESC, rowid DESC LIMIT 1""",
                (user_id, property_key(subject.address)),
            ).fetchone()
        return assess_snapshot(row, subject) if row else ForecastResult(
            status="unavailable", reason="No licensed property-specific export is available for this address."
        )


def get_str_forecast_provider() -> StrForecastProvider:
    return LicensedExportForecastProvider()


def apply_forecast(deal: StrDeal, result: ForecastResult) -> StrDeal:
    forecast = result.forecast
    if forecast is None or result.status != "available":
        raise ValueError("A validated current property forecast is required")
    revenues, days = [0.0] * 12, [0] * 12
    for month in forecast.months:
        revenues[month.month.month - 1] = month.gross_revenue
        days[month.month.month - 1] = calendar.monthrange(month.month.year, month.month.month)[1]
    payload = deal.model_dump()
    payload.update(annual_gross_revenue=sum(revenues), monthly_gross_revenue=revenues,
                   monthly_calendar_days=days, revenue_source="licensed_property_forecast",
                   forecast_as_of=forecast.as_of, comparable_count=result.qualified_comparable_count,
                   forecast_snapshot_id=result.snapshot_id)
    return StrDeal.model_validate(payload)


def scenario_for_storage(deal: StrDeal) -> StrDeal:
    if not deal.forecast_snapshot_id:
        return deal
    # Retain a reference, not a duplicate licensed dataset beyond its retention term.
    return StrDeal.model_validate({**deal.model_dump(), "monthly_gross_revenue": None,
                                   "annual_gross_revenue": 0, "forecast_as_of": None,
                                   "comparable_count": 0})
