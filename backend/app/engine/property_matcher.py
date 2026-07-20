from __future__ import annotations

from app.engine.affordability import calculate_affordability, monthly_mortgage_payment
from app.routes.product_models import (
    FinancialProfile,
    PropertyListing,
    PropertyMatch,
    PropertyMetrics,
    SearchCriteria,
)


def _ratio_score(value: float | None, target: float, points: float) -> float:
    if value is None:
        return 0.0
    if target <= 0:
        return points
    return min(points, max(0.0, points * value / target))


def analyze_property(
    listing: PropertyListing,
    criteria: SearchCriteria,
    profile: FinancialProfile,
) -> PropertyMatch:
    affordability = calculate_affordability(profile)
    purpose_range = affordability.primary if criteria.purpose == "primary" else affordability.investment
    down_pct = criteria.down_payment_pct or purpose_range.down_payment_pct
    loan_amount = listing.price * (1 - down_pct)
    principal_interest = monthly_mortgage_payment(
        loan_amount, profile.mortgage_rate, profile.mortgage_term_years
    )
    taxes = listing.price * profile.property_tax_rate / 12
    insurance = listing.price * profile.home_insurance_rate / 12
    total_housing = principal_interest + taxes + insurance + listing.hoa_monthly
    cash_required = listing.price * (down_pct + profile.closing_cost_rate)
    reasons: list[str] = []
    warnings: list[str] = []

    max_price = criteria.max_price or purpose_range.comfortable_max
    min_price = criteria.min_price or 0
    within_price = min_price <= listing.price <= max_price
    score = 0.0
    if within_price:
        score += 22
        reasons.append("Inside your saved price range")
    elif listing.price <= purpose_range.stretch_max:
        score += 9
        warnings.append("Above your comfortable range but below the stretch ceiling")
    else:
        warnings.append("Above your calculated purchase ceiling")

    if cash_required <= purpose_range.capital_available:
        score += 18
        reasons.append("Down payment and closing costs fit available capital")
    else:
        warnings.append("Upfront cash exceeds capital available after reserves")

    projected_rent: float | None = None
    noi: float | None = None
    cashflow: float | None = None
    cap_rate: float | None = None
    cash_on_cash: float | None = None
    dscr: float | None = None

    if criteria.purpose == "primary":
        budget = purpose_range.monthly_payment_budget or 0
        if total_housing <= budget:
            score += 35
            reasons.append("Estimated all-in housing payment fits your monthly budget")
        elif total_housing <= budget * 1.10:
            score += 15
            warnings.append("Monthly payment is within 10% of the stretch budget")
        else:
            warnings.append("Estimated monthly payment exceeds your risk-adjusted budget")
        score += 10 if listing.bedrooms >= criteria.min_bedrooms else 0
        score += 8 if listing.bathrooms >= criteria.min_bathrooms else 0
        if listing.days_on_market is not None and listing.days_on_market <= 30:
            score += 7
            reasons.append("Recently listed")
    else:
        projected_rent = listing.estimated_rent
        if projected_rent is None:
            warnings.append("No market-rent estimate is available, so yield metrics are incomplete")
        else:
            vacancy = projected_rent * profile.investment_vacancy_rate
            variable_opex = projected_rent * (
                profile.investment_management_rate
                + profile.investment_maintenance_rate
                + profile.investment_capex_rate
            )
            noi = projected_rent - vacancy - variable_opex - taxes - insurance - listing.hoa_monthly
            cashflow = noi - principal_interest
            cap_rate = noi * 12 / listing.price if listing.price else None
            cash_on_cash = cashflow * 12 / cash_required if cash_required else None
            dscr = noi / principal_interest if principal_interest else None

            target_dscr = criteria.min_dscr if criteria.min_dscr is not None else profile.min_dscr
            target_coc = criteria.min_cash_on_cash if criteria.min_cash_on_cash is not None else profile.min_cash_on_cash
            target_cashflow = criteria.min_monthly_cashflow if criteria.min_monthly_cashflow is not None else profile.min_monthly_cashflow
            target_cap = criteria.min_cap_rate if criteria.min_cap_rate is not None else 0.05

            score += _ratio_score(dscr, target_dscr, 20)
            score += _ratio_score(cash_on_cash, target_coc, 18)
            score += _ratio_score(cap_rate, target_cap, 12)
            score += 10 if cashflow >= target_cashflow else max(0, 10 * cashflow / target_cashflow) if target_cashflow > 0 else 0

            if dscr is not None and dscr >= target_dscr:
                reasons.append(f"DSCR clears your {target_dscr:.2f} target")
            else:
                warnings.append(f"DSCR is below your {target_dscr:.2f} target")
            if cashflow >= target_cashflow:
                reasons.append("Projected cash flow clears your monthly target")
            else:
                warnings.append("Projected cash flow is below your monthly target")
            if cash_on_cash is not None and cash_on_cash >= target_coc:
                reasons.append("Cash-on-cash return clears your target")
            else:
                warnings.append("Cash-on-cash return is below your target")
        if listing.days_on_market is not None and listing.days_on_market >= 30:
            score += 5
            reasons.append("Longer time on market may create negotiating room")

    score = round(min(100.0, max(0.0, score)), 1)
    verdict = "strong" if score >= max(criteria.min_match_score, 78) else "possible" if score >= criteria.min_match_score else "outside_range"
    return PropertyMatch(
        listing=listing,
        metrics=PropertyMetrics(
            monthly_principal_interest=round(principal_interest, 2),
            monthly_taxes=round(taxes, 2),
            monthly_insurance=round(insurance, 2),
            total_monthly_housing_cost=round(total_housing, 2),
            cash_required=round(cash_required, 2),
            projected_monthly_rent=round(projected_rent, 2) if projected_rent is not None else None,
            noi_monthly=round(noi, 2) if noi is not None else None,
            monthly_cashflow=round(cashflow, 2) if cashflow is not None else None,
            cap_rate=round(cap_rate, 6) if cap_rate is not None else None,
            cash_on_cash=round(cash_on_cash, 6) if cash_on_cash is not None else None,
            dscr=round(dscr, 4) if dscr is not None else None,
        ),
        score=score,
        verdict=verdict,
        reasons=reasons,
        warnings=warnings,
    )
