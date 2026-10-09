from __future__ import annotations

import calendar
import copy
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import MIGRATIONS, connection, init_database, json_loads
from app.main import app
from app.routes.product_models import PropertyListing
from app.services.property_providers import PropertyProviderError


def synthetic_export(address: str = "1 Synthetic Lane, Example, PA") -> dict:
    """Entirely synthetic fixture; never licensed vendor data or a market forecast."""
    today = date.today()
    months = []
    for i in range(12):
        ordinal = today.year * 12 + today.month - 1 + i
        month = date(ordinal // 12, ordinal % 12 + 1, 1)
        days = calendar.monthrange(month.year, month.month)[1]
        months.append({"month": month.isoformat(), "gross_revenue": 1000 * .5 * days,
                       "adr": 1000, "occupancy": .5, "available_nights": days})
    return {
        "forecast_kind": "property_specific", "provider": "Synthetic test provider",
        "source_url": "https://example.invalid/forecast", "attribution": "Synthetic tests only, not a real forecast",
        "license_reference": "synthetic-test-contract", "licensed_use_attested": True,
        "permitted_use": "internal_underwriting", "retention_permitted": True,
        "retention_until": (today + timedelta(days=365)).isoformat(), "data_version": "synthetic-v1",
        "property": {"address": address, "property_type": "Single Family", "bedrooms": 3,
                     "bathrooms": 2, "provider_property_id": "subject-1"},
        "as_of": today.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "USD", "revenue_basis": "accommodation_only_before_owner_use",
        "methodology": "Synthetic accommodation revenue excluding cleaning fees and taxes.",
        "months": months,
        "comparables": [{"provider_property_id": f"synthetic-comp-{i}", "source_url": f"https://example.invalid/comp/{i}",
                         "property_type": "Single Family", "bedrooms": 3, "bathrooms": 2,
                         "distance_miles": i+1, "period_start": (today-timedelta(days=364)).isoformat(),
                         "period_end": today.isoformat(), "gross_revenue": 100000,
                         "observed_booked_nights": 180, "owner_blocked_nights": 0} for i in range(8)],
    }


class StrWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original = {k: getattr(settings, k) for k in ("database_path", "rate_limit_enabled", "registration_enabled", "property_provider", "rentcast_api_key")}
        settings.database_path = str(Path(self.temp.name)/"app.db")
        settings.rate_limit_enabled = False
        settings.registration_enabled = True
        settings.property_provider = "rentcast"
        settings.rentcast_api_key = "synthetic-key"
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        self.register("first@example.invalid")

    def tearDown(self) -> None:
        self.context.__exit__(None, None, None)
        for key, value in self.original.items():
            setattr(settings, key, value)
        self.temp.cleanup()

    def register(self, email: str) -> None:
        r = self.client.post("/api/auth/register", json={"name": "Synthetic Tester", "email": email, "password": "syntheticpass1"})
        self.assertEqual(r.status_code, 201, r.text)

    def import_export(self, payload: dict | None = None) -> dict:
        r = self.client.post("/api/str/forecasts/import", json=payload or synthetic_export())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def create_search(self, **updates: object) -> str:
        r = self.client.post("/api/str/acquisitions", json={"name": "Synthetic acquisition", "criteria": {"max_price": 400000}, **updates})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["id"]

    def sale_listing(self, address: str = "1 Synthetic Lane, Example, PA", **changes: object) -> PropertyListing:
        return PropertyListing(id="sale-1", provider="rentcast", address=address, city="Example", state="PA",
                               price=300000, bedrooms=3, bathrooms=2, property_type="Single Family",
                               days_on_market=10, hoa_monthly=100, **changes)

    def evidence(self, status: str = "verified", **updates: object) -> dict:
        return {"status": status, "document_reference": "https://example.invalid/written-permission",
                "authority": "Synthetic authority", "checked_on": date.today().isoformat(),
                "valid_until": (date.today()+timedelta(days=30)).isoformat(), **updates}

    def put_gates(self, payload: dict, status: str = "verified") -> None:
        r = self.client.put("/api/str/eligibility", json={"property": payload["property"], "municipality": self.evidence(status), "hoa": self.evidence()})
        self.assertEqual(r.status_code, 200, r.text)

    def scan(self, search_id: str, listings: list | None = None) -> dict:
        with patch("app.services.str_acquisitions.RentCastPropertyProvider.sale_listings", new=AsyncMock(return_value=listings or [self.sale_listing()])) as mock:
            r = self.client.post(f"/api/str/acquisitions/{search_id}/scan")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(mock.call_args.args[0].purpose, "primary")
        return r.json()

    def test_scenario_crud_and_every_operation_is_user_scoped(self) -> None:
        payload = {"name": "First scenario", "deal": {"forecast_as_of": date.today().isoformat()}}
        r = self.client.post("/api/str/scenarios", json=payload)
        self.assertEqual(r.status_code, 201, r.text)
        sid = r.json()["id"]
        self.assertEqual(self.client.get(f"/api/str/scenarios/{sid}").json()["name"], "First scenario")
        payload["name"] = "Updated scenario"
        self.assertEqual(self.client.put(f"/api/str/scenarios/{sid}", json=payload).json()["name"], "Updated scenario")
        self.client.post("/api/auth/logout")
        self.register("second@example.invalid")
        self.assertEqual(self.client.get("/api/str/scenarios").json(), [])
        self.assertEqual(self.client.get(f"/api/str/scenarios/{sid}").status_code, 404)
        self.assertEqual(self.client.put(f"/api/str/scenarios/{sid}", json=payload).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/str/scenarios/{sid}").status_code, 404)
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/login", json={"email": "first@example.invalid", "password": "syntheticpass1"})
        self.assertEqual(self.client.delete(f"/api/str/scenarios/{sid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/str/scenarios/{sid}").status_code, 404)

    def test_str_requires_authentication(self) -> None:
        self.client.post("/api/auth/logout")
        for method, path, body in [("post", "/api/str/underwrite", {}), ("get", "/api/str/scenarios", None),
                                   ("post", "/api/str/forecasts/import", synthetic_export()),
                                   ("get", "/api/str/acquisitions", None),
                                   ("put", "/api/str/eligibility", {"property": synthetic_export()["property"]})]:
            r = getattr(self.client, method)(path, **({"json": body} if body is not None else {}))
            self.assertEqual(r.status_code, 401, path)

    def test_snapshots_are_immutable_idempotent_and_private(self) -> None:
        payload = synthetic_export()
        first = self.import_export(payload)
        self.assertEqual(first["status"], "available")
        self.assertEqual(first["qualified_comparable_count"], 8)
        self.assertEqual(self.import_export(payload)["snapshot_id"], first["snapshot_id"])
        changed = copy.deepcopy(payload)
        changed["data_version"] = "synthetic-v2"
        second = self.import_export(changed)
        self.assertNotEqual(second["snapshot_id"], first["snapshot_id"])
        self.assertEqual(self.client.get(f"/api/str/forecasts/{first['snapshot_id']}").json()["forecast"]["data_version"], "synthetic-v1")
        self.assertEqual(self.client.put(f"/api/str/forecasts/{first['snapshot_id']}", json=changed).status_code, 405)
        self.client.post("/api/auth/logout")
        self.register("second@example.invalid")
        self.assertEqual(self.client.get(f"/api/str/forecasts/{first['snapshot_id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/str/forecasts/{first['snapshot_id']}").status_code, 404)
        self.assertEqual(self.client.post("/api/str/forecasts/lookup", json=payload["property"]).json()["status"], "unavailable")
        self.assertEqual(self.client.post("/api/str/underwrite", json={"address": payload["property"]["address"], "forecast_snapshot_id": first["snapshot_id"]}).status_code, 404)

    def test_market_data_invalid_months_revenue_dates_license_and_duplicates_are_rejected(self) -> None:
        for mutation in (lambda p: p.update(forecast_kind="market_average"),
                         lambda p: p.update(licensed_use_attested=False),
                         lambda p: p.update(retention_permitted=False),
                         lambda p: p.update(currency="EUR"),
                         lambda p: p.update(revenue_basis="includes_owner_blocks"),
                         lambda p: p.update(as_of=(date.today()+timedelta(days=1)).isoformat()),
                         lambda p: p["months"][1].update(month=p["months"][0]["month"]),
                         lambda p: p["months"][0].update(gross_revenue=-1),
                         lambda p: p["months"][0].update(gross_revenue=1),
                         lambda p: p["months"][0].update(occupancy=1.5),
                         lambda p: p["comparables"][1].update(provider_property_id=p["comparables"][0]["provider_property_id"]),
                         lambda p: p["comparables"][0].update(observed_booked_nights=366, owner_blocked_nights=2)):
            payload = synthetic_export()
            mutation(payload)
            r = self.client.post("/api/str/forecasts/import", json=payload)
            self.assertEqual(r.status_code, 422, r.text)

    def test_stale_insufficient_comp_and_property_mismatch_states(self) -> None:
        payload = synthetic_export()
        payload["comparables"][0]["owner_blocked_nights"] = 1
        imported = self.import_export(payload)
        self.assertEqual(imported["status"], "insufficient_evidence")
        self.assertEqual(self.client.post("/api/str/underwrite", json={"address": payload["property"]["address"],
                         "forecast_snapshot_id": imported["snapshot_id"]}).status_code, 409)
        payload = synthetic_export()
        payload["as_of"] = (date.today()-timedelta(days=91)).isoformat()
        for comp in payload["comparables"]:
            comp["period_end"] = payload["as_of"]
            comp["period_start"] = (date.today()-timedelta(days=455)).isoformat()
        self.assertEqual(self.import_export(payload)["status"], "stale")
        payload = synthetic_export()
        self.import_export(payload)
        query = {**payload["property"], "bedrooms": 6}
        self.assertEqual(self.client.post("/api/str/forecasts/lookup", json=query).json()["status"], "property_mismatch")
        query["address"] = "2 Nearby Lane, Example, PA"
        self.assertEqual(self.client.post("/api/str/forecasts/lookup", json=query).json()["status"], "unavailable")

    def test_self_asserted_provenance_cannot_clear_underwriting_gate(self) -> None:
        payload = synthetic_export()
        r = self.client.post("/api/str/underwrite", json={"revenue_source": "licensed_property_forecast", "forecast_as_of": date.today().isoformat(),
                    "comparable_count": 12, "monthly_gross_revenue": [15000]*12,
                    "regulatory_gate": "verified", "hoa_gate": "verified", "regulatory_evidence": self.evidence(), "hoa_evidence": self.evidence()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["screening_status"], "research_only")
        forecast = self.import_export(payload)
        request = {"address": payload["property"]["address"], "forecast_snapshot_id": forecast["snapshot_id"],
                   "annual_gross_revenue": 99999999, "monthly_gross_revenue": [999999]*12,
                   "regulatory_evidence": self.evidence(), "hoa_evidence": self.evidence()}
        r = self.client.post("/api/str/underwrite", json=request)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertAlmostEqual(r.json()["annual_gross_before_owner_use"], sum(m["gross_revenue"] for m in payload["months"]))
        self.assertEqual(r.json()["screening_status"], "meets_financial_screen")
        request["address"] = "2 Different Lane, Example, PA"
        self.assertEqual(self.client.post("/api/str/underwrite", json=request).status_code, 422)

    def test_scenarios_keep_snapshot_reference_not_duplicate_licensed_data(self) -> None:
        payload = synthetic_export()
        forecast = self.import_export(payload)
        r = self.client.post("/api/str/scenarios", json={"name": "Referenced evidence", "deal": {
            "address": payload["property"]["address"], "forecast_snapshot_id": forecast["snapshot_id"],
            "monthly_gross_revenue": [10000]*12, "annual_gross_revenue": 120000}})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["deal"]["forecast_snapshot_id"], forecast["snapshot_id"])
        self.assertIsNone(r.json()["deal"]["monthly_gross_revenue"])
        self.assertEqual(r.json()["deal"]["annual_gross_revenue"], 0)

    def test_missing_forecast_and_unknown_legal_gates_never_rank(self) -> None:
        sid = self.create_search()
        run = self.scan(sid)
        c = run["candidates"][0]
        self.assertEqual(c["forecast_status"], "unavailable")
        self.assertIsNone(c["rank"])
        self.assertIsNone(c["underwriting"])
        self.import_export()
        c = self.scan(sid)["candidates"][0]
        self.assertEqual(c["status"], "research_only")
        self.assertIsNone(c["rank"])

    def test_written_legal_gates_and_stress_screen_rank_only_validated_candidates(self) -> None:
        sid = self.create_search()
        payload = synthetic_export()
        self.import_export(payload)
        self.put_gates(payload)
        c = self.scan(sid)["candidates"][0]
        self.assertEqual(c["rank"], 1)
        self.assertEqual(c["status"], "meets_financial_screen")
        self.assertAlmostEqual(c["underwriting"]["annual_fixed_operating_costs"], 21900+1200)
        self.assertIn("Synthetic", c["provider_attribution"])
        self.put_gates(payload, "blocked")
        c = self.scan(sid)["candidates"][0]
        self.assertEqual(c["status"], "blocked")
        self.assertIsNone(c["rank"])
        self.assertGreaterEqual(len(self.client.get(f"/api/str/acquisitions/{sid}/runs").json()), 2)

    def test_expired_permission_is_unknown_but_prohibition_remains_blocked(self) -> None:
        payload = synthetic_export()
        self.import_export(payload)
        sid = self.create_search()
        old = self.evidence(checked_on=(date.today()-timedelta(days=2)).isoformat(), valid_until=(date.today()-timedelta(days=1)).isoformat())
        self.client.put("/api/str/eligibility", json={"property": payload["property"], "municipality": old, "hoa": self.evidence()})
        self.assertIsNone(self.scan(sid)["candidates"][0]["rank"])
        old["status"] = "blocked"
        self.client.put("/api/str/eligibility", json={"property": payload["property"], "municipality": old, "hoa": self.evidence()})
        self.assertEqual(self.scan(sid)["candidates"][0]["status"], "blocked")
        self.assertEqual(self.client.put("/api/str/eligibility", json={"property": payload["property"], "municipality": {"status": "verified"}}).status_code, 422)

    def test_rentcast_access_failure_is_unavailable_without_demo_fallback(self) -> None:
        sid = self.create_search()
        settings.rentcast_api_key = None
        r = self.client.post(f"/api/str/acquisitions/{sid}/scan")
        self.assertEqual(r.json()["status"], "unavailable")
        self.assertEqual(r.json()["candidates"], [])
        settings.rentcast_api_key = "synthetic-key"
        with patch("app.services.str_acquisitions.RentCastPropertyProvider.sale_listings", new=AsyncMock(side_effect=PropertyProviderError("failure"))):
            r = self.client.post(f"/api/str/acquisitions/{sid}/scan")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "unavailable")
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_leases").fetchone()[0], 0)

    def test_search_history_forecasts_and_eligibility_are_user_isolated(self) -> None:
        sid = self.create_search()
        payload = synthetic_export()
        self.import_export(payload)
        self.put_gates(payload)
        self.scan(sid)
        self.client.post("/api/auth/logout")
        self.register("second@example.invalid")
        self.assertEqual(self.client.get("/api/str/acquisitions").json(), [])
        for method, suffix, body in [("post", "/scan", {}), ("get", "/runs", None), ("delete", "", None),
                                     ("put", "", {"name": "Foreign change"})]:
            r = getattr(self.client, method)(f"/api/str/acquisitions/{sid}{suffix}", **({"json": body} if body is not None else {}))
            self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(self.client.post("/api/str/eligibility/lookup", json=payload["property"]).json()["municipality"]["status"], "unknown")

    def test_scan_lease_prevents_overlapping_runs(self) -> None:
        sid = self.create_search()
        with connection() as db:
            db.execute("INSERT INTO str_acquisition_leases VALUES (?,?,?)", (sid, "other", (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()))
        self.assertEqual(self.client.post(f"/api/str/acquisitions/{sid}/scan").status_code, 409)

    def test_acquisition_rate_limit_bounds_manual_provider_calls(self) -> None:
        sid = self.create_search()
        settings.rentcast_api_key = None
        settings.rate_limit_enabled = True
        app.state.rate_limiter.reset()
        for _ in range(6):
            self.assertEqual(self.client.post(f"/api/str/acquisitions/{sid}/scan").status_code, 200)
        self.assertEqual(self.client.post(f"/api/str/acquisitions/{sid}/scan").status_code, 429)
        app.state.rate_limiter.reset()

    def test_expired_retention_purges_snapshot_and_derived_runs(self) -> None:
        payload = synthetic_export()
        forecast = self.import_export(payload)
        sid = self.create_search()
        self.put_gates(payload)
        self.scan(sid)
        with connection() as db:
            yesterday = (date.today()-timedelta(days=1)).isoformat()
            db.execute("UPDATE str_forecast_snapshots SET retention_until=?", (yesterday,))
            db.execute("UPDATE str_acquisition_runs SET retention_until=?", (yesterday,))
        self.assertEqual(self.client.get(f"/api/str/forecasts/{forecast['snapshot_id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/str/acquisitions/{sid}/runs").json(), [])
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM str_forecast_snapshots").fetchone()[0], 0)

    def test_delete_snapshot_removes_derived_history(self) -> None:
        payload = synthetic_export()
        forecast = self.import_export(payload)
        sid = self.create_search()
        self.put_gates(payload)
        self.scan(sid)
        self.assertEqual(self.client.delete(f"/api/str/forecasts/{forecast['snapshot_id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/str/acquisitions/{sid}/runs").json(), [])

    def test_backups_exclude_licensed_datasets_but_retain_scenario_references(self) -> None:
        import sqlite3
        from app.jobs.database_maintenance import create_backup
        payload = synthetic_export()
        forecast = self.import_export(payload)
        sid = self.create_search()
        self.put_gates(payload)
        self.scan(sid)
        self.client.post("/api/str/scenarios", json={"name": "Preserved scenario", "deal": {
            "address": payload["property"]["address"], "forecast_snapshot_id": forecast["snapshot_id"]}})
        backup = create_backup(Path(self.temp.name)/"backups")
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM str_forecast_snapshots").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_runs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM str_scenarios").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM str_acquisition_searches").fetchone()[0], 1)
        self.assertNotIn(b"Synthetic tests only, not a real forecast", backup.read_bytes())

    def test_sale_filters_and_additional_financial_thresholds_cannot_be_bypassed(self) -> None:
        sid = self.create_search(criteria={"max_price": 400000, "min_dscr": 10})
        payload = synthetic_export()
        self.import_export(payload)
        self.put_gates(payload)
        c = self.scan(sid)["candidates"][0]
        self.assertEqual(c["status"], "below_financial_screen")
        self.assertIsNone(c["rank"])
        listing = self.sale_listing().model_copy(update={"price": 500000})
        self.assertEqual(self.scan(sid, [listing])["candidates"], [])

    def test_stale_and_mismatched_forecasts_never_rank_acquisitions(self) -> None:
        sid = self.create_search()
        payload = synthetic_export()
        payload["comparables"] = payload["comparables"][:7]
        self.import_export(payload)
        self.put_gates(payload)
        c = self.scan(sid)["candidates"][0]
        self.assertEqual(c["forecast_status"], "insufficient_evidence")
        self.assertIsNone(c["rank"])
        self.import_export()
        listing = self.sale_listing().model_copy(update={"bedrooms": 6})
        c = self.scan(sid, [listing])["candidates"][0]
        self.assertEqual(c["forecast_status"], "property_mismatch")
        self.assertIsNone(c["rank"])

    def test_job_processes_only_enabled_searches_and_reports_unavailable_as_failure(self) -> None:
        import asyncio
        from app.jobs.scan_str_acquisitions import run
        self.create_search(enabled=False)
        enabled = self.create_search(enabled=True)
        settings.rentcast_api_key = None
        self.assertEqual(asyncio.run(run()), 1)
        with connection() as db:
            rows = db.execute("SELECT search_id FROM str_acquisition_runs").fetchall()
        self.assertEqual([r["search_id"] for r in rows], [enabled])


class StrUpgradeTests(unittest.TestCase):
    def test_upgrade_from_populated_v2_preserves_existing_features_and_is_idempotent(self) -> None:
        original = settings.database_path
        with tempfile.TemporaryDirectory() as temp:
            settings.database_path = str(Path(temp)/"upgrade.db")
            try:
                with connection() as db:
                    db.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                    for version, sql in MIGRATIONS[:2]:
                        db.executescript(sql)
                        db.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))
                    db.execute("INSERT INTO users VALUES('u','Existing user','old@example.invalid','hash','now')")
                    db.execute("INSERT INTO saved_simulations VALUES('sim','u','SBLOC','{}','now','now')")
                    db.execute("INSERT INTO saved_searches(id,user_id,name,criteria_json,created_at,updated_at) VALUES('search','u','LTR','{}','now','now')")
                init_database()
                init_database()
                with connection() as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 4)
                    self.assertEqual(db.execute("SELECT name FROM saved_simulations").fetchone()[0], "SBLOC")
                    self.assertEqual(db.execute("SELECT name FROM saved_searches").fetchone()[0], "LTR")
                    db.execute("INSERT INTO str_scenarios VALUES('s','u','STR','{}','now','now')")
                    db.execute("DELETE FROM users WHERE id='u'")
                    self.assertEqual(db.execute("SELECT count(*) FROM str_scenarios").fetchone()[0], 0)
            finally:
                settings.database_path = original
