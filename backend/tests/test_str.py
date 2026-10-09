from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.engine.str_underwriting import analyze_str, monthly_payment, remaining_principal
from app.routes.str_models import StrDeal


class StrUnderwritingTests(unittest.TestCase):
    def example(self, **changes: object) -> StrDeal:
        return StrDeal(**{
            "name": "Test cabin", "address": "1 Test Lane, PA",
            "property_price": 350_000, "annual_gross_revenue": 65_000,
            "owner_nights": 0, "revenue_source": "assumption",
            "regulatory_gate": "unknown", "hoa_gate": "unknown",
            **changes,
        })

    def test_base_accounting_identity(self) -> None:
        out = analyze_str(self.example())
        self.assertAlmostEqual(
            out.annual_noi,
            out.annual_gross_after_owner_use
            - out.annual_variable_operating_costs
            - out.annual_fixed_operating_costs,
        )
        self.assertAlmostEqual(out.annual_cash_flow, out.annual_noi - out.annual_debt_service)
        self.assertEqual(out.screening_status, "research_only")

    def test_hybrid_monthly_owner_use_uses_peak_revenue(self) -> None:
        gross = [2000.0] * 12
        gross[9] = 20_000
        d = self.example(
            strategy="hybrid", owner_nights=10,
            owner_nights_by_month=[0] * 9 + [10, 0, 0],
            monthly_gross_revenue=gross,
        )
        out = analyze_str(d)
        self.assertAlmostEqual(out.foregone_owner_revenue, 20_000 * 10 / 31)
        self.assertAlmostEqual(out.annual_gross_before_owner_use, 42_000)

    def test_hybrid_unseasonal_fallback_is_visible(self) -> None:
        out = analyze_str(self.example(strategy="hybrid", owner_nights=21))
        self.assertAlmostEqual(out.foregone_owner_revenue, 65_000 * 21 / 365)
        self.assertTrue(any("uniform" in msg for msg in out.warnings))

    def test_invalid_owner_use_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.example(strategy="hybrid", owner_nights=20,
                         owner_nights_by_month=[1] * 12)

    def test_revenue_downside_monotonic_and_refinance(self) -> None:
        d = self.example(refinance_apr=0.05, refinance_fees=1000)
        out = analyze_str(d)
        self.assertLess(out.downside_cash_flow, out.annual_cash_flow)
        self.assertGreater(out.upside_cash_flow, out.annual_cash_flow)
        self.assertGreater(out.refinance_annual_payment_savings, 0)
        self.assertIsNotNone(out.refinance_cost_payback_years)

    def test_no_debt_zero_rate(self) -> None:
        out = analyze_str(self.example(down_payment_pct=1, mortgage_apr=0))
        self.assertEqual(out.annual_debt_service, 0)
        self.assertIsNone(out.debt_service_coverage)
        self.assertEqual(remaining_principal(0, 0, 360, 24), 0)
        self.assertAlmostEqual(monthly_payment(12000, 0, 12), 1000)

    def test_gates_never_mark_unverified_as_investable(self) -> None:
        d = self.example(revenue_source="licensed_property_forecast",
                         comparable_count=12, forecast_as_of="2026-10-09",
                         monthly_gross_revenue=[10_000] * 12,
                         regulatory_gate="blocked", hoa_gate="verified")
        self.assertEqual(analyze_str(d).screening_status, "blocked")


if __name__ == "__main__":
    unittest.main()
