from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import connection
from app.main import app


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_settings = {
            "database_path": settings.database_path,
            "property_provider": settings.property_provider,
            "rentcast_api_key": settings.rentcast_api_key,
            "fred_api_key": settings.fred_api_key,
            "rate_limit_enabled": settings.rate_limit_enabled,
            "registration_enabled": settings.registration_enabled,
        }
        settings.database_path = str(Path(self.temporary_directory.name) / "test.db")
        settings.property_provider = "demo"
        settings.rentcast_api_key = None
        settings.fred_api_key = None
        settings.rate_limit_enabled = False
        settings.registration_enabled = True
        app.state.rate_limiter.reset()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        for key, value in self.original_settings.items():
            setattr(settings, key, value)
        app.state.rate_limiter.reset()
        self.temporary_directory.cleanup()

    def register(self, email: str = "planner@example.com") -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test Planner",
                "email": email,
                "password": "planningpass1",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def create_search(self) -> str:
        response = self.client.post(
            "/api/searches",
            json={
                "name": "Primary search",
                "criteria": {
                    "purpose": "primary",
                    "location": "Cleveland, OH",
                    "max_price": 500_000,
                    "min_bedrooms": 3,
                    "min_bathrooms": 2,
                },
                "notifications_enabled": False,
                "notification_email": None,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_health_readiness_and_protected_route(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["ok"])
        self.assertEqual(self.client.get("/api/profile").status_code, 401)

        ready = self.client.get("/api/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["database"]["schema_version"], 2)

    def test_authenticated_demo_workflow_and_session_cookie(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test Planner",
                "email": "planner@example.com",
                "password": "planningpass1",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)

        self.assertEqual(self.client.get("/api/profile").status_code, 200)
        self.assertEqual(self.client.get("/api/affordability").status_code, 200)
        search_id = self.create_search()
        scan = self.client.post(f"/api/searches/{search_id}/scan")
        self.assertEqual(scan.status_code, 200, scan.text)
        self.assertEqual(scan.json()["provider_mode"], "demo")
        self.assertGreater(scan.json()["total_scanned"], 0)
        self.assertGreater(len(scan.json()["matches"]), 0)
        self.assertEqual(
            self.client.get(f"/api/searches/{search_id}/matches").status_code,
            200,
        )

    def test_risk_is_bounded_and_zero_loan_is_valid_json(self) -> None:
        self.register()
        request = {
            "portfolio_value": 1_000_000,
            "loan_amount": 0,
            "maintenance_ltv_max": 0.7,
            "mu_annual": 0.07,
            "sigma_annual": 0.22,
            "horizons_months": [12, 36, 60],
            "runs": 10_000,
        }
        response = self.client.post("/api/risk", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["danger_portfolio_value"], 0)
        self.assertTrue(
            all(result["breach_probability"] == 0 for result in payload["results"])
        )
        self.assertTrue(
            all(result["sample_size"] <= 512 for result in payload["results"])
        )

        too_many_horizons = {**request, "horizons_months": [1, 2, 3, 4]}
        self.assertEqual(
            self.client.post("/api/risk", json=too_many_horizons).status_code,
            422,
        )
        excessive_runs = {**request, "runs": 25_001}
        self.assertEqual(self.client.post("/api/risk", json=excessive_runs).status_code, 422)
        duplicate_horizons = {**request, "horizons_months": [12, 12]}
        self.assertEqual(
            self.client.post("/api/risk", json=duplicate_horizons).status_code,
            422,
        )

    def test_existing_scan_lease_returns_conflict(self) -> None:
        self.register()
        search_id = self.create_search()
        with connection() as db:
            db.execute(
                """
                INSERT INTO scan_leases (search_id, lease_token, acquired_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    search_id,
                    "existing-lease",
                    "2026-01-01T00:00:00+00:00",
                    "2999-01-01T00:00:00+00:00",
                ),
            )
        response = self.client.post(f"/api/searches/{search_id}/scan")
        self.assertEqual(response.status_code, 409)

    def test_saved_search_isolated_between_users(self) -> None:
        self.register("first@example.com")
        search_id = self.create_search()
        self.client.post("/api/auth/logout")
        self.register("second@example.com")
        self.assertEqual(self.client.get(f"/api/searches/{search_id}/matches").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/searches/{search_id}").status_code, 404)

    def test_registration_can_be_disabled(self) -> None:
        settings.registration_enabled = False
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Test Planner",
                "email": "planner@example.com",
                "password": "planningpass1",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_login_rate_limit(self) -> None:
        settings.rate_limit_enabled = True
        app.state.rate_limiter.reset()
        responses = [
            self.client.post(
                "/api/auth/login",
                json={"email": "missing@example.com", "password": "wrong"},
            )
            for _ in range(11)
        ]
        self.assertTrue(all(response.status_code == 401 for response in responses[:10]))
        self.assertEqual(responses[-1].status_code, 429)
        self.assertIn("retry-after", responses[-1].headers)

    def test_fred_failure_degrades_to_fallback(self) -> None:
        self.register()
        settings.fred_api_key = "configured-for-test"
        with (
            patch(
                "app.routes.api.fetch_latest_observation",
                new=AsyncMock(side_effect=RuntimeError("upstream unavailable")),
            ),
            self.assertLogs("app.routes.api", level="ERROR"),
        ):
            response = self.client.get("/api/macro")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
