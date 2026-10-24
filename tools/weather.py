from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import httpx

from services.log_privacy import priv

if TYPE_CHECKING:
    from config import WeatherConfig
    from memory.unified import UnifiedMemory


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODE_RU = {
    0:  "ясно",
    1:  "малооблачно",
    2:  "облачно с прояснениями",
    3:  "пасмурно",
    45: "туман",
    48: "инейный туман",
    51: "лёгкая морось",
    53: "морось",
    55: "сильная морось",
    56: "ледяная морось",
    57: "сильная ледяная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "сильный ледяной дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    77: "снежные зёрна",
    80: "кратковременный дождь",
    81: "ливень",
    82: "сильный ливень",
    85: "небольшой снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с небольшим градом",
    99: "гроза с градом",
}

WEEKDAYS_RU = {
    "понедельник": 0, "пн": 0,
    "вторник": 1, "вт": 1,
    "среда": 2, "ср": 2, "среду": 2,
    "четверг": 3, "чт": 3,
    "пятница": 4, "пт": 4, "пятницу": 4,
    "суббота": 5, "сб": 5, "субботу": 5,
    "воскресенье": 6, "вс": 6, "воскресение": 6,
}

MONTHS_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}

DAYPART_RU = {
    "утром": "morning", "утро": "morning",
    "днём": "day", "днем": "day", "день": "day",
    "вечером": "evening", "вечер": "evening",
    "ночью": "night", "ночь": "night",
}

DAYPART_HOURS = {
    "night":   (0, 6),
    "morning": (6, 12),
    "day":     (12, 18),
    "evening": (18, 24),
}

DAYPART_LABEL_RU = {
    "morning": "утром",
    "day":     "днём",
    "evening": "вечером",
    "night":   "ночью",
}


@dataclass
class WhenSpec:
    target_date: date
    daypart: str | None = None
    is_now: bool = False


def resolve_when(when: str | None, today: date | None = None) -> WhenSpec | None:
    if today is None:
        today = date.today()
    if not when:
        return WhenSpec(target_date=today, is_now=True)

    s = when.strip().lower().replace("ё", "е")

    daypart = None
    for kw, part in DAYPART_RU.items():
        kw_e = kw.replace("ё", "е")
        if kw_e in s:
            daypart = part
            s = s.replace(kw_e, "").strip()
            break

    if not s or s in ("сейчас", "текущая", "текущую"):
        return WhenSpec(target_date=today, daypart=daypart, is_now=(daypart is None))
    if s in ("сегодня", "на сегодня"):
        return WhenSpec(target_date=today, daypart=daypart)
    if s in ("завтра", "на завтра"):
        return WhenSpec(target_date=today + timedelta(days=1), daypart=daypart)
    if s in ("послезавтра", "на послезавтра"):
        return WhenSpec(target_date=today + timedelta(days=2), daypart=daypart)
    if s in ("на выходных", "в выходные", "выходные"):
        days_ahead = (5 - today.weekday()) % 7
        return WhenSpec(target_date=today + timedelta(days=days_ahead), daypart=daypart)

    for tok in re.split(r"\s+", s):
        if tok in WEEKDAYS_RU:
            target_wd = WEEKDAYS_RU[tok]
            days_ahead = (target_wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return WhenSpec(target_date=today + timedelta(days=days_ahead), daypart=daypart)

    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        try:
            return WhenSpec(target_date=date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), daypart=daypart)
        except ValueError:
            return None

    dotted = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", s)
    if dotted:
        d, m = int(dotted.group(1)), int(dotted.group(2))
        y = int(dotted.group(3)) if dotted.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            candidate = date(y, m, d)
        except ValueError:
            return None
        if not dotted.group(3) and candidate < today:
            candidate = candidate.replace(year=y + 1)
        return WhenSpec(target_date=candidate, daypart=daypart)

    m = re.match(r"(\d{1,2})\s+([а-я]+)", s)
    if m:
        day_num = int(m.group(1))
        month_word = m.group(2)
        month = None
        for stem, num in MONTHS_RU.items():
            if month_word.startswith(stem):
                month = num
                break
        if month:
            year = today.year
            try:
                candidate = date(year, month, day_num)
            except ValueError:
                return None
            if candidate < today:
                candidate = candidate.replace(year=year + 1)
            return WhenSpec(target_date=candidate, daypart=daypart)

    return None


