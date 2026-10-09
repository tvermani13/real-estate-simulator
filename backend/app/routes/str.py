from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from app.core.auth import CurrentUser, isoformat, utc_now
from app.core.database import connection, json_dumps, json_loads
from app.engine.str_underwriting import analyze_str
from app.routes.str_models import StrDeal, StrScenarioCreate, StrScenarioOut, StrUnderwriting

router = APIRouter(prefix="/api/str", tags=["short-term rentals"])


@router.post("/underwrite", response_model=StrUnderwriting)
def underwrite(deal: StrDeal, user: CurrentUser) -> StrUnderwriting:
    return analyze_str(deal)


def _row_to_scenario(row: object) -> StrScenarioOut:
    return StrScenarioOut(
        id=row["id"], name=row["name"],
        deal=StrDeal.model_validate(json_loads(row["deal_json"])),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


@router.get("/scenarios", response_model=list[StrScenarioOut])
def list_scenarios(user: CurrentUser) -> list[StrScenarioOut]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM str_scenarios WHERE user_id = ? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    return [_row_to_scenario(row) for row in rows]


@router.post("/scenarios", response_model=StrScenarioOut, status_code=201)
def save_scenario(request: StrScenarioCreate, user: CurrentUser) -> StrScenarioOut:
    scenario_id, now = str(uuid4()), isoformat(utc_now())
    with connection() as db:
        db.execute(
            """INSERT INTO str_scenarios
               (id, user_id, name, deal_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scenario_id, user["id"], request.name, json_dumps(request.deal.model_dump()), now, now),
        )
    return StrScenarioOut(id=scenario_id, name=request.name, deal=request.deal, created_at=now, updated_at=now)


@router.put("/scenarios/{scenario_id}", response_model=StrScenarioOut)
def update_scenario(scenario_id: str, request: StrScenarioCreate, user: CurrentUser) -> StrScenarioOut:
    now = isoformat(utc_now())
    with connection() as db:
        cursor = db.execute(
            """UPDATE str_scenarios SET name = ?, deal_json = ?, updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (request.name, json_dumps(request.deal.model_dump()), now, scenario_id, user["id"]),
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404, detail="STR scenario not found")
        row = db.execute("SELECT * FROM str_scenarios WHERE id = ? AND user_id = ?", (scenario_id, user["id"])).fetchone()
    return _row_to_scenario(row)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, user: CurrentUser) -> Response:
    with connection() as db:
        cursor = db.execute(
            "DELETE FROM str_scenarios WHERE id = ? AND user_id = ?", (scenario_id, user["id"])
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404, detail="STR scenario not found")
    return Response(status_code=204)
