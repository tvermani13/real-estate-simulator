from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from app.core.auth import CurrentUser, isoformat, utc_now
from app.core.database import connection, json_dumps, json_loads
from app.routes.str_acquisition_models import AcquisitionRun, AcquisitionSearchCreate, AcquisitionSearchOut, PropertyEligibility
from app.routes.str_forecast_models import ForecastProperty, ForecastResult, LicensedForecastExport
from app.services.str_acquisitions import eligibility_for, scan_acquisitions
from app.services.str_forecasts import get_str_forecast_provider, import_forecast, property_key, purge_expired_evidence, scenario_for_storage, snapshot_by_id

router = APIRouter(prefix="/api/str", tags=["STR evidence and acquisitions"])


@router.post("/forecasts/import", response_model=ForecastResult, status_code=201)
def import_export(request: LicensedForecastExport, user: CurrentUser) -> ForecastResult:
    return import_forecast(user["id"], request)


@router.get("/forecasts/{snapshot_id}", response_model=ForecastResult)
def get_snapshot(snapshot_id: str, user: CurrentUser) -> ForecastResult:
    result = snapshot_by_id(user["id"], snapshot_id)
    if result is None:
        raise HTTPException(404, "Forecast snapshot not found or retention expired")
    return result


@router.delete("/forecasts/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: str, user: CurrentUser) -> Response:
    with connection() as db:
        cursor = db.execute("DELETE FROM str_forecast_snapshots WHERE id=? AND user_id=?", (snapshot_id, user["id"]))
        if not cursor.rowcount:
            raise HTTPException(404, "Forecast snapshot not found")
        # Derived scan results carry licensed figures too; remove this user's affected history.
        rows = db.execute("SELECT id,result_json FROM str_acquisition_runs WHERE user_id=?", (user["id"],)).fetchall()
        for row in rows:
            run = AcquisitionRun.model_validate(json_loads(row["result_json"]))
            if any(c.snapshot_id == snapshot_id for c in run.candidates):
                db.execute("DELETE FROM str_acquisition_runs WHERE id=? AND user_id=?", (row["id"], user["id"]))
    return Response(status_code=204)


@router.post("/forecasts/lookup", response_model=ForecastResult)
async def lookup_forecast(request: ForecastProperty, user: CurrentUser) -> ForecastResult:
    return await get_str_forecast_provider().forecast(request, user["id"])


@router.put("/eligibility", response_model=PropertyEligibility)
def put_eligibility(request: PropertyEligibility, user: CurrentUser) -> PropertyEligibility:
    with connection() as db:
        db.execute(
            """INSERT INTO str_eligibility(user_id,property_key,evidence_json,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(user_id,property_key) DO UPDATE SET evidence_json=excluded.evidence_json, updated_at=excluded.updated_at""",
            (user["id"], property_key(request.property.address), json_dumps(request.model_dump(mode="json")), isoformat(utc_now())),
        )
    return request


@router.post("/eligibility/lookup", response_model=PropertyEligibility)
def lookup_eligibility(request: ForecastProperty, user: CurrentUser) -> PropertyEligibility:
    return eligibility_for(user["id"], request)


def search_out(row: object) -> AcquisitionSearchOut:
    return AcquisitionSearchOut(**json_loads(row["request_json"]), id=row["id"],
                                created_at=row["created_at"], updated_at=row["updated_at"], last_scanned_at=row["last_scanned_at"])


@router.get("/acquisitions", response_model=list[AcquisitionSearchOut])
def list_searches(user: CurrentUser) -> list[AcquisitionSearchOut]:
    with connection() as db:
        rows = db.execute("SELECT * FROM str_acquisition_searches WHERE user_id=? ORDER BY updated_at DESC", (user["id"],)).fetchall()
    return [search_out(row) for row in rows]


@router.post("/acquisitions", response_model=AcquisitionSearchOut, status_code=201)
def create_search(request: AcquisitionSearchCreate, user: CurrentUser) -> AcquisitionSearchOut:
    request.deal_template = scenario_for_storage(request.deal_template)
    search_id, now = str(uuid4()), isoformat(utc_now())
    with connection() as db:
        db.execute(
            "INSERT INTO str_acquisition_searches(id,user_id,name,request_json,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (search_id, user["id"], request.name, json_dumps(request.model_dump(mode="json")), int(request.enabled), now, now),
        )
    return AcquisitionSearchOut(**request.model_dump(), id=search_id, created_at=now, updated_at=now)


@router.put("/acquisitions/{search_id}", response_model=AcquisitionSearchOut)
def update_search(search_id: str, request: AcquisitionSearchCreate, user: CurrentUser) -> AcquisitionSearchOut:
    request.deal_template = scenario_for_storage(request.deal_template)
    with connection() as db:
        cursor = db.execute(
            "UPDATE str_acquisition_searches SET name=?,request_json=?,enabled=?,updated_at=? WHERE id=? AND user_id=?",
            (request.name, json_dumps(request.model_dump(mode="json")), int(request.enabled), isoformat(utc_now()), search_id, user["id"]),
        )
        if not cursor.rowcount:
            raise HTTPException(404, "STR acquisition search not found")
        row = db.execute("SELECT * FROM str_acquisition_searches WHERE id=? AND user_id=?", (search_id, user["id"])).fetchone()
    return search_out(row)


@router.delete("/acquisitions/{search_id}", status_code=204)
def delete_search(search_id: str, user: CurrentUser) -> Response:
    with connection() as db:
        cursor = db.execute("DELETE FROM str_acquisition_searches WHERE id=? AND user_id=?", (search_id, user["id"]))
        if not cursor.rowcount:
            raise HTTPException(404, "STR acquisition search not found")
    return Response(status_code=204)


@router.post("/acquisitions/{search_id}/scan", response_model=AcquisitionRun)
async def scan_search(search_id: str, user: CurrentUser) -> AcquisitionRun:
    return await scan_acquisitions(search_id, user)


@router.get("/acquisitions/{search_id}/runs", response_model=list[AcquisitionRun])
def list_runs(search_id: str, user: CurrentUser) -> list[AcquisitionRun]:
    purge_expired_evidence()
    with connection() as db:
        if not db.execute("SELECT id FROM str_acquisition_searches WHERE id=? AND user_id=?", (search_id, user["id"])).fetchone():
            raise HTTPException(404, "STR acquisition search not found")
        rows = db.execute("SELECT result_json FROM str_acquisition_runs WHERE search_id=? AND user_id=? ORDER BY created_at DESC LIMIT 20", (search_id, user["id"])).fetchall()
    return [AcquisitionRun.model_validate(json_loads(row["result_json"])) for row in rows]
