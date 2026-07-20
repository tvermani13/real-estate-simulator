from __future__ import annotations

from dataclasses import dataclass

from app.routes.product_models import AffordabilityResponse, FinancialProfile, PurchaseRange


@dataclass(frozen=True)
class RiskPolicy:
    front_end_ratio: float
    back_end_ratio: float
    take_home_housing_ratio: float
    investment_capital_ratio: float


RISK_POLICIES = {
    "conservative": RiskPolicy(0.25, 0.36, 0.30, 0.45),
    "balanced": RiskPolicy(0.28, 0.40, 0.35, 0.60),
    "growth": RiskPolicy(0.31, 0.43, 0.40, 0.75),
}


def monthly_mortgage_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    months = years * 12
    if annual_rate <= 0:
        return principal / months
    monthly_rate = annual_rate / 12
    return principal * monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)


def mortgage_payment_factor(annual_rate: float, years: int) -> float:
    return monthly_mortgage_payment(1.0, annual_rate, years)


def calculate_affordability(profile: FinancialProfile) -> AffordabilityResponse:
    policy = RISK_POLICIES[profile.risk_tolerance]
    gross_monthly = profile.annual_gross_income / 12
    required_reserves = profile.reserve_months * (
        profile.monthly_living_expenses + profile.monthly_debt_payments
    )
    investable_cash = max(0.0, profile.liquid_cash - required_reserves)
    liquid_net_worth = profile.liquid_cash + profile.taxable_investments - profile.total_liabilities
    net_worth = (
        profile.liquid_cash
        + profile.taxable_investments
        + profile.retirement_assets
        + profile.other_assets
        - profile.total_liabilities
    )
    current_dti = profile.monthly_debt_payments / gross_monthly if gross_monthly else 0.0

    front_end_budget = gross_monthly * policy.front_end_ratio
    back_end_budget = max(0.0, gross_monthly * policy.back_end_ratio - profile.monthly_debt_payments)
    take_home_budget = (
        profile.monthly_take_home_income * policy.take_home_housing_ratio
        if profile.monthly_take_home_income > 0
        else float("inf")
    )
    monthly_housing_budget = max(0.0, min(front_end_budget, back_end_budget, take_home_budget))

    payment_factor = mortgage_payment_factor(profile.mortgage_rate, profile.mortgage_term_years)
    primary_loan_ratio = 1 - profile.primary_down_payment_pct
    primary_monthly_cost_factor = (
        primary_loan_ratio * payment_factor
        + (profile.property_tax_rate + profile.home_insurance_rate) / 12
    )
    primary_payment_max = max(
        0.0,
        (monthly_housing_budget - profile.primary_hoa_monthly) / primary_monthly_cost_factor,
    ) if primary_monthly_cost_factor else 0.0
    primary_cash_max = investable_cash / (
        profile.primary_down_payment_pct + profile.closing_cost_rate
    )
    primary_stretch = min(primary_payment_max, primary_cash_max)
    primary_comfort = primary_stretch * 0.88

    deployable_investment_cash = investable_cash * policy.investment_capital_ratio
    investment_cash_max = deployable_investment_cash / (
        profile.investment_down_payment_pct + profile.closing_cost_rate
    )
    investment_comfort = investment_cash_max * 0.88

    return AffordabilityResponse(
        net_worth=round(net_worth, 2),
        liquid_net_worth=round(liquid_net_worth, 2),
        required_reserves=round(required_reserves, 2),
        investable_cash=round(investable_cash, 2),
        current_back_end_dti=round(current_dti, 6),
        primary=PurchaseRange(
            purpose="primary",
            comfortable_min=round(primary_comfort * 0.75, 2),
            comfortable_max=round(primary_comfort, 2),
            stretch_max=round(primary_stretch, 2),
            payment_limited_max=round(primary_payment_max, 2),
            cash_limited_max=round(primary_cash_max, 2),
            monthly_payment_budget=round(monthly_housing_budget, 2),
            capital_available=round(investable_cash, 2),
            down_payment_pct=profile.primary_down_payment_pct,
            explanation="Limited by the lower of your risk-adjusted monthly housing budget and cash after reserves.",
        ),
        investment=PurchaseRange(
            purpose="investment",
            comfortable_min=round(investment_comfort * 0.70, 2),
            comfortable_max=round(investment_comfort, 2),
            stretch_max=round(investment_cash_max, 2),
            payment_limited_max=None,
            cash_limited_max=round(investment_cash_max, 2),
            monthly_payment_budget=None,
            capital_available=round(deployable_investment_cash, 2),
            down_payment_pct=profile.investment_down_payment_pct,
            explanation="Liquidity sets the initial ceiling; every listing must also pass your DSCR, cash-flow, and return thresholds.",
        ),
        assumptions=[
            f"{profile.reserve_months} months of living expenses and debt payments remain untouched.",
            f"Primary housing is tested at {policy.front_end_ratio:.0%} front-end and {policy.back_end_ratio:.0%} back-end DTI.",
            "Taxes, insurance, HOA, closing costs, and mortgage principal and interest are included.",
            "This is a planning range, not a lender pre-approval or financial advice.",
        ],
    )
