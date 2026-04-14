from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.engine.fred import fetch_latest_observation

from app.engine.monte_carlo import margin_call_probability
from app.engine.sbloc_cashflow import compute_sbloc_cashflow, stress_test_rates
from app.engine.tax_drag import estimate_gross_sale_for_net_cash, ten_year_opportunity_cost
from app.routes.models import (
    RiskHorizonResult,
    RiskRequest,
    RiskResponse,
    ScenarioARequest,
    ScenarioAResponse,
    ScenarioBRequest,
    ScenarioBResponse,
    StressRow,
)


router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/macro")
async def macro() -> dict:
    """
    Macro indicators used in the UI banner.
    If FRED_API_KEY isn't set, returns reasonable placeholders.
    """
    if not settings.fred_api_key:
        # Fallback values so UI works out-of-the-box.
        sofr = {"series_id": settings.sofr_series_id, "date": None, "value": 0.05}
        effr = {"series_id": settings.effr_series_id, "date": None, "value": 0.053}
        return {"sofr": sofr, "effr": effr, "source": "fallback"}

    sofr_latest = await fetch_latest_observation(
        api_key=settings.fred_api_key, series_id=settings.sofr_series_id
    )
    effr_latest = await fetch_latest_observation(
        api_key=settings.fred_api_key, series_id=settings.effr_series_id
    )

    def normalize_rate(v: float | None) -> float | None:
        # FRED commonly reports rates in percent (e.g. 5.33 means 5.33%).
        # The frontend expects decimals for `formatPct` (e.g. 0.0533).
        if v is None:
            return None
        return v / 100.0 if v > 1.0 else v

    return {
        "sofr": {
            "series_id": sofr_latest.series_id,
            "date": sofr_latest.date,
            "value": normalize_rate(sofr_latest.value),
        },
        "effr": {
            "series_id": effr_latest.series_id,
            "date": effr_latest.date,
            "value": normalize_rate(effr_latest.value),
        },
        "source": "fred",
    }


@router.post("/scenario-a")
def scenario_a(req: ScenarioARequest) -> ScenarioAResponse:
    r = estimate_gross_sale_for_net_cash(
        net_cash_needed=req.deal.down_payment_required,
        weighted_average_cost_basis_pct=req.portfolio.weighted_average_cost_basis_pct,
        capital_gains_tax_rate=req.capital_gains_tax_rate,
    )
    opp = ten_year_opportunity_cost(
        gross_sale_amount=r.gross_sale_required,
        annual_equity_return=req.portfolio.expected_equity_return_annual,
        years=10,
    )
    return ScenarioAResponse(
        gross_sale_required=r.gross_sale_required,
        capital_gains_tax_paid=r.capital_gains_tax_paid,
        estimated_capital_gains_realized=r.estimated_capital_gains_realized,
        ten_year_opportunity_cost=opp,
    )


@router.post("/scenario-b")
def scenario_b(req: ScenarioBRequest) -> ScenarioBResponse:
    base = compute_sbloc_cashflow(
        loan_amount=req.loan_amount,
        sofr_rate=req.sofr_rate,
        broker_spread=req.broker_spread,
        expected_monthly_rent=req.deal.expected_monthly_rent,
        operating_expenses=req.deal.operating_expenses,
    )

    stressed_rows: list[StressRow] = []
    for sofr in stress_test_rates(base_sofr=req.sofr_rate):
        row = compute_sbloc_cashflow(
            loan_amount=req.loan_amount,
            sofr_rate=sofr,
            broker_spread=req.broker_spread,
            expected_monthly_rent=req.deal.expected_monthly_rent,
            operating_expenses=req.deal.operating_expenses,
        )
        stressed_rows.append(
            StressRow(
                sofr_rate=sofr,
                annual_rate=row.annual_rate,
                monthly_interest_payment=row.monthly_interest_payment,
                net_cashflow_monthly=row.net_cashflow_monthly,
            )
        )

    return ScenarioBResponse(
        base=StressRow(
            sofr_rate=req.sofr_rate,
            annual_rate=base.annual_rate,
            monthly_interest_payment=base.monthly_interest_payment,
            net_cashflow_monthly=base.net_cashflow_monthly,
        ),
        stressed=stressed_rows,
    )


@router.post("/risk")
def risk(req: RiskRequest) -> RiskResponse:
    danger_value = (
        req.loan_amount / req.maintenance_ltv_max if req.loan_amount > 0 else float("inf")
    )
    results: list[RiskHorizonResult] = []
    for horizon in req.horizons_months:
        r = margin_call_probability(
            portfolio_value=req.portfolio_value,
            loan_amount=req.loan_amount,
            maintenance_ltv_max=req.maintenance_ltv_max,
            mu_annual=req.mu_annual,
            sigma_annual=req.sigma_annual,
            horizon_months=horizon,
            runs=req.runs,
        )
        results.append(
            RiskHorizonResult(
                horizon_months=r.horizon_months,
                breach_probability=r.breach_probability,
                breach_count=r.breach_count,
                runs=r.runs,
                ending_values=r.ending_values,
            )
        )
    return RiskResponse(danger_portfolio_value=float(danger_value), results=results)

