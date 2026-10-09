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

    def test_negative_monthly_revenue_and_owner_nights_are_rejected(self) -> None:
        for changes in ({"monthly_gross_revenue": [-1] + [1000] * 11},
                        {"strategy": "hybrid", "owner_nights_by_month": [-1] + [0] * 11},
                        {"annual_gross_revenue": float("inf")},
                        {"mortgage_apr": float("nan")},
                        {"forecast_as_of": "not-a-date"},
                        {"strategy": "investment", "owner_nights_by_month": [1] * 12}):
            with self.assertRaises(ValidationError):
                self.example(**changes)

    def test_full_owner_use_and_zero_capital_are_json_safe(self) -> None:
        d = self.example(strategy="hybrid", owner_nights=365,
                         owner_nights_by_month=[31,28,31,30,31,30,31,31,30,31,30,31],
                         monthly_gross_revenue=[1000]*12,
                         down_payment_pct=0, closing_cost_pct=0, furnishings=0, cash_reserve=0)
        out = analyze_str(d)
        self.assertEqual(out.annual_gross_after_owner_use, 0)
        self.assertIsNone(out.break_even_gross_before_owner_use)
        self.assertIsNone(out.cash_on_cash)
        self.assertNotIn("Infinity", out.model_dump_json())

    def test_zero_gross_with_full_owner_use_has_no_breakeven(self) -> None:
        out = analyze_str(self.example(strategy="hybrid", owner_nights=365, annual_gross_revenue=0))
        self.assertIsNone(out.break_even_gross_before_owner_use)

    def test_personal_use_displaces_expected_bookings_not_adr_twice(self) -> None:
        # $200 ADR × 50% occupancy × 31 nights; 10 blocked nights displace $100/night.
        revenue = [0]*12
        revenue[0] = 3100
        deal = self.example(strategy="hybrid", owner_nights=10,
                            owner_nights_by_month=[10]+[0]*11, monthly_gross_revenue=revenue)
        out = analyze_str(deal)
        self.assertAlmostEqual(out.foregone_owner_revenue, 1000)
        self.assertAlmostEqual(out.annual_gross_after_owner_use, 2100)
        self.assertAlmostEqual(out.downside_cash_flow,
                               2100*.8*.6 - out.annual_fixed_operating_costs - out.annual_debt_service)

    def test_amortization_matches_independent_payment_schedule(self) -> None:
        principal, rate, term = 250000, .08, 360
        payment = monthly_payment(principal, rate, term)
        self.assertAlmostEqual(payment, 1834.411434698448, places=6)
        balance = principal
        for month in range(1, term+1):
            balance = balance*(1+rate/12)-payment
            if month in (1,24,180,359,360):
                self.assertAlmostEqual(remaining_principal(principal, rate, term, month), max(0,balance), places=5)
        self.assertAlmostEqual(monthly_payment(12000, 1e-12, 12), 1000, places=6)

    def test_refinance_uses_amortized_balance_and_remaining_term(self) -> None:
        d = self.example(refinance_after_months=24, refinance_apr=.05, refinance_fees=2000)
        out = analyze_str(d)
        principal = 350000*.75
        balance = principal
        payment = monthly_payment(principal,.08,360)
        for _ in range(24):
            balance=balance*(1+.08/12)-payment
        expected_new = monthly_payment(balance,.05,336)*12
        self.assertAlmostEqual(out.refinance_remaining_principal, balance)
        self.assertEqual(out.refinance_remaining_term_months, 336)
        self.assertAlmostEqual(out.future_refinanced_annual_cash_flow, out.annual_noi-expected_new)
        self.assertAlmostEqual(out.refinance_cost_payback_years, 2000/(payment*12-expected_new))
        worse=analyze_str(self.example(refinance_apr=.15, refinance_fees=2000))
        self.assertLess(worse.refinance_annual_payment_savings,0)
        self.assertIsNone(worse.refinance_cost_payback_years)

    def test_dscr_and_cash_on_cash_match_explicit_accounting(self) -> None:
        out=analyze_str(self.example(hoa_annual=1200))
        gross=65000
        noi=gross*.6-(6000+3600+4800+2500+5000+1200)
        invested=350000*(.25+.05)+25000+15000
        self.assertAlmostEqual(out.annual_noi,noi)
        self.assertAlmostEqual(out.debt_service_coverage,noi/out.annual_debt_service)
        self.assertAlmostEqual(out.cash_on_cash,(noi-out.annual_debt_service)/invested)
        self.assertAlmostEqual(out.break_even_gross_before_owner_use,
                               (out.annual_fixed_operating_costs+out.annual_debt_service)/.6)

    def test_leap_february_calendar_displacement(self) -> None:
        days = [31,29,31,30,31,30,31,31,30,31,30,31]
        out = analyze_str(self.example(strategy="hybrid", owner_nights=29,
            owner_nights_by_month=[0,29]+[0]*10, monthly_calendar_days=days,
            monthly_gross_revenue=[1000,2900]+[1000]*10))
        self.assertEqual(out.foregone_owner_revenue, 2900)
        with self.assertRaises(ValidationError):
            self.example(monthly_calendar_days=[28]*12)


if __name__ == "__main__":
    unittest.main()
