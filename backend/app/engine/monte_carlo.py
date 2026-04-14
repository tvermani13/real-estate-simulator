from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonteCarloResult:
    horizon_months: int
    runs: int
    breach_probability: float
    ending_values: list[float]
    breach_count: int


def gbm_paths_monthly(
    *,
    s0: float,
    mu_annual: float,
    sigma_annual: float,
    months: int,
    runs: int,
    seed: int | None = 42,
) -> np.ndarray:
    if s0 <= 0:
        raise ValueError("s0 must be > 0")
    if sigma_annual < 0:
        raise ValueError("sigma_annual must be >= 0")
    if months <= 0:
        raise ValueError("months must be > 0")
    if runs <= 0:
        raise ValueError("runs must be > 0")

    dt = 1.0 / 12.0
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(size=(runs, months))
    drift = (mu_annual - 0.5 * sigma_annual**2) * dt
    diffusion = sigma_annual * np.sqrt(dt) * z
    log_returns = drift + diffusion

    # paths shape: (runs, months+1)
    log_paths = np.cumsum(log_returns, axis=1)
    log_paths = np.concatenate([np.zeros((runs, 1)), log_paths], axis=1)
    return s0 * np.exp(log_paths)


def margin_call_probability(
    *,
    portfolio_value: float,
    loan_amount: float,
    maintenance_ltv_max: float,
    mu_annual: float,
    sigma_annual: float,
    horizon_months: int,
    runs: int = 10_000,
    seed: int | None = 42,
) -> MonteCarloResult:
    """
    Breach event: loan / portfolio_value >= maintenance_ltv_max at ANY point.
    Equivalent portfolio_value <= loan / maintenance_ltv_max.
    """
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be > 0")
    if loan_amount < 0:
        raise ValueError("loan_amount must be >= 0")
    if maintenance_ltv_max <= 0 or maintenance_ltv_max >= 1.0:
        raise ValueError("maintenance_ltv_max must be in (0, 1)")

    danger_value = loan_amount / maintenance_ltv_max if loan_amount > 0 else np.inf
    paths = gbm_paths_monthly(
        s0=portfolio_value,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
        months=horizon_months,
        runs=runs,
        seed=seed,
    )

    breached = (paths <= danger_value).any(axis=1)
    breach_count = int(breached.sum())
    prob = float(breach_count / runs)
    ending = paths[:, -1].astype(float).tolist()
    return MonteCarloResult(
        horizon_months=int(horizon_months),
        runs=int(runs),
        breach_probability=prob,
        ending_values=ending,
        breach_count=breach_count,
    )

