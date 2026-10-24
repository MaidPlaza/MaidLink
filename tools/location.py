from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from memory.unified import UnifiedMemory


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass
class GeocodeResult:
    city: str
    country: str
    lat: float
    lon: float
    timezone: str | None = None
    admin1: str | None = None
    source: str = "open-meteo-geocoding"

    def to_profile_dict(self) -> dict:
        out = {
            "city": self.city,
            "country": self.country,
            "lat": self.lat,
            "lon": self.lon,
            "source": self.source,
            "updated_at": time.time(),
        }
        if self.timezone:
            out["timezone"] = self.timezone
        if self.admin1:
            out["admin1"] = self.admin1
        return out


_GEOCODE_CACHE: dict[str, tuple[float, GeocodeResult | None]] = {}
_GEOCODE_TTL = 24 * 3600


class GeocodeError(Exception):
    kind: str = "generic"

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def geocode(query: str) -> GeocodeResult:
    key = query.strip().lower()
    if not key:
        raise GeocodeError("empty", "Пустой запрос города.")

    cached = _GEOCODE_CACHE.get(key)
    if cached and (time.time() - cached[0]) < _GEOCODE_TTL and cached[1] is not None:
        return cached[1]

    try:
        response = httpx.get(
            GEOCODING_URL,
            params={"name": query, "count": 1, "language": "ru", "format": "json"},
            timeout=8.0,
        )
        response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise GeocodeError("network", "Не удалось связаться с сервисом геокодинга.") from e
    except httpx.HTTPStatusError as e:
        raise GeocodeError("http", f"Сервис геокодинга вернул {e.response.status_code}.") from e

    data = response.json() or {}
    results = data.get("results") or []
    if not results:
        raise GeocodeError("not_found", f"Не нашла «{query}» на карте.")

    top = results[0]
    try:
        result = GeocodeResult(
            city=top.get("name") or query,
            country=top.get("country") or "",
            lat=float(top["latitude"]),
            lon=float(top["longitude"]),
            timezone=top.get("timezone"),
            admin1=top.get("admin1"),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise GeocodeError("bad_response", "Сервис вернул неожиданный ответ.") from e

    _GEOCODE_CACHE[key] = (time.time(), result)
    return result


def get_saved_location(memory: "UnifiedMemory | None") -> dict | None:
    if memory is None:
        return None
    profile = memory.get_user_profile()
    loc = profile.get("location")
    if not isinstance(loc, dict):
        return None
    if "lat" not in loc or "lon" not in loc:
        return None
    return loc


def save_location(memory: "UnifiedMemory", query: str) -> dict:
    result = geocode(query)
    payload = result.to_profile_dict()
    memory.update_user_profile("location", payload)
    return payload