from tools import location as _location


_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}


def fetch_forecast(lat: float, lon: float, config: "WeatherConfig") -> dict:
    key = (round(lat, 3), round(lon, 3))
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < config.cache_ttl_seconds:
        return cached[1]

    forecast_days = max(1, min(16, config.forecast_days + 1))
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,weathercode,wind_speed_10m,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max,wind_speed_10m_max",
        "hourly": "temperature_2m,apparent_temperature,weathercode",
        "forecast_days": forecast_days,
        "timezone": "auto",
        "wind_speed_unit": "ms",
    }
    response = httpx.get(OPEN_METEO_URL, params=params, timeout=10.0)
    response.raise_for_status()
    data = response.json()
    _CACHE[key] = (now, data)
    return data


def _fmt_temp(value) -> str:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    sign = "+" if n > 0 else ("" if n == 0 else "−")
    return f"{sign}{abs(n)}°"


def _cond_ru(code) -> str:
    try:
        return WMO_CODE_RU.get(int(code), f"код погоды {code}")
    except (TypeError, ValueError):
        return "неизвестно"


def _dominant_code(codes: list) -> int | None:
    codes = [c for c in codes if c is not None]
    if not codes:
        return None
    counts: dict[int, int] = {}
    for c in codes:
        counts[c] = counts.get(c, 0) + 1
    max_count = max(counts.values())
    return max(c for c, n in counts.items() if n == max_count)


def _date_phrase(d: date) -> str:
    today = date.today()
    delta = (d - today).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == 2:
        return "послезавтра"
    wd = ["в понедельник", "во вторник", "в среду", "в четверг",
          "в пятницу", "в субботу", "в воскресенье"][d.weekday()]
    if 0 < delta <= 7:
        return wd
    return f"{d.day}.{d.month:02d}"


def _slice_hourly(hourly: dict, target: date, start_hour: int, end_hour: int) -> dict:
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    feels = hourly.get("apparent_temperature", [])
    codes = hourly.get("weathercode", [])
    target_prefix = target.isoformat()
    out_t, out_f, out_c = [], [], []
    for i, t in enumerate(times):
        if not t.startswith(target_prefix):
            continue
        try:
            hour = int(t[11:13])
        except (ValueError, IndexError):
            continue
        if start_hour <= hour < end_hour:
            if i < len(temps):
                out_t.append(temps[i])
            if i < len(feels):
                out_f.append(feels[i])
            if i < len(codes):
                out_c.append(codes[i])
    return {"temp": out_t, "feels": out_f, "code": out_c}


def _avg(values) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _format_now(current: dict, city: str) -> str:
    temp = _fmt_temp(current.get("temperature_2m"))
    feels = _fmt_temp(current.get("apparent_temperature"))
    cond = _cond_ru(current.get("weathercode"))
    wind = current.get("wind_speed_10m")
    parts = [f"{city}, сейчас: {cond}, {temp}"]
    if feels != temp and feels != "—":
        parts.append(f"ощущается как {feels}")
    if wind is not None:
        try:
            parts.append(f"ветер {round(float(wind))} м/с")
        except (TypeError, ValueError):
            pass
    return ", ".join(parts) + "."


