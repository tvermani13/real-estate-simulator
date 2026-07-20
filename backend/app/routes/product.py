from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.core.auth import (
    CurrentUser,
    authenticate_user,
    create_session,
    create_user,
    isoformat,
    revoke_session,
    utc_now,
)
from app.core.config import settings
from app.core.database import connection, json_dumps, json_loads
from app.engine.affordability import calculate_affordability
from app.engine.property_matcher import analyze_property
from app.routes.product_models import (
    AffordabilityResponse,
    AuthResponse,
    FinancialProfile,
    LoginRequest,
    PropertyMatch,
    ProviderStatus,
    RegisterRequest,
    SavedSearchCreate,
    SavedSearchOut,
    SavedSimulationCreate,
    SavedSimulationOut,
    ScanResponse,
    UserOut,
)
from app.services.notifications import send_match_email
from app.services.property_providers import PropertyProviderError, get_property_provider


router = APIRouter(prefix="/api")


def _user_out(user: dict[str, str]) -> UserOut:
    return UserOut(**user)


def _profile_for(user_id: str) -> FinancialProfile:
    with connection() as db:
        row = db.execute(
            "SELECT profile_json FROM financial_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    return FinancialProfile.model_validate(json_loads(row["profile_json"])) if row else FinancialProfile()


def _save_profile(user_id: str, profile: FinancialProfile) -> None:
    now = isoformat(utc_now())
    with connection() as db:
        db.execute(
            """
            INSERT INTO financial_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at
            """,
            (user_id, json_dumps(profile.model_dump()), now),
        )


def _saved_search_from_row(row: object) -> SavedSearchOut:
    return SavedSearchOut(
        id=row["id"],
        name=row["name"],
        criteria=json_loads(row["criteria_json"]),
        notifications_enabled=bool(row["notifications_enabled"]),
        notification_email=row["notification_email"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_scanned_at=row["last_scanned_at"],
    )


def _get_search(search_id: str, user_id: str) -> SavedSearchOut:
    with connection() as db:
        row = db.execute(
            "SELECT * FROM saved_searches WHERE id = ? AND user_id = ?", (search_id, user_id)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return _saved_search_from_row(row)


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(req: RegisterRequest, response: Response) -> AuthResponse:
    user = create_user(req.name, req.email, req.password)
    _save_profile(user["id"], FinancialProfile())
    create_session(user["id"], response)
    return AuthResponse(user=_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, response: Response) -> AuthResponse:
    user = authenticate_user(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    create_session(user["id"], response)
    return AuthResponse(user=_user_out(user))


@router.post("/auth/logout", status_code=204, response_class=Response)
def logout(
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> Response:
    revoke_session(session_cookie, response)
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=AuthResponse)
def me(user: CurrentUser) -> AuthResponse:
    return AuthResponse(user=_user_out(user))


@router.get("/profile", response_model=FinancialProfile)
def get_profile(user: CurrentUser) -> FinancialProfile:
    return _profile_for(user["id"])


@router.put("/profile", response_model=FinancialProfile)
def put_profile(profile: FinancialProfile, user: CurrentUser) -> FinancialProfile:
    _save_profile(user["id"], profile)
    return profile


@router.get("/affordability", response_model=AffordabilityResponse)
def affordability(user: CurrentUser) -> AffordabilityResponse:
    return calculate_affordability(_profile_for(user["id"]))


@router.get("/property-provider", response_model=ProviderStatus)
def property_provider_status(user: CurrentUser) -> ProviderStatus:
    provider = get_property_provider()
    if provider.mode == "live":
        detail = "Live RentCast sale listings with local rental comps are enabled."
    elif settings.property_provider.lower() == "rentcast":
        detail = "RentCast was selected but no API key is configured, so illustrative listings are active."
    else:
        detail = "Illustrative listings are active. Add a RentCast API key to scan live US listings."
    return ProviderStatus(
        provider=provider.name,
        mode=provider.mode,
        configured=provider.mode == "live",
        detail=detail,
        capabilities=["sale listings", "primary affordability", "rental cash-flow screening"],
    )


@router.get("/searches", response_model=list[SavedSearchOut])
def list_searches(user: CurrentUser) -> list[SavedSearchOut]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM saved_searches WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)
        ).fetchall()
    return [_saved_search_from_row(row) for row in rows]


@router.post("/searches", response_model=SavedSearchOut, status_code=201)
def create_search(req: SavedSearchCreate, user: CurrentUser) -> SavedSearchOut:
    now = isoformat(utc_now())
    search_id = str(uuid4())
    notification_email = req.notification_email or (user["email"] if req.notifications_enabled else None)
    with connection() as db:
        db.execute(
            """
            INSERT INTO saved_searches
            (id, user_id, name, criteria_json, notifications_enabled, notification_email, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                search_id,
                user["id"],
                req.name.strip(),
                json_dumps(req.criteria.model_dump()),
                int(req.notifications_enabled),
                notification_email,
                now,
                now,
            ),
        )
    return _get_search(search_id, user["id"])


@router.put("/searches/{search_id}", response_model=SavedSearchOut)
def update_search(search_id: str, req: SavedSearchCreate, user: CurrentUser) -> SavedSearchOut:
    _get_search(search_id, user["id"])
    now = isoformat(utc_now())
    with connection() as db:
        db.execute(
            """
            UPDATE saved_searches
            SET name = ?, criteria_json = ?, notifications_enabled = ?, notification_email = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                req.name.strip(),
                json_dumps(req.criteria.model_dump()),
                int(req.notifications_enabled),
                req.notification_email,
                now,
                search_id,
                user["id"],
            ),
        )
    return _get_search(search_id, user["id"])


@router.delete("/searches/{search_id}", status_code=204, response_class=Response)
def delete_search(search_id: str, user: CurrentUser) -> Response:
    _get_search(search_id, user["id"])
    with connection() as db:
        db.execute("DELETE FROM saved_searches WHERE id = ? AND user_id = ?", (search_id, user["id"]))
    return Response(status_code=204)


@router.get("/searches/{search_id}/matches", response_model=list[PropertyMatch])
def saved_matches(search_id: str, user: CurrentUser) -> list[PropertyMatch]:
    _get_search(search_id, user["id"])
    with connection() as db:
        rows = db.execute(
            "SELECT match_json FROM listing_matches WHERE search_id = ? ORDER BY match_score DESC, last_seen_at DESC",
            (search_id,),
        ).fetchall()
    return [PropertyMatch.model_validate(json_loads(row["match_json"])) for row in rows]


@router.post("/searches/{search_id}/scan", response_model=ScanResponse)
async def scan_search(search_id: str, user: CurrentUser) -> ScanResponse:
    saved_search = _get_search(search_id, user["id"])
    profile = _profile_for(user["id"])
    affordability_result = calculate_affordability(profile)
    criteria = saved_search.criteria
    if criteria.max_price is None:
        calculated = affordability_result.primary if criteria.purpose == "primary" else affordability_result.investment
        criteria = criteria.model_copy(update={"max_price": calculated.comfortable_max})

    provider = get_property_provider()
    try:
        listings = await provider.sale_listings(criteria)
    except PropertyProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    analyzed = [analyze_property(listing, criteria, profile) for listing in listings]
    analyzed.sort(key=lambda match: match.score, reverse=True)
    now = isoformat(utc_now())
    new_qualifying_count = 0
    pending_notifications: list[PropertyMatch] = []
    persisted: list[PropertyMatch] = []
    with connection() as db:
        for match in analyzed:
            existing = db.execute(
                "SELECT id, notified_at FROM listing_matches WHERE search_id = ? AND provider_listing_id = ?",
                (search_id, match.listing.id),
            ).fetchone()
            is_new = existing is None
            stored_match = match.model_copy(update={"is_new": is_new})
            match_id = str(uuid4()) if is_new else existing["id"]
            db.execute(
                """
                INSERT INTO listing_matches
                (id, search_id, provider_listing_id, match_json, match_score, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_id, provider_listing_id) DO UPDATE SET
                    match_json = excluded.match_json,
                    match_score = excluded.match_score,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    match_id,
                    search_id,
                    match.listing.id,
                    json_dumps(stored_match.model_dump()),
                    match.score,
                    now,
                    now,
                ),
            )
            persisted.append(stored_match)
            if is_new and match.score >= criteria.min_match_score:
                new_qualifying_count += 1
            if match.score >= criteria.min_match_score and (is_new or existing["notified_at"] is None):
                pending_notifications.append(stored_match)
        db.execute(
            "UPDATE saved_searches SET last_scanned_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (now, now, search_id, user["id"]),
        )

    notification_status = "Notifications are off"
    if saved_search.notifications_enabled and saved_search.notification_email:
        try:
            notification_status = send_match_email(
                saved_search.notification_email, saved_search, pending_notifications
            )
            if pending_notifications and notification_status.startswith("Email sent"):
                with connection() as db:
                    db.executemany(
                        "UPDATE listing_matches SET notified_at = ? WHERE search_id = ? AND provider_listing_id = ?",
                        [(now, search_id, match.listing.id) for match in pending_notifications],
                    )
        except Exception as exc:
            notification_status = f"Matches saved, but email delivery failed: {exc}"

    refreshed_search = _get_search(search_id, user["id"])
    return ScanResponse(
        search=refreshed_search,
        provider=provider.name,
        provider_mode=provider.mode,
        scanned_at=now,
        total_scanned=len(listings),
        matches=persisted,
        new_match_count=new_qualifying_count,
        notification_status=notification_status,
    )


def _simulation_from_row(row: object) -> SavedSimulationOut:
    return SavedSimulationOut(
        id=row["id"],
        name=row["name"],
        inputs=json_loads(row["inputs_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/simulations", response_model=list[SavedSimulationOut])
def list_simulations(user: CurrentUser) -> list[SavedSimulationOut]:
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM saved_simulations WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)
        ).fetchall()
    return [_simulation_from_row(row) for row in rows]


@router.post("/simulations", response_model=SavedSimulationOut, status_code=201)
def save_simulation(req: SavedSimulationCreate, user: CurrentUser) -> SavedSimulationOut:
    now = isoformat(utc_now())
    simulation_id = str(uuid4())
    with connection() as db:
        db.execute(
            """
            INSERT INTO saved_simulations (id, user_id, name, inputs_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (simulation_id, user["id"], req.name.strip(), json_dumps(req.inputs), now, now),
        )
        row = db.execute(
            "SELECT * FROM saved_simulations WHERE id = ? AND user_id = ?", (simulation_id, user["id"])
        ).fetchone()
    return _simulation_from_row(row)


@router.delete("/simulations/{simulation_id}", status_code=204, response_class=Response)
def delete_simulation(simulation_id: str, user: CurrentUser) -> Response:
    with connection() as db:
        cursor = db.execute(
            "DELETE FROM saved_simulations WHERE id = ? AND user_id = ?", (simulation_id, user["id"])
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Saved simulation not found")
    return Response(status_code=204)
