from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SblocCashflowResult:
    loan_amount: float
    annual_rate: float
    monthly_interest_payment: float
    noi_monthly: float
    net_cashflow_monthly: float


def compute_sbloc_cashflow(
    *,
    loan_amount: float,
    sofr_rate: float,
    broker_spread: float,
    expected_monthly_rent: float,
    operating_expenses: float,
) -> SblocCashflowResult:
    if loan_amount < 0:
        raise ValueError("loan_amount must be >= 0")
    annual_rate = max(0.0, sofr_rate + broker_spread)
    monthly_interest = loan_amount * annual_rate / 12.0
    noi = expected_monthly_rent - operating_expenses
    net = noi - monthly_interest
    return SblocCashflowResult(
        loan_amount=float(loan_amount),
        annual_rate=float(annual_rate),
        monthly_interest_payment=float(monthly_interest),
        noi_monthly=float(noi),
        net_cashflow_monthly=float(net),
    )


def stress_test_rates(
    *,
    base_sofr: float,
    bps_shocks: list[int] | tuple[int, ...] = (100, 200, 300),
) -> list[float]:
    return [float(base_sofr + (bps / 10000.0)) for bps in bps_shocks]

