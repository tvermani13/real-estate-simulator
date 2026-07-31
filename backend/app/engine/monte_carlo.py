from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonteCarloResult:
    horizon_months: int
    runs: int
    breach_probability: float
    ending_value_sample: list[float]
    ending_value_percentiles: dict[str, float]
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
    distribution_sample_size: int = 512,
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

    if distribution_sample_size <= 0:
        raise ValueError("distribution_sample_size must be > 0")

    danger_value = loan_amount / maintenance_ltv_max if loan_amount > 0 else 0.0
    paths = gbm_paths_monthly(
        s0=portfolio_value,
        mu_annual=mu_annual,
        sigma_annual=sigma_annual,
        months=horizon_months,
        runs=runs,
        seed=seed,
    )

    breached = (
        (paths <= danger_value).any(axis=1)
        if loan_amount > 0
        else np.zeros(runs, dtype=bool)
    )
    breach_count = int(breached.sum())
    prob = float(breach_count / runs)
    ending = paths[:, -1].astype(float)
    sorted_ending = np.sort(ending)
    sample_count = min(distribution_sample_size, runs)
    sample_indices = np.linspace(0, runs - 1, num=sample_count, dtype=int)
    sample = sorted_ending[sample_indices].tolist()
    quantiles = np.quantile(ending, [0.05, 0.25, 0.5, 0.75, 0.95])
    return MonteCarloResult(
        horizon_months=int(horizon_months),
        runs=int(runs),
        breach_probability=prob,
        ending_value_sample=sample,
        ending_value_percentiles={
            "p05": float(quantiles[0]),
            "p25": float(quantiles[1]),
            "p50": float(quantiles[2]),
            "p75": float(quantiles[3]),
            "p95": float(quantiles[4]),
        },
        breach_count=breach_count,
    )
