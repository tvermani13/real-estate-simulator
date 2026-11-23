from __future__ import annotations

import logging
import sqlite3
from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.core.auth import (
    CurrentPrincipal,
    LegacyOnly,
    authenticate_user,
    create_session,
    create_user,
    isoformat,
    revoke_session,
    utc_now,
)
from app.core.config import settings
from app.core.database import connection, json_dumps, json_loads
from app.core.scope import Scope
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
logger = logging.getLogger(__name__)


def _user_out(user: dict[str, str]) -> UserOut:
    return UserOut(**user)


def _profile_for(scope: Scope) -> FinancialProfile:
    where, params = scope.match()
    with connection() as db:
        row = db.execute(f"SELECT profile_json FROM financial_profiles WHERE {where}", params).fetchone()
    return FinancialProfile.model_validate(json_loads(row["profile_json"])) if row else FinancialProfile()


def _save_profile(scope: Scope, profile: FinancialProfile) -> None:
    now = isoformat(utc_now())
    # A legacy profile keeps its historical id (the account id); a platform one gets its own.
    profile_id = scope.user_id or str(uuid4())
    columns = ", ".join(scope.columns())
    marks = ", ".join("?" for _ in scope.columns())
    with connection() as db:
        db.execute(
            f"""
            INSERT INTO financial_profiles (id, {columns}, profile_json, updated_at) VALUES (?, {marks}, ?, ?)
            ON CONFLICT({scope.conflict_target()}) DO UPDATE SET
                profile_json = excluded.profile_json, updated_at = excluded.updated_at
            """,
            (profile_id, *scope.values(), json_dumps(profile.model_dump()), now),
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


def _get_search(search_id: str, scope: Scope) -> SavedSearchOut:
    where, params = scope.match()
    with connection() as db:
        row = db.execute(
            f"SELECT * FROM saved_searches WHERE id = ? AND {where}", (search_id, *params)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return _saved_search_from_row(row)


def _require_notifications_allowed(scope: Scope, req: SavedSearchCreate) -> None:
    """Platform sign-in cannot enable email alerts yet.

    Alerts are sent by a background job and to an address the platform has not
    verified for this person. Both wait for worker authorization (platform P5)
    and a verified destination, so a platform search stays a manual, on-screen scan.
    """
    if scope.is_platform and (req.notifications_enabled or req.notification_email):
        raise HTTPException(
            status_code=409,
            detail="Email alerts are not available with platform sign-in yet. Scan from this page instead.",
        )


@router.post("/auth/register", response_model=AuthResponse, status_code=201, dependencies=[LegacyOnly])
def register(req: RegisterRequest, response: Response) -> AuthResponse:
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail="Account registration is disabled")
    user = create_user(req.name, req.email, req.password)
    _save_profile(Scope.legacy(user["id"]), FinancialProfile())
    create_session(user["id"], response)
    return AuthResponse(user=_user_out(user))


@router.post("/auth/login", response_model=AuthResponse, dependencies=[LegacyOnly])
def login(req: LoginRequest, response: Response) -> AuthResponse:
    user = authenticate_user(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    create_session(user["id"], response)
    return AuthResponse(user=_user_out(user))


@router.post("/auth/logout", status_code=204, response_class=Response, dependencies=[LegacyOnly])
def logout(
    response: Response,
    session_cookie: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> Response:
    revoke_session(session_cookie, response)
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=AuthResponse)
def me(principal: CurrentPrincipal) -> AuthResponse:
    return AuthResponse(
        user=_user_out(principal.display),
        sign_in="legacy" if principal.user is not None else "platform",
        workspace_id=principal.scope.workspace_id,
    )


@router.get("/profile", response_model=FinancialProfile)
def get_profile(principal: CurrentPrincipal) -> FinancialProfile:
    return _profile_for(principal.scope)


@router.put("/profile", response_model=FinancialProfile)
def put_profile(profile: FinancialProfile, principal: CurrentPrincipal) -> FinancialProfile:
    _save_profile(principal.scope, profile)
    return profile


@router.get("/affordability", response_model=AffordabilityResponse)
def affordability(principal: CurrentPrincipal) -> AffordabilityResponse:
    return calculate_affordability(_profile_for(principal.scope))


@router.get("/property-provider", response_model=ProviderStatus)
def property_provider_status(_principal: CurrentPrincipal) -> ProviderStatus:
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
def list_searches(principal: CurrentPrincipal) -> list[SavedSearchOut]:
    where, params = principal.scope.match()
    with connection() as db:
        rows = db.execute(
            f"SELECT * FROM saved_searches WHERE {where} ORDER BY updated_at DESC", params
        ).fetchall()
    return [_saved_search_from_row(row) for row in rows]


@router.post("/searches", response_model=SavedSearchOut, status_code=201)
def create_search(req: SavedSearchCreate, principal: CurrentPrincipal) -> SavedSearchOut:
    scope = principal.scope
    _require_notifications_allowed(scope, req)
    now = isoformat(utc_now())
    search_id = str(uuid4())
    notification_email = req.notification_email or (
        principal.user["email"] if principal.user and req.notifications_enabled else None
    )
    columns = ", ".join(scope.columns())
    marks = ", ".join("?" for _ in scope.columns())
    with connection() as db:
        db.execute(
            f"""
            INSERT INTO saved_searches
            (id, {columns}, name, criteria_json, notifications_enabled, notification_email, created_at, updated_at)
            VALUES (?, {marks}, ?, ?, ?, ?, ?, ?)
            """,
            (
                search_id,
                *scope.values(),
                req.name.strip(),
                json_dumps(req.criteria.model_dump()),
                int(req.notifications_enabled),
                notification_email,
                now,
                now,
            ),
        )
    return _get_search(search_id, scope)


@router.put("/searches/{search_id}", response_model=SavedSearchOut)
def update_search(search_id: str, req: SavedSearchCreate, principal: CurrentPrincipal) -> SavedSearchOut:
    scope = principal.scope
    _get_search(search_id, scope)
    _require_notifications_allowed(scope, req)
    now = isoformat(utc_now())
    where, params = scope.match()
    with connection() as db:
        db.execute(
            f"""
            UPDATE saved_searches
            SET name = ?, criteria_json = ?, notifications_enabled = ?, notification_email = ?, updated_at = ?
            WHERE id = ? AND {where}
            """,
            (
                req.name.strip(),
                json_dumps(req.criteria.model_dump()),
                int(req.notifications_enabled),
                req.notification_email,
                now,
                search_id,
                *params,
            ),
        )
    return _get_search(search_id, scope)


@router.delete("/searches/{search_id}", status_code=204, response_class=Response)
def delete_search(search_id: str, principal: CurrentPrincipal) -> Response:
    scope = principal.scope
    _get_search(search_id, scope)
    where, params = scope.match()
    with connection() as db:
        db.execute(f"DELETE FROM saved_searches WHERE id = ? AND {where}", (search_id, *params))
    return Response(status_code=204)


@router.get("/searches/{search_id}/matches", response_model=list[PropertyMatch])
def saved_matches(search_id: str, principal: CurrentPrincipal) -> list[PropertyMatch]:
    scope = principal.scope
    _get_search(search_id, scope)
    where, params = scope.match("s")
    with connection() as db:
        # The parent is joined under the scope, so a match is never read through a search that moved.
        rows = db.execute(
            f"""
            SELECT m.match_json FROM listing_matches m
            JOIN saved_searches s ON s.id = m.search_id
            WHERE m.search_id = ? AND {where}
            ORDER BY m.match_score DESC, m.last_seen_at DESC
            """,
            (search_id, *params),
        ).fetchall()
    return [PropertyMatch.model_validate(json_loads(row["match_json"])) for row in rows]


def _acquire_scan_lease(search_id: str) -> str:
    now = utc_now()
    acquired_at = isoformat(now)
    expires_at = isoformat(now + timedelta(minutes=max(1, settings.scan_lease_minutes)))
    lease_token = str(uuid4())
    try:
        with connection() as db:
            db.execute("DELETE FROM scan_leases WHERE expires_at <= ?", (acquired_at,))
            db.execute(
                """
                INSERT INTO scan_leases (search_id, lease_token, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (search_id, lease_token, acquired_at, expires_at),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="This saved search is already being scanned",
        ) from exc
    return lease_token


def _release_scan_lease(search_id: str, lease_token: str) -> None:
    with connection() as db:
        db.execute(
            "DELETE FROM scan_leases WHERE search_id = ? AND lease_token = ?",
            (search_id, lease_token),
        )


@router.post("/searches/{search_id}/scan", response_model=ScanResponse)
async def scan_search(search_id: str, principal: CurrentPrincipal) -> ScanResponse:
    saved_search = _get_search(search_id, principal.scope)
    lease_token = _acquire_scan_lease(search_id)
    try:
        return await _run_scan(search_id, principal.scope, saved_search)
    finally:
        _release_scan_lease(search_id, lease_token)


async def _run_scan(
    search_id: str,
    scope: Scope,
    saved_search: SavedSearchOut,
) -> ScanResponse:
    profile = _profile_for(scope)
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
    owner_where, owner_params = scope.match()
    with connection() as db:
        # Take the write lock and confirm the search still belongs to this scope: the provider call
        # above can be long, and nothing may be stored under a scope that no longer owns the search.
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            f"SELECT 1 FROM saved_searches WHERE id = ? AND {owner_where}", (search_id, *owner_params)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="Saved search not found")
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
            f"UPDATE saved_searches SET last_scanned_at = ?, updated_at = ? WHERE id = ? AND {owner_where}",
            (now, now, search_id, *owner_params),
        )

    notification_status = "Notifications are off"
    # Alerts go to legacy accounts only. This guard is independent of the request checks, so a row
    # that somehow carries an enabled flag and a recipient still sends nothing for a platform scope.
    if not scope.is_platform and saved_search.notifications_enabled and saved_search.notification_email:
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
        except Exception:
            logger.exception("Email delivery failed for saved search %s", search_id)
            notification_status = "Matches saved, but email delivery failed; retry later"

    refreshed_search = _get_search(search_id, scope)
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
def list_simulations(principal: CurrentPrincipal) -> list[SavedSimulationOut]:
    where, params = principal.scope.match()
    with connection() as db:
        rows = db.execute(
            f"SELECT * FROM saved_simulations WHERE {where} ORDER BY updated_at DESC", params
        ).fetchall()
    return [_simulation_from_row(row) for row in rows]


@router.post("/simulations", response_model=SavedSimulationOut, status_code=201)
def save_simulation(req: SavedSimulationCreate, principal: CurrentPrincipal) -> SavedSimulationOut:
    scope = principal.scope
    now = isoformat(utc_now())
    simulation_id = str(uuid4())
    columns = ", ".join(scope.columns())
    marks = ", ".join("?" for _ in scope.columns())
    where, params = scope.match()
    with connection() as db:
        db.execute(
            f"""
            INSERT INTO saved_simulations (id, {columns}, name, inputs_json, created_at, updated_at)
            VALUES (?, {marks}, ?, ?, ?, ?)
            """,
            (simulation_id, *scope.values(), req.name.strip(), json_dumps(req.inputs), now, now),
        )
        row = db.execute(
            f"SELECT * FROM saved_simulations WHERE id = ? AND {where}", (simulation_id, *params)
        ).fetchone()
    return _simulation_from_row(row)


@router.delete("/simulations/{simulation_id}", status_code=204, response_class=Response)
def delete_simulation(simulation_id: str, principal: CurrentPrincipal) -> Response:
    where, params = principal.scope.match()
    with connection() as db:
        cursor = db.execute(f"DELETE FROM saved_simulations WHERE id = ? AND {where}", (simulation_id, *params))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Saved simulation not found")
    return Response(status_code=204)
