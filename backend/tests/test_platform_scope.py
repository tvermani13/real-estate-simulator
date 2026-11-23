"""Platform-owned records: isolation, notification limits, jobs and the restore drill.

The platform principal is injected through the dependency override, the same
seam the platform-context adapter will use (H1b). These tests prove the data
layer and routes keep every scope apart; they do not test sign-in.
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.core.database import connection
from app.core.scope import Scope
from app.main import app
from app.routes.product_models import PropertyListing
from tests.test_str_workflows import synthetic_export

WS_A = "ws_aaaaaaaaaaaaaaaaaaaa"
WS_B = "ws_bbbbbbbbbbbbbbbbbbbb"
SUB_1 = "usr_1111111111111111111111"
SUB_2 = "usr_2222222222222222222222"
NIL = "00000000-0000-4000-8000-000000000000"


def platform(workspace: str, sub: str) -> Principal:
    return Principal(scope=Scope.platform(workspace, sub))


class PlatformScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original = {k: getattr(settings, k) for k in (
            "database_path", "rate_limit_enabled", "registration_enabled", "property_provider", "rentcast_api_key")}
        settings.database_path = str(Path(self.temp.name) / "app.db")
        settings.rate_limit_enabled = False
        settings.registration_enabled = True
        settings.property_provider = "rentcast"
        settings.rentcast_api_key = "synthetic-key"
        self.who = platform(WS_A, SUB_1)
        app.dependency_overrides[current_principal] = lambda: self.who
        self.context = TestClient(app)
        self.client = self.context.__enter__()

    def tearDown(self) -> None:
        app.dependency_overrides.pop(current_principal, None)
        self.context.__exit__(None, None, None)
        for key, value in self.original.items():
            setattr(settings, key, value)
        self.temp.cleanup()

    def as_(self, principal: Principal) -> None:
        self.who = principal

    def sale_listing(self) -> PropertyListing:
        return PropertyListing(id="sale-1", provider="rentcast", address="1 Synthetic Lane, Example, PA",
                               city="Example", state="PA", price=300000, bedrooms=3, bathrooms=2,
                               property_type="Single Family", days_on_market=10, hoa_monthly=100)

    def evidence(self) -> dict:
        return {"status": "verified", "document_reference": "https://example.invalid/written-permission",
                "authority": "Synthetic authority", "checked_on": date.today().isoformat(),
                "valid_until": date.today().replace(year=date.today().year + 1).isoformat()}

    def seed(self) -> dict[str, str]:
        """One record of every private kind for the current principal."""
        ids: dict[str, str] = {}
        r = self.client.put("/api/profile", json={"annual_gross_income": 123456})
        self.assertEqual(r.status_code, 200, r.text)
        ids["search"] = self.client.post("/api/searches", json={"name": "Mine", "criteria": {"max_price": 300000}}).json()["id"]
        ids["simulation"] = self.client.post("/api/simulations", json={"name": "Sim", "inputs": {"a": 1}}).json()["id"]
        ids["scenario"] = self.client.post(
            "/api/str/scenarios", json={"name": "Scenario", "deal": {"address": "9 Private Rd"}}).json()["id"]
        export = synthetic_export()
        forecast = self.client.post("/api/str/forecasts/import", json=export)
        self.assertEqual(forecast.status_code, 201, forecast.text)
        ids["snapshot"] = forecast.json()["snapshot_id"]
        r = self.client.put("/api/str/eligibility", json={
            "property": export["property"], "municipality": self.evidence(), "hoa": self.evidence()})
        self.assertEqual(r.status_code, 200, r.text)
        ids["acquisition"] = self.client.post(
            "/api/str/acquisitions", json={"name": "Acq", "criteria": {"max_price": 400000}}).json()["id"]
        with patch("app.services.str_acquisitions.RentCastPropertyProvider.sale_listings",
                   new=AsyncMock(return_value=[self.sale_listing()])):
            run = self.client.post(f"/api/str/acquisitions/{ids['acquisition']}/scan")
        self.assertEqual(run.status_code, 200, run.text)
        return ids

    def assert_nothing_visible(self, ids: dict[str, str]) -> None:
        c = self.client
        self.assertEqual(c.get("/api/searches").json(), [])
        self.assertEqual(c.get("/api/simulations").json(), [])
        self.assertEqual(c.get("/api/str/scenarios").json(), [])
        self.assertEqual(c.get("/api/str/acquisitions").json(), [])
        self.assertEqual(c.get("/api/profile").json()["annual_gross_income"], 180_000)
        export = synthetic_export()
        self.assertEqual(c.post("/api/str/forecasts/lookup", json=export["property"]).json()["status"], "unavailable")
        eligibility = c.post("/api/str/eligibility/lookup", json=export["property"]).json()
        self.assertNotEqual(eligibility["municipality"]["status"], "verified")
        gone = [
            c.put(f"/api/searches/{ids['search']}", json={"name": "Renamed", "criteria": {}}),
            c.delete(f"/api/searches/{ids['search']}"),
            c.get(f"/api/searches/{ids['search']}/matches"),
            c.post(f"/api/searches/{ids['search']}/scan"),
            c.delete(f"/api/simulations/{ids['simulation']}"),
            c.get(f"/api/str/scenarios/{ids['scenario']}"),
            c.put(f"/api/str/scenarios/{ids['scenario']}", json={"name": "Renamed", "deal": {}}),
            c.delete(f"/api/str/scenarios/{ids['scenario']}"),
            c.get(f"/api/str/forecasts/{ids['snapshot']}"),
            c.delete(f"/api/str/forecasts/{ids['snapshot']}"),
            c.put(f"/api/str/acquisitions/{ids['acquisition']}", json={"name": "Renamed", "criteria": {}}),
            c.delete(f"/api/str/acquisitions/{ids['acquisition']}"),
            c.post(f"/api/str/acquisitions/{ids['acquisition']}/scan"),
            c.get(f"/api/str/acquisitions/{ids['acquisition']}/runs"),
        ]
        for response in gone:
            self.assertEqual(response.status_code, 404, f"{response.request.method} {response.request.url}: {response.text}")

    def assert_owner_intact(self, ids: dict[str, str]) -> None:
        c = self.client
        self.assertEqual(len(c.get("/api/searches").json()), 1)
        self.assertEqual(len(c.get("/api/simulations").json()), 1)
        self.assertEqual(len(c.get("/api/str/scenarios").json()), 1)
        self.assertEqual(len(c.get("/api/str/acquisitions").json()), 1)
        self.assertEqual(c.get("/api/profile").json()["annual_gross_income"], 123456)
        self.assertEqual(c.get(f"/api/str/forecasts/{ids['snapshot']}").status_code, 200)
        self.assertEqual(len(c.get(f"/api/str/acquisitions/{ids['acquisition']}/runs").json()), 1)

    def test_a_platform_scope_owns_every_kind_of_record_with_no_legacy_account(self) -> None:
        ids = self.seed()
        self.assert_owner_intact(ids)
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 0)
            for table in ("financial_profiles", "saved_searches", "saved_simulations", "str_scenarios",
                          "str_forecast_snapshots", "str_eligibility", "str_acquisition_searches",
                          "str_acquisition_runs"):
                rows = db.execute(f"SELECT user_id, workspace_id, owner_sub FROM {table}").fetchall()
                self.assertTrue(rows, table)
                self.assertTrue(all(tuple(r) == (None, WS_A, SUB_1) for r in rows), table)

    def test_another_workspace_another_subject_and_guessed_ids_see_nothing(self) -> None:
        ids = self.seed()
        intruders = {
            "same subject, other workspace": platform(WS_B, SUB_1),
            "other subject, same workspace": platform(WS_A, SUB_2),
            "other subject, other workspace": platform(WS_B, SUB_2),
        }
        for name, intruder in intruders.items():
            with self.subTest(name):
                self.as_(intruder)
                self.assert_nothing_visible(ids)
        self.as_(platform(WS_A, SUB_1))
        self.assert_owner_intact(ids)
        # An id that never existed answers the same as another scope's id.
        self.as_(platform(WS_B, SUB_1))
        for response in (self.client.get(f"/api/str/scenarios/{NIL}"),
                         self.client.delete(f"/api/searches/{NIL}"),
                         self.client.get(f"/api/str/forecasts/{NIL}")):
            self.assertEqual(response.status_code, 404)

    def test_a_subject_keeps_separate_equal_records_in_each_workspace(self) -> None:
        self.seed()
        self.as_(platform(WS_B, SUB_1))
        ids_b = self.seed()  # the same unique forecast content and eligibility key, no collision
        self.assert_owner_intact(ids_b)
        self.as_(platform(WS_A, SUB_1))
        self.assertEqual(len(self.client.get("/api/searches").json()), 1)
        self.assertEqual(self.client.get("/api/profile").json()["annual_gross_income"], 123456)

    def test_profile_updates_replace_the_scopes_own_profile_only(self) -> None:
        self.client.put("/api/profile", json={"annual_gross_income": 1})
        self.client.put("/api/profile", json={"annual_gross_income": 2})
        self.as_(platform(WS_B, SUB_1))
        self.client.put("/api/profile", json={"annual_gross_income": 3})
        with connection() as db:
            rows = db.execute("SELECT workspace_id, profile_json FROM financial_profiles ORDER BY workspace_id").fetchall()
        self.assertEqual([r["workspace_id"] for r in rows], [WS_A, WS_B])

    def test_legacy_and_platform_records_are_disjoint_both_ways(self) -> None:
        platform_ids = self.seed()
        app.dependency_overrides.pop(current_principal)
        legacy = self.client.post("/api/auth/register", json={
            "name": "Legacy Person", "email": "legacy@example.invalid", "password": "syntheticpass1"})
        self.assertEqual(legacy.status_code, 201, legacy.text)
        self.assert_nothing_visible(platform_ids)
        legacy_search = self.client.post("/api/searches", json={"name": "Legacy", "criteria": {}}).json()["id"]
        legacy_scenario = self.client.post("/api/str/scenarios", json={"name": "Legacy scenario", "deal": {}}).json()["id"]
        app.dependency_overrides[current_principal] = lambda: self.who
        self.assertEqual([s["name"] for s in self.client.get("/api/searches").json()], ["Mine"])
        for response in (self.client.delete(f"/api/searches/{legacy_search}"),
                         self.client.get(f"/api/str/scenarios/{legacy_scenario}")):
            self.assertEqual(response.status_code, 404)

    def test_platform_scope_cannot_turn_on_email_alerts_or_scheduled_scans(self) -> None:
        search = {"name": "Alerts", "criteria": {"max_price": 300000}}
        for extra in (
            {"notifications_enabled": True, "notification_email": "someone@example.invalid"},
            {"notification_email": "someone@example.invalid"},
        ):
            r = self.client.post("/api/searches", json={**search, **extra})
            self.assertEqual(r.status_code, 409, r.text)
        mine = self.client.post("/api/searches", json=search).json()["id"]
        r = self.client.put(f"/api/searches/{mine}", json={
            **search, "notifications_enabled": True, "notification_email": "someone@example.invalid"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertFalse(self.client.get("/api/searches").json()[0]["notifications_enabled"])

        acquisition = {"name": "Scheduled", "criteria": {"max_price": 400000}, "enabled": True}
        self.assertEqual(self.client.post("/api/str/acquisitions", json=acquisition).status_code, 409)
        mine = self.client.post("/api/str/acquisitions", json={**acquisition, "enabled": False}).json()["id"]
        self.assertEqual(self.client.put(f"/api/str/acquisitions/{mine}", json=acquisition).status_code, 409)
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM saved_searches WHERE notifications_enabled=1").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_searches WHERE enabled=1").fetchone()[0], 0)

    def test_a_manual_scan_of_a_platform_search_works_without_sending_anything(self) -> None:
        search = self.client.post("/api/searches", json={"name": "Manual", "criteria": {"max_price": 600000}}).json()["id"]
        with patch("app.services.property_providers.RentCastPropertyProvider.sale_listings",
                   new=AsyncMock(return_value=[self.sale_listing()])), \
                patch("app.routes.product.send_match_email") as email:
            r = self.client.post(f"/api/searches/{search}/scan")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["notification_status"], "Notifications are off")
        email.assert_not_called()

    def test_background_jobs_never_select_platform_records(self) -> None:
        from app.jobs import scan_saved_searches, scan_str_acquisitions
        self.seed()
        # Even a row forced on in the database is skipped: the jobs join to legacy accounts.
        with connection() as db:
            db.execute("UPDATE saved_searches SET notifications_enabled = 1")
            db.execute("UPDATE str_acquisition_searches SET enabled = 1")
        scanned = []
        with patch.object(scan_saved_searches, "scan_search", new=AsyncMock(side_effect=lambda *a: scanned.append(a))):
            self.assertEqual(asyncio.run(scan_saved_searches.run()), 0)
        with patch.object(scan_str_acquisitions, "scan_acquisitions", new=AsyncMock(side_effect=lambda *a: scanned.append(a))):
            self.assertEqual(asyncio.run(scan_str_acquisitions.run()), 0)
        self.assertEqual(scanned, [])

    def test_a_scan_whose_search_changes_owner_during_provider_io_stores_nothing(self) -> None:
        search = self.client.post("/api/searches", json={"name": "Moving", "criteria": {"max_price": 600000}}).json()["id"]

        async def slow_provider(*_args, **_kwargs):
            # The search is transferred to another subject while the provider call is in flight.
            with connection() as db:
                db.execute("UPDATE saved_searches SET owner_sub = ? WHERE id = ?", (SUB_2, search))
            return [self.sale_listing()]

        with patch("app.services.property_providers.RentCastPropertyProvider.sale_listings", new=slow_provider):
            r = self.client.post(f"/api/searches/{search}/scan")
        self.assertEqual(r.status_code, 404, r.text)
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM listing_matches").fetchone()[0], 0)
        # The new owner sees no matches that the old scope's scan could have left behind.
        self.as_(platform(WS_A, SUB_2))
        self.assertEqual(self.client.get(f"/api/searches/{search}/matches").json(), [])

    def test_an_alert_is_never_sent_for_a_platform_scope_even_if_the_row_says_so(self) -> None:
        search = self.client.post("/api/searches", json={"name": "Forced", "criteria": {"max_price": 600000}}).json()["id"]
        with connection() as db:
            db.execute("UPDATE saved_searches SET notifications_enabled=1, notification_email='x@example.invalid' WHERE id=?", (search,))
        with patch("app.services.property_providers.RentCastPropertyProvider.sale_listings",
                   new=AsyncMock(return_value=[self.sale_listing()])), \
                patch("app.routes.product.send_match_email") as email:
            r = self.client.post(f"/api/searches/{search}/scan")
        self.assertEqual(r.status_code, 200, r.text)
        email.assert_not_called()
        self.assertEqual(r.json()["notification_status"], "Notifications are off")

    def test_enabling_alerts_without_an_address_is_a_validation_error_in_every_scope(self) -> None:
        # Request validation runs before the scope guard, so the legacy answer is unchanged: 422.
        r = self.client.post("/api/searches", json={"name": "Alerts", "criteria": {}, "notifications_enabled": True})
        self.assertEqual(r.status_code, 422, r.text)

    def test_me_for_a_platform_person_has_no_hearthline_profile(self) -> None:
        user = self.client.get("/api/auth/me").json()["user"]
        self.assertEqual(user["id"], SUB_1)
        self.assertEqual(user["email"], "")

    def test_the_database_refuses_a_foreign_owner_on_a_run(self) -> None:
        ids = self.seed()
        with connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO str_acquisition_runs(id,search_id,workspace_id,owner_sub,result_json,retention_until,created_at)"
                    " VALUES('r1',?,?,?,'{}','2099-01-01','now')", (ids["acquisition"], WS_B, SUB_1))

    def test_restore_drill_a_backup_restored_into_an_empty_database_keeps_scopes(self) -> None:
        from app.jobs.database_maintenance import create_backup, restore_backup
        ids = self.seed()
        self.as_(platform(WS_B, SUB_2))
        self.client.post("/api/searches", json={"name": "Other tenant", "criteria": {}})
        backup = create_backup(Path(self.temp.name) / "backups")

        def snapshot() -> dict[str, list[tuple]]:
            with connection() as db:
                return {t: [tuple(r) for r in db.execute(
                    f"SELECT id, workspace_id, owner_sub FROM {t} ORDER BY id").fetchall()]
                        for t in ("saved_searches", "saved_simulations", "str_scenarios", "str_acquisition_searches")}
        before = snapshot()

        # Replace the live database with an empty one, then restore the backup into it.
        Path(settings.database_path).unlink()
        for suffix in ("-wal", "-shm"):
            Path(settings.database_path + suffix).unlink(missing_ok=True)
        restore_backup(backup, confirm_replace=True)

        self.assertEqual(snapshot(), before)
        # Licensed evidence is excluded from backups by design; everything else returns and stays scoped.
        self.as_(platform(WS_A, SUB_1))
        self.assertEqual(len(self.client.get("/api/searches").json()), 1)
        self.assertEqual(self.client.get("/api/profile").json()["annual_gross_income"], 123456)
        self.assertEqual(self.client.get(f"/api/str/forecasts/{ids['snapshot']}").status_code, 404)
        self.as_(platform(WS_B, SUB_2))
        self.assertEqual([s["name"] for s in self.client.get("/api/searches").json()], ["Other tenant"])
        self.as_(platform(WS_B, SUB_1))
        self.assertEqual(self.client.get("/api/searches").json(), [])
        with connection() as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
