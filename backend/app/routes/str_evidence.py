from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from app.core.auth import CurrentPrincipal, isoformat, utc_now
from app.core.database import connection, json_dumps, json_loads
from app.core.scope import Scope
from app.routes.str_acquisition_models import AcquisitionRun, AcquisitionSearchCreate, AcquisitionSearchOut, PropertyEligibility
from app.routes.str_forecast_models import ForecastProperty, ForecastResult, LicensedForecastExport
from app.services.str_acquisitions import eligibility_for, scan_acquisitions
from app.services.str_forecasts import get_str_forecast_provider, import_forecast, property_key, retire_expired_for_read, scenario_for_storage, snapshot_by_id

router = APIRouter(prefix="/api/str", tags=["STR evidence and acquisitions"])


@router.post("/forecasts/import", response_model=ForecastResult, status_code=201)
def import_export(request: LicensedForecastExport, principal: CurrentPrincipal) -> ForecastResult:
    return import_forecast(principal.scope, request)


@router.get("/forecasts/{snapshot_id}", response_model=ForecastResult)
def get_snapshot(snapshot_id: str, principal: CurrentPrincipal) -> ForecastResult:
    result = snapshot_by_id(principal.scope, snapshot_id)
    if result is None:
        raise HTTPException(404, "Forecast snapshot not found or retention expired")
    return result


