from __future__ import annotations

from app.routes.str_models import StrDeal, StrUnderwriting

DAYS_BY_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    if months <= 0 or principal <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** (-months))


def remaining_principal(principal: float, annual_rate: float, term_months: int, elapsed: int) -> float:
    if principal <= 0 or elapsed >= term_months:
        return 0.0
    payment = monthly_payment(principal, annual_rate, term_months)
    rate = annual_rate / 12
    if rate == 0:
        return max(0.0, principal - elapsed * payment)
    factor = (1 + rate) ** elapsed
    return max(0.0, principal * factor - payment * ((factor - 1) / rate))


def analyze_str(deal: StrDeal) -> StrUnderwriting:
    warnings: list[str] = []
    gross = sum(deal.monthly_gross_revenue) if deal.monthly_gross_revenue is not None else deal.annual_gross_revenue
    if deal.monthly_gross_revenue is not None and abs(gross - deal.annual_gross_revenue) > 1:
        warnings.append("Monthly gross revenue takes precedence over the annual input.")
    if deal.revenue_source in ("assumption", "market_average"):
        warnings.append("Revenue is not a property-specific verified forecast; research use only.")
    if not deal.forecast_as_of:
        warnings.append("Revenue evidence has no as-of date.")
    if deal.comparable_count < 8 and deal.revenue_source != "actual_operations":
        warnings.append("Fewer than 8 comparable rentals support this forecast.")
    if deal.monthly_gross_revenue is None:
        warnings.append("No 12-month revenue profile: owner-use loss assumes uniform revenue per day.")
    if deal.regulatory_gate != "verified":
        warnings.append("Written municipal STR eligibility remains unverified or blocked.")
    if deal.hoa_gate != "verified":
        warnings.append("HOA/deed STR eligibility remains unverified or blocked.")
    if deal.strategy == "hybrid":
        warnings.append("Lender second-home eligibility and mixed-use tax treatment must be checked.")
    warnings.append("Check actual tax assessment, flood/insurance, septic, winter access, and vendor quotes.")

    owner_loss = 0.0
    if deal.strategy == "hybrid":
        if deal.monthly_gross_revenue is not None and deal.owner_nights_by_month is not None:
            owner_loss = sum(
                monthly_revenue * (nights / days)
                for monthly_revenue, nights, days in zip(
                    deal.monthly_gross_revenue, deal.owner_nights_by_month, DAYS_BY_MONTH
                )
            )
        else:
            owner_loss = gross * deal.owner_nights / 365
            if deal.owner_nights and deal.monthly_gross_revenue is not None:
                warnings.append("Owner-night timing not specified; seasonal revenue loss is approximated.")
    owner_loss = min(gross, owner_loss)
    variable_rate = deal.management_pct + deal.platform_pct + deal.turnovers_pct
    fixed = (
        deal.property_tax_annual + deal.insurance_annual + deal.utilities_annual
        + deal.property_services_annual + deal.repairs_capex_annual
    )
    loan = deal.property_price * (1 - deal.down_payment_pct)
    total_months = deal.loan_term_years * 12
    monthly_debt = monthly_payment(loan, deal.mortgage_apr, total_months)
    annual_debt = 12 * monthly_debt
    capital = (
        deal.property_price * (deal.down_payment_pct + deal.closing_cost_pct)
        + deal.furnishings + deal.cash_reserve
    )

    def cash_flow_at(revenue_factor: float) -> float:
        adjusted_gross = gross * revenue_factor
        adjusted_owner_loss = owner_loss * revenue_factor
        realized_gross = max(0, adjusted_gross - adjusted_owner_loss)
        return realized_gross * (1 - variable_rate) - fixed - annual_debt

    realized = gross - owner_loss
    variable = realized * variable_rate
    noi = realized - variable - fixed
    cf = noi - annual_debt
    if deal.owner_nights and gross > 0:
        owner_fraction = owner_loss / gross
    else:
        owner_fraction = 0
    break_even = (
        (fixed + annual_debt) / ((1 - variable_rate) * (1 - owner_fraction))
        if owner_fraction < 1 else float("inf")
    )
    debt_coverage = (noi / annual_debt) if annual_debt > 0 else None

    balance = remaining_principal(loan, deal.mortgage_apr, total_months, deal.refinance_after_months)
    new_debt = monthly_payment(balance, deal.refinance_apr, total_months - deal.refinance_after_months) * 12
    savings = annual_debt - new_debt
    payback = deal.refinance_fees / savings if savings > 0 else None

    blocked = deal.regulatory_gate == "blocked" or deal.hoa_gate == "blocked"
    vetted = (
        deal.regulatory_gate == "verified" and deal.hoa_gate == "verified"
        and deal.revenue_source in ("licensed_property_forecast", "actual_operations")
        and bool(deal.forecast_as_of) and (deal.comparable_count >= 8 or deal.revenue_source == "actual_operations")
        and deal.monthly_gross_revenue is not None
    )
    if blocked:
        status = "blocked"
    elif not vetted:
        status = "research_only"
    elif (debt_coverage is None or debt_coverage >= 1.25) and cf / capital >= 0.08 and cash_flow_at(0.8) >= 0:
        status = "meets_financial_screen"
    else:
        status = "below_financial_screen"

    return StrUnderwriting(
        annual_gross_before_owner_use=gross,
        foregone_owner_revenue=owner_loss,
        annual_gross_after_owner_use=realized,
        annual_fixed_operating_costs=fixed,
        annual_variable_operating_costs=variable,
        annual_noi=noi,
        annual_debt_service=annual_debt,
        annual_cash_flow=cf,
        downside_cash_flow=cash_flow_at(0.8),
        upside_cash_flow=cash_flow_at(1.2),
        debt_service_coverage=debt_coverage,
        cap_rate=noi / deal.property_price,
        cash_on_cash=cf / capital if capital else 0,
        capital_required_including_reserves=capital,
        break_even_gross_before_owner_use=break_even,
        future_refinanced_annual_cash_flow=noi - new_debt,
        refinance_annual_payment_savings=savings,
        refinance_cost_payback_years=payback,
        screening_status=status,
        warnings=warnings,
    )
