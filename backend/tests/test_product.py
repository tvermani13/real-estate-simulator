from __future__ import annotations

import asyncio
import unittest

from app.core.auth import hash_password, verify_password
from app.engine.affordability import calculate_affordability
from app.engine.monte_carlo import margin_call_probability
from app.engine.property_matcher import analyze_property
from app.routes.product_models import FinancialProfile, PropertyListing, SearchCriteria
from app.services.property_providers import (
    DemoPropertyProvider,
    RentCastPropertyProvider,
    _market_preset,
)


class ProductEngineTests(unittest.TestCase):
    def test_password_hashes_are_salted_and_verifiable(self) -> None:
        first = hash_password("planningpass1")
        second = hash_password("planningpass1")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("planningpass1", first))
        self.assertFalse(verify_password("wrongpass1", first))

    def test_affordability_preserves_reserves_and_uses_lower_constraint(self) -> None:
        profile = FinancialProfile(
            annual_gross_income=180_000,
            monthly_take_home_income=10_500,
            monthly_debt_payments=700,
            monthly_living_expenses=4_500,
            liquid_cash=160_000,
            reserve_months=6,
        )
        result = calculate_affordability(profile)
        self.assertEqual(result.required_reserves, 31_200)
        self.assertEqual(result.investable_cash, 128_800)
        self.assertLessEqual(result.primary.stretch_max, result.primary.cash_limited_max)
        self.assertLess(result.primary.comfortable_max, result.primary.stretch_max)

    def test_investment_match_includes_debt_and_operating_metrics(self) -> None:
        profile = FinancialProfile(liquid_cash=250_000)
        criteria = SearchCriteria(
            purpose="investment",
            location="Raleigh, NC",
            max_price=350_000,
            min_bedrooms=3,
            min_bathrooms=2,
        )
        listing = PropertyListing(
            id="test-listing",
            provider="test",
            address="1 Test Street, Raleigh, NC",
            city="Raleigh",
            state="NC",
            price=275_000,
            bedrooms=3,
            bathrooms=2,
            square_feet=1_700,
            property_type="Single Family",
            estimated_rent=2_650,
            rent_estimate_source="test",
        )
        match = analyze_property(listing, criteria, profile)
        self.assertIsNotNone(match.metrics.dscr)
        self.assertIsNotNone(match.metrics.cap_rate)
        self.assertIsNotNone(match.metrics.cash_on_cash)
        self.assertIsNotNone(match.metrics.monthly_cashflow)
        self.assertGreater(match.metrics.cash_required, 0)

    def test_demo_provider_is_explicit_and_respects_market(self) -> None:
        criteria = SearchCriteria(
            purpose="primary",
            location="Cleveland, OH",
            max_price=500_000,
            min_bedrooms=3,
            min_bathrooms=2,
        )
        listings = asyncio.run(DemoPropertyProvider().sale_listings(criteria))
        self.assertGreater(len(listings), 0)
        self.assertTrue(all(item.provider == "demo" for item in listings))
        self.assertTrue(all("Cleveland, OH" in item.address for item in listings))

    def test_fairfield_county_uses_geographic_query_and_strict_county_filter(self) -> None:
        criteria = SearchCriteria(location="Fairfield County, CT")
        provider = RentCastPropertyProvider("test-key")
        params = provider._query_params(criteria)

        self.assertAlmostEqual(params["latitude"], 41.2560)
        self.assertAlmostEqual(params["longitude"], -73.3709)
        self.assertEqual(params["radius"], 32)
        self.assertNotIn("city", params)

        preset = _market_preset(criteria.location)
        filtered = provider._filter_market_rows(
            [
                {"id": "fairfield-1", "county": "Fairfield", "state": "CT"},
                {"id": "fairfield-2", "county": "Fairfield County", "state": "CT"},
                {"id": "westchester", "county": "Westchester", "state": "NY"},
            ],
            preset,
        )
        self.assertEqual([row["id"] for row in filtered], ["fairfield-1", "fairfield-2"])

    def test_nationwide_location_modes_include_configurable_address_radius(self) -> None:
        provider = RentCastPropertyProvider("test-key")

        zip_params = provider._query_params(SearchCriteria(location="06830"))
        self.assertEqual(zip_params["zipCode"], "06830")

        city_params = provider._query_params(SearchCriteria(location="Stamford, CT"))
        self.assertEqual(city_params["city"], "Stamford")
        self.assertEqual(city_params["state"], "CT")

        address_params = provider._query_params(
            SearchCriteria(location="1 Main Street, Hartford, CT", radius_miles=12)
        )
        self.assertEqual(address_params["address"], "1 Main Street, Hartford, CT")
        self.assertEqual(address_params["radius"], 12)
        self.assertNotIn("city", address_params)

    def test_zero_loan_has_no_margin_breach_and_distribution_is_bounded(self) -> None:
        result = margin_call_probability(
            portfolio_value=1_000_000,
            loan_amount=0,
            maintenance_ltv_max=0.7,
            mu_annual=0.07,
            sigma_annual=0.22,
            horizon_months=60,
            runs=10_000,
        )
        self.assertEqual(result.breach_probability, 0)
        self.assertEqual(result.breach_count, 0)
        self.assertEqual(len(result.ending_value_sample), 512)
        self.assertEqual(
            set(result.ending_value_percentiles),
            {"p05", "p25", "p50", "p75", "p95"},
        )


if __name__ == "__main__":
    unittest.main()
