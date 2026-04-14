from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaxDragResult:
    net_cash_needed: float
    gross_sale_required: float
    capital_gains_tax_paid: float
    estimated_capital_gains_realized: float
    ten_year_opportunity_cost: float


def estimate_gross_sale_for_net_cash(
    *,
    net_cash_needed: float,
    weighted_average_cost_basis_pct: float,
    capital_gains_tax_rate: float,
) -> TaxDragResult:
    """
    Compute gross stock sale required to net `net_cash_needed` after cap gains taxes.

    Assumptions:
    - weighted_average_cost_basis_pct is in [0, 1] (e.g. 0.6 means 60% cost basis).
    - tax is only on gains portion of sold amount.
    """
    if net_cash_needed <= 0:
        return TaxDragResult(
            net_cash_needed=0.0,
            gross_sale_required=0.0,
            capital_gains_tax_paid=0.0,
            estimated_capital_gains_realized=0.0,
            ten_year_opportunity_cost=0.0,
        )

    wab = weighted_average_cost_basis_pct
    if wab <= 0 or wab > 1:
        raise ValueError("weighted_average_cost_basis_pct must be in (0, 1].")
    if capital_gains_tax_rate < 0 or capital_gains_tax_rate >= 1:
        raise ValueError("capital_gains_tax_rate must be in [0, 1).")

    gain_fraction = 1.0 - wab
    # net = gross - tax_rate * gains = gross - tax_rate * gross * gain_fraction
    effective_keep = 1.0 - capital_gains_tax_rate * gain_fraction
    if effective_keep <= 0:
        raise ValueError("Inputs imply non-positive net proceeds.")

    gross = net_cash_needed / effective_keep
    gains = gross * gain_fraction
    tax_paid = gains * capital_gains_tax_rate

    return TaxDragResult(
        net_cash_needed=float(net_cash_needed),
        gross_sale_required=float(gross),
        capital_gains_tax_paid=float(tax_paid),
        estimated_capital_gains_realized=float(gains),
        ten_year_opportunity_cost=0.0,
    )


def ten_year_opportunity_cost(
    *,
    gross_sale_amount: float,
    annual_equity_return: float,
    years: int = 10,
) -> float:
    if gross_sale_amount <= 0:
        return 0.0
    if years <= 0:
        return 0.0
    return float(gross_sale_amount * ((1.0 + annual_equity_return) ** years - 1.0))