def _format_day(daily: dict, hourly: dict, target: date, city: str) -> str:
    times = daily.get("time", [])
    iso = target.isoformat()
    if iso not in times:
        return f"Прогноза на {iso} нет в ответе сервиса."
    idx = times.index(iso)

    t_max = _fmt_temp(_pick(daily.get("temperature_2m_max"), idx))
    t_min = _fmt_temp(_pick(daily.get("temperature_2m_min"), idx))
    cond = _cond_ru(_pick(daily.get("weathercode"), idx))
    precip = _pick(daily.get("precipitation_probability_max"), idx)

    out = f"{city}, {_date_phrase(target)}: {cond}, от {t_min} до {t_max}"
    try:
        if precip is not None and int(precip) >= 40:
            out += f", вероятность осадков {int(precip)}%"
    except (TypeError, ValueError):
        pass
    return out + "."


def _format_daypart(hourly: dict, target: date, daypart: str, city: str) -> str:
    start, end = DAYPART_HOURS[daypart]
    sl = _slice_hourly(hourly, target, start, end)
    if not sl["temp"]:
        return f"Почасовых данных на {_date_phrase(target)} {DAYPART_LABEL_RU[daypart]} нет."
    avg_t = _fmt_temp(_avg(sl["temp"]))
    avg_f = _fmt_temp(_avg(sl["feels"]))
    cond = _cond_ru(_dominant_code(sl["code"]))
    out = f"{city}, {_date_phrase(target)} {DAYPART_LABEL_RU[daypart]}: {cond}, {avg_t}"
    if avg_f != avg_t and avg_f != "—":
        out += f", ощущается как {avg_f}"
    return out + "."


def _pick(arr, idx):
    if arr is None or idx is None:
        return None
    try:
        return arr[idx]
    except (IndexError, TypeError):
        return None


def get_weather(
    when: str | None,
    memory: "UnifiedMemory | None",
    config: "WeatherConfig",
    city: str | None = None,
    debug: bool = False,
) -> str:
    if not config.enabled:
        return "Инструмент погоды выключен в настройках."

    spec = resolve_when(when)
    if spec is None:
        return f"Не разобрала «{when}». Уточни — сегодня, завтра, день недели или дата."

    horizon = (spec.target_date - date.today()).days
    if horizon > config.forecast_days:
        return f"Прогноз дальше чем на {config.forecast_days} дней я получить не могу, Господин."
    if horizon < 0:
        return "Я не умею смотреть погоду в прошлом."

    loc_city: str
    lat: float
    lon: float
    source: str
    if city and city.strip():
        try:
            geocoded = _location.geocode(city.strip())
        except _location.GeocodeError as e:
            if e.kind == "not_found":
                return f"Не нашла «{city}» на карте. Уточни название города."
            if e.kind == "network":
                return "Не удалось связаться с сервисом геокодинга — проверьте интернет."
            return f"Не получилось распознать город: {e.message}"
        loc_city, lat, lon = geocoded.city, geocoded.lat, geocoded.lon
        source = "argument"
    else:
        saved = _location.get_saved_location(memory)
        if not saved:
            return (
                "Не знаю твоего города — в профиле нет местоположения. "
                "Если хочешь, чтобы я запомнила, где ты живёшь, вызови set_location "
                "(например, set_location(city='Москва')). "
                "Или укажи город для разового запроса: get_weather(when=..., city='...')."
            )
        loc_city = saved.get("city") or "твоём городе"
        lat = float(saved["lat"])
        lon = float(saved["lon"])
        source = "profile"

    if debug:
        print(f"[WEATHER] location: {priv(loc_city)} "
              f"({priv(f'{lat:.3f},{lon:.3f}')}) source={source}")

    try:
        data = fetch_forecast(lat, lon, config)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 429:
            return "Сервис погоды временно ограничил запросы — попробуй через минуту."
        return f"Сервис погоды вернул ошибку {code}."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Не удалось дозвониться до сервиса погоды — проверьте интернет."
    except Exception as e:
        return f"Не получилось узнать погоду: {e}"

    if spec.is_now:
        current = data.get("current", {})
        return _format_now(current, loc_city)

    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    if spec.daypart:
        return _format_daypart(hourly, spec.target_date, spec.daypart, loc_city)

    return _format_day(daily, hourly, spec.target_date, loc_city)
