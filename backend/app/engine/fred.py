from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class FredSeriesLatest:
    series_id: str
    date: str | None
    value: float | None


async def fetch_latest_observation(
    *,
    api_key: str,
    series_id: str,
    timeout_s: float = 10.0,
) -> FredSeriesLatest:
    """
    Fetch latest observation from FRED series.
    Returns `value=None` if data missing/unparseable.
    """
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "api_key": api_key,
        "file_type": "json",
        "series_id": series_id,
        "sort_order": "desc",
        "limit": 1,
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    obs = (data.get("observations") or [])
    if not obs:
        return FredSeriesLatest(series_id=series_id, date=None, value=None)

    latest = obs[0]
    date = latest.get("date")
    raw = latest.get("value")
    try:
        value = float(raw)
    except Exception:
        value = None
    return FredSeriesLatest(series_id=series_id, date=date, value=value)

