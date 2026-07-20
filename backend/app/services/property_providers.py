from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.routes.product_models import PropertyListing, SearchCriteria


class PropertyProviderError(RuntimeError):
    pass


class PropertyProvider(ABC):
    name: str
    mode: str

    @abstractmethod
    async def sale_listings(self, criteria: SearchCriteria) -> list[PropertyListing]:
        raise NotImplementedError


@dataclass(frozen=True)
class MarketPreset:
    aliases: tuple[str, ...]
    latitude: float
    longitude: float
    radius_miles: float
    county: str
    state: str


MARKET_PRESETS = (
    MarketPreset(
        aliases=("fairfield county, ct", "fairfield county ct", "fairfield, ct county"),
        latitude=41.2560,
        longitude=-73.3709,
        radius_miles=32,
        county="Fairfield",
        state="CT",
    ),
)


def _normalized_location(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _market_preset(location: str) -> MarketPreset | None:
    normalized = _normalized_location(location)
    return next(
        (preset for preset in MARKET_PRESETS if normalized in preset.aliases),
        None,
    )


def _location_parts(location: str) -> tuple[str, str, str | None]:
    clean = location.strip()
    if clean.isdigit() and len(clean) == 5:
        return "Sample market", "", clean
    pieces = [part.strip() for part in clean.split(",") if part.strip()]
    if len(pieces) >= 2 and len(pieces[-1]) == 2:
        return ", ".join(pieces[:-1]), pieces[-1].upper(), None
    return clean, "", None


def _looks_like_street_address(location: str) -> bool:
    first_segment = location.split(",", 1)[0].strip()
    return any(character.isdigit() for character in first_segment)


@dataclass(frozen=True)
class DemoTemplate:
    street: str
    price_ratio: float
    bedrooms: float
    bathrooms: float
    square_feet: float
    property_type: str
    year_built: int
    hoa: float
    days_on_market: int
    rent_ratio: float


DEMO_TEMPLATES = [
    DemoTemplate("18 Sample Maple Lane", 0.68, 3, 2, 1680, "Single Family", 1998, 0, 12, 0.0082),
    DemoTemplate("204 Sample Juniper Street", 0.78, 4, 2.5, 2190, "Single Family", 2006, 45, 24, 0.0077),
    DemoTemplate("77 Sample Market Way", 0.86, 3, 2, 1840, "Townhouse", 2017, 185, 8, 0.0072),
    DemoTemplate("310 Sample Park Avenue", 0.94, 4, 3, 2610, "Single Family", 2011, 70, 39, 0.0068),
    DemoTemplate("9 Sample River Court", 1.04, 5, 3.5, 3180, "Single Family", 2021, 95, 6, 0.0063),
    DemoTemplate("142 Sample Oak Terrace", 0.59, 2, 2, 1240, "Condo", 2003, 315, 51, 0.0088),
    DemoTemplate("51 Sample Cedar Drive", 0.73, 3, 2, 1575, "Single Family", 1987, 0, 67, 0.0085),
    DemoTemplate("88 Sample Harbor Place", 0.89, 3, 2.5, 2020, "Townhouse", 2019, 225, 18, 0.0071),
]


class DemoPropertyProvider(PropertyProvider):
    name = "demo"
    mode = "demo"

    async def sale_listings(self, criteria: SearchCriteria) -> list[PropertyListing]:
        city, state, zip_code = _location_parts(criteria.location)
        anchor = criteria.max_price or 600_000
        anchor = max(anchor, criteria.min_price or 0, 150_000)
        listings: list[PropertyListing] = []
        for index, item in enumerate(DEMO_TEMPLATES, start=1):
            price = round(anchor * item.price_ratio / 1000) * 1000
            if criteria.min_price is not None and price < criteria.min_price:
                continue
            if criteria.max_price is not None and price > criteria.max_price * 1.12:
                continue
            if item.bedrooms < criteria.min_bedrooms or item.bathrooms < criteria.min_bathrooms:
                continue
            if criteria.property_types and item.property_type not in criteria.property_types:
                continue
            if criteria.max_days_on_market and item.days_on_market > criteria.max_days_on_market:
                continue
            listings.append(
                PropertyListing(
                    id=f"demo-{index}-{city.lower().replace(' ', '-')}-{state.lower()}",
                    provider=self.name,
                    address=f"{item.street}, {criteria.location}",
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    price=price,
                    bedrooms=item.bedrooms,
                    bathrooms=item.bathrooms,
                    square_feet=item.square_feet,
                    property_type=item.property_type,
                    year_built=item.year_built,
                    hoa_monthly=item.hoa,
                    days_on_market=item.days_on_market,
                    estimated_rent=round(price * item.rent_ratio / 50) * 50,
                    rent_estimate_source="illustrative demo assumption",
                )
            )
        return listings


class RentCastPropertyProvider(PropertyProvider):
    name = "rentcast"
    mode = "live"
    base_url = "https://api.rentcast.io/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _query_params(self, criteria: SearchCriteria, *, rental: bool = False) -> dict[str, Any]:
        city, state, zip_code = _location_parts(criteria.location)
        preset = _market_preset(criteria.location)
        result_multiplier = 4 if preset else 3 if rental else 1
        params: dict[str, Any] = {
            "status": "Active",
            "limit": min(settings.scanner_result_limit * result_multiplier, 100),
            "bedrooms": f"{criteria.min_bedrooms:g}:*",
            "bathrooms": f"{criteria.min_bathrooms:g}:*",
        }
        if preset:
            params.update(
                {
                    "latitude": preset.latitude,
                    "longitude": preset.longitude,
                    "radius": preset.radius_miles,
                }
            )
        elif zip_code:
            params["zipCode"] = zip_code
        elif _looks_like_street_address(criteria.location):
            params["address"] = criteria.location
            params["radius"] = criteria.radius_miles
        elif state:
            params.update({"city": city, "state": state})
        else:
            params["address"] = criteria.location
            params["radius"] = criteria.radius_miles
        if criteria.property_types:
            params["propertyType"] = ",".join(criteria.property_types)
        if not rental:
            low = "*" if criteria.min_price is None else f"{criteria.min_price:g}"
            high = "*" if criteria.max_price is None else f"{criteria.max_price:g}"
            params["price"] = f"{low}:{high}"
        if criteria.max_days_on_market:
            params["daysOld"] = f"*:{criteria.max_days_on_market}"
        return params

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={"Accept": "application/json", "X-Api-Key": self.api_key},
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise PropertyProviderError("RentCast returned an unexpected response")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise PropertyProviderError(f"RentCast request failed: {exc}") from exc

    @staticmethod
    def _rent_medians(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, int], float], float | None]:
        buckets: dict[tuple[str, int], list[float]] = defaultdict(list)
        all_rents: list[float] = []
        for row in rows:
            rent = row.get("price")
            if not isinstance(rent, (int, float)) or rent <= 0:
                continue
            key = (str(row.get("propertyType") or ""), round(float(row.get("bedrooms") or 0)))
            buckets[key].append(float(rent))
            all_rents.append(float(rent))
        return ({key: statistics.median(values) for key, values in buckets.items()}, statistics.median(all_rents) if all_rents else None)

    @staticmethod
    def _filter_market_rows(
        rows: list[dict[str, Any]], preset: MarketPreset | None
    ) -> list[dict[str, Any]]:
        if preset is None:
            return rows

        def normalized_county(row: dict[str, Any]) -> str:
            county = str(row.get("county") or "").strip().lower()
            return county.removesuffix(" county")

        return [
            row
            for row in rows
            if normalized_county(row) == preset.county.lower()
            and str(row.get("state") or "").strip().upper() == preset.state
        ]

    async def sale_listings(self, criteria: SearchCriteria) -> list[PropertyListing]:
        preset = _market_preset(criteria.location)
        sale_rows = self._filter_market_rows(
            await self._get("/listings/sale", self._query_params(criteria)), preset
        )
        rent_rows: list[dict[str, Any]] = []
        if criteria.purpose == "investment":
            rent_rows = self._filter_market_rows(
                await self._get(
                    "/listings/rental/long-term", self._query_params(criteria, rental=True)
                ),
                preset,
            )
        medians, fallback_rent = self._rent_medians(rent_rows)
        listings: list[PropertyListing] = []
        for row in sale_rows:
            try:
                property_type = str(row.get("propertyType") or "Unknown")
                bedrooms = float(row.get("bedrooms") or 0)
                rent = medians.get((property_type, round(bedrooms)), fallback_rent)
                hoa = row.get("hoa") if isinstance(row.get("hoa"), dict) else {}
                listings.append(
                    PropertyListing(
                        id=str(row["id"]),
                        provider=self.name,
                        address=str(row.get("formattedAddress") or row["id"]),
                        city=str(row.get("city") or ""),
                        state=str(row.get("state") or ""),
                        zip_code=str(row.get("zipCode")) if row.get("zipCode") else None,
                        price=float(row["price"]),
                        bedrooms=bedrooms,
                        bathrooms=float(row.get("bathrooms") or 0),
                        square_feet=float(row["squareFootage"]) if row.get("squareFootage") else None,
                        property_type=property_type,
                        year_built=int(row["yearBuilt"]) if row.get("yearBuilt") else None,
                        hoa_monthly=float(hoa.get("fee") or 0),
                        days_on_market=int(row["daysOnMarket"]) if row.get("daysOnMarket") is not None else None,
                        listed_date=row.get("listedDate"),
                        latitude=float(row["latitude"]) if row.get("latitude") is not None else None,
                        longitude=float(row["longitude"]) if row.get("longitude") is not None else None,
                        estimated_rent=rent,
                        rent_estimate_source="local rental listing median" if rent else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return listings[: settings.scanner_result_limit]


def get_property_provider() -> PropertyProvider:
    if settings.property_provider.lower() == "rentcast" and settings.rentcast_api_key:
        return RentCastPropertyProvider(settings.rentcast_api_key)
    return DemoPropertyProvider()