@router.delete("/forecasts/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: str, principal: CurrentPrincipal) -> Response:
    where, params = principal.scope.match()
    with connection() as db:
        cursor = db.execute(f"DELETE FROM str_forecast_snapshots WHERE id=? AND {where}", (snapshot_id, *params))
        if not cursor.rowcount:
            raise HTTPException(404, "Forecast snapshot not found")
        # Derived scan results carry licensed figures too; remove this user's affected history.
        rows = db.execute(f"SELECT id,result_json FROM str_acquisition_runs WHERE {where}", params).fetchall()
        for row in rows:
            run = AcquisitionRun.model_validate(json_loads(row["result_json"]))
            if any(c.snapshot_id == snapshot_id for c in run.candidates):
                db.execute(f"DELETE FROM str_acquisition_runs WHERE id=? AND {where}", (row["id"], *params))
    return Response(status_code=204)


@router.post("/forecasts/lookup", response_model=ForecastResult)
async def lookup_forecast(request: ForecastProperty, principal: CurrentPrincipal) -> ForecastResult:
    return await get_str_forecast_provider().forecast(request, principal.scope)


@router.put("/eligibility", response_model=PropertyEligibility)
def put_eligibility(request: PropertyEligibility, principal: CurrentPrincipal) -> PropertyEligibility:
    scope = principal.scope
    columns, marks = ",".join(scope.columns()), ",".join("?" for _ in scope.columns())
    with connection() as db:
        db.execute(
            f"""INSERT INTO str_eligibility({columns},property_key,evidence_json,updated_at) VALUES({marks},?,?,?)
               ON CONFLICT({scope.conflict_target("property_key")}) DO UPDATE SET evidence_json=excluded.evidence_json, updated_at=excluded.updated_at""",
            (*scope.values(), property_key(request.property.address), json_dumps(request.model_dump(mode="json")), isoformat(utc_now())),
        )
    return request


@router.post("/eligibility/lookup", response_model=PropertyEligibility)
def lookup_eligibility(request: ForecastProperty, principal: CurrentPrincipal) -> PropertyEligibility:
    return eligibility_for(principal.scope, request)


def _require_manual_scan_only(scope: Scope, request: AcquisitionSearchCreate) -> None:
    """A platform search is scanned by hand. The scheduled scan waits for platform worker authorization (P5)."""
    if scope.is_platform and request.enabled:
        raise HTTPException(
            status_code=409,
            detail="Scheduled acquisition scans are not available with platform sign-in yet. Scan from this page instead.",
        )


def search_out(row: object) -> AcquisitionSearchOut:
    return AcquisitionSearchOut(**json_loads(row["request_json"]), id=row["id"],
                                created_at=row["created_at"], updated_at=row["updated_at"], last_scanned_at=row["last_scanned_at"])


@router.get("/acquisitions", response_model=list[AcquisitionSearchOut])
def list_searches(principal: CurrentPrincipal) -> list[AcquisitionSearchOut]:
    where, params = principal.scope.match()
    with connection() as db:
        rows = db.execute(f"SELECT * FROM str_acquisition_searches WHERE {where} ORDER BY updated_at DESC", params).fetchall()
    return [search_out(row) for row in rows]


@router.post("/acquisitions", response_model=AcquisitionSearchOut, status_code=201)
def create_search(request: AcquisitionSearchCreate, principal: CurrentPrincipal) -> AcquisitionSearchOut:
    scope = principal.scope
    _require_manual_scan_only(scope, request)
    request.deal_template = scenario_for_storage(request.deal_template)
    search_id, now = str(uuid4()), isoformat(utc_now())
    columns, marks = ",".join(scope.columns()), ",".join("?" for _ in scope.columns())
    with connection() as db:
        db.execute(
            f"INSERT INTO str_acquisition_searches(id,{columns},name,request_json,enabled,created_at,updated_at) VALUES(?,{marks},?,?,?,?,?)",
            (search_id, *scope.values(), request.name, json_dumps(request.model_dump(mode="json")), int(request.enabled), now, now),
        )
    return AcquisitionSearchOut(**request.model_dump(), id=search_id, created_at=now, updated_at=now)


@router.put("/acquisitions/{search_id}", response_model=AcquisitionSearchOut)
def update_search(search_id: str, request: AcquisitionSearchCreate, principal: CurrentPrincipal) -> AcquisitionSearchOut:
    scope = principal.scope
    _require_manual_scan_only(scope, request)
    request.deal_template = scenario_for_storage(request.deal_template)
    where, params = scope.match()
    with connection() as db:
        cursor = db.execute(
            f"UPDATE str_acquisition_searches SET name=?,request_json=?,enabled=?,updated_at=? WHERE id=? AND {where}",
            (request.name, json_dumps(request.model_dump(mode="json")), int(request.enabled), isoformat(utc_now()), search_id, *params),
        )
        if not cursor.rowcount:
            raise HTTPException(404, "STR acquisition search not found")
        row = db.execute(f"SELECT * FROM str_acquisition_searches WHERE id=? AND {where}", (search_id, *params)).fetchone()
    return search_out(row)


@router.delete("/acquisitions/{search_id}", status_code=204)
def delete_search(search_id: str, principal: CurrentPrincipal) -> Response:
    where, params = principal.scope.match()
    with connection() as db:
        cursor = db.execute(f"DELETE FROM str_acquisition_searches WHERE id=? AND {where}", (search_id, *params))
        if not cursor.rowcount:
            raise HTTPException(404, "STR acquisition search not found")
    return Response(status_code=204)


@router.post("/acquisitions/{search_id}/scan", response_model=AcquisitionRun)
async def scan_search(search_id: str, principal: CurrentPrincipal) -> AcquisitionRun:
    return await scan_acquisitions(search_id, principal.scope)


@router.get("/acquisitions/{search_id}/runs", response_model=list[AcquisitionRun])
def list_runs(search_id: str, principal: CurrentPrincipal) -> list[AcquisitionRun]:
    retire_expired_for_read(principal.scope)
    where, params = principal.scope.match()
    with connection() as db:
        if not db.execute(f"SELECT id FROM str_acquisition_searches WHERE id=? AND {where}", (search_id, *params)).fetchone():
            raise HTTPException(404, "STR acquisition search not found")
        rows = db.execute(f"SELECT result_json FROM str_acquisition_runs WHERE search_id=? AND {where} AND retention_until >= ? ORDER BY created_at DESC LIMIT 20", (search_id, *params, date.today().isoformat())).fetchall()
    return [AcquisitionRun.model_validate(json_loads(row["result_json"])) for row in rows]
