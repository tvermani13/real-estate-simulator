"""The financial engine must stay byte-for-byte identical (platform ADR 0012, decision 8).

Fixed manual inputs go through the normal HTTP entry points (the Monte Carlo
seed is the engine's own fixed default). The expected response bodies live in
``golden/engine_outputs.json`` and were captured from the engine before any
platform change. Regenerate them only for a deliberate engine change:

    GOLDEN_UPDATE=1 PYTHONPATH=backend .venv/bin/python -m unittest tests.test_engine_golden
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import init_database
from app.main import app

GOLDEN = Path(__file__).parent / "golden" / "engine_outputs.json"

PORTFOLIO = {
    "total_portfolio_value": 2_400_000,
    "weighted_average_cost_basis_pct": 0.42,
    "historical_volatility_annual": 0.18,
    "expected_equity_return_annual": 0.07,
    "broker_maintenance_requirement_ltv_max": 0.7,
}
DEAL = {
    "property_purchase_price": 640_000,
    "down_payment_required": 160_000,
    "expected_monthly_rent": 4_100,
    "operating_expenses": 1_150,
    "expected_annual_appreciation": 0.03,
}
PROFILE = {
    "annual_gross_income": 310_000,
    "monthly_take_home_income": 17_250,
    "monthly_debt_payments": 1_900,
    "monthly_living_expenses": 6_400,
    "liquid_cash": 220_000,
    "taxable_investments": 900_000,
    "retirement_assets": 540_000,
    "other_assets": 35_000,
    "total_liabilities": 410_000,
    "credit_score": 781,
    "risk_tolerance": "balanced",
}
STR_DEAL = {
    "name": "Golden cabin",
    "address": "12 Ridge Road, Gatlinburg, TN",
    "property_price": 525_000,
    "down_payment_pct": 0.25,
    "mortgage_apr": 0.0725,
    "annual_gross_revenue": 88_000,
    "strategy": "hybrid",
    "owner_nights": 30,
}

CASES: dict[str, tuple[str, str, dict | None]] = {
    "scenario_a": ("POST", "/api/scenario-a", {"portfolio": PORTFOLIO, "deal": DEAL, "capital_gains_tax_rate": 0.238}),
    "scenario_b": (
        "POST",
        "/api/scenario-b",
        {"portfolio": PORTFOLIO, "deal": DEAL, "loan_amount": 480_000, "sofr_rate": 0.043, "broker_spread": 0.02},
    ),
    "risk": (
        "POST",
        "/api/risk",
        {
            "portfolio_value": 2_400_000,
            "loan_amount": 480_000,
            "maintenance_ltv_max": 0.7,
            "mu_annual": 0.07,
            "sigma_annual": 0.18,
            "horizons_months": [12, 36, 60],
            "runs": 2_000,
        },
    ),
    "str_underwrite": ("POST", "/api/str/underwrite", STR_DEAL),
    "affordability": ("GET", "/api/affordability", None),
}


class EngineGoldenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original = {
            "database_path": settings.database_path,
            "rate_limit_enabled": settings.rate_limit_enabled,
            "registration_enabled": settings.registration_enabled,
        }
        settings.database_path = str(Path(self.temporary_directory.name) / "test.db")
        settings.rate_limit_enabled = False
        settings.registration_enabled = True
        app.state.rate_limiter.reset()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        for key, value in self.original.items():
            setattr(settings, key, value)
        app.state.rate_limiter.reset()
        self.temporary_directory.cleanup()

    def run_cases(self) -> dict[str, str]:
        registered = self.client.post(
            "/api/auth/register",
            json={"name": "Golden Planner", "email": "golden@example.com", "password": "planningpass1"},
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        saved = self.client.put("/api/profile", json=PROFILE)
        self.assertEqual(saved.status_code, 200, saved.text)
        outputs: dict[str, str] = {}
        for name, (method, path, body) in CASES.items():
            response = self.client.request(method, path, json=body) if body is not None else self.client.request(method, path)
            self.assertEqual(response.status_code, 200, f"{name}: {response.text}")
            outputs[name] = response.text
        return outputs

    def assert_same(self, actual: object, expected: object, where: str) -> None:
        """Structure, strings and integers must match exactly. Floats may differ in the last
        digits between platforms' math libraries, so they match to one part in 1e9."""
        if isinstance(expected, float) and isinstance(actual, float):
            self.assertTrue(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), f"{where}: {actual} != {expected}")
        elif isinstance(expected, dict) and isinstance(actual, dict):
            self.assertEqual(sorted(actual), sorted(expected), where)
            for key in expected:
                self.assert_same(actual[key], expected[key], f"{where}.{key}")
        elif isinstance(expected, list) and isinstance(actual, list):
            self.assertEqual(len(actual), len(expected), where)
            for index, (a, e) in enumerate(zip(actual, expected)):
                self.assert_same(a, e, f"{where}[{index}]")
        else:
            self.assertEqual(actual, expected, where)

    def test_engine_outputs_match_the_recorded_ones(self) -> None:
        outputs = self.run_cases()
        if os.environ.get("GOLDEN_UPDATE") == "1":
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(outputs, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(sorted(expected), sorted(outputs))
        for name in sorted(outputs):
            self.assert_same(json.loads(outputs[name]), json.loads(expected[name]), name)

    def test_the_same_inputs_give_the_same_bytes_twice(self) -> None:
        first = self.run_cases()
        self.client.cookies.clear()
        self.client.post("/api/auth/logout")
        # A fresh database in the same process must reproduce them exactly.
        second_dir = tempfile.TemporaryDirectory()
        try:
            settings.database_path = str(Path(second_dir.name) / "second.db")
            init_database()
            self.client.cookies.clear()
            second = self.run_cases()
        finally:
            second_dir.cleanup()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
