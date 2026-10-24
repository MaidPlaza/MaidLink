from __future__ import annotations

from services.log_privacy import priv
from tools.registry import ToolContext


def handle_get_weather(args: dict, ctx: ToolContext) -> str:
    from tools.weather import get_weather as _fetch_weather

    cfg = ctx.weather_config
    if cfg is None:
        from config import WeatherConfig
        cfg = WeatherConfig()
    when = (args.get("when") or "").strip()
    city = (args.get("city") or "").strip() or None
    if ctx.debug:
        print(f"[MEM] get_weather(when={when!r}, city=«{priv(city or '')}»)")
    return _fetch_weather(
        when,
        memory=ctx.memory,
        config=cfg,
        city=city,
        debug=ctx.debug,
    )


def handle_set_location(args: dict, ctx: ToolContext) -> str:
    from tools.location import save_location, GeocodeError

    if ctx.memory is None:
        return "Память недоступна, нечего сохранять."
    city = (args.get("city") or "").strip()
    if not city:
        return "Нужно название города — параметр city пустой."
    if ctx.debug:
        print(f"[MEM] set_location(city=«{priv(city)}»)")
    try:
        saved = save_location(ctx.memory, city)
    except GeocodeError as e:
        if e.kind == "not_found":
            return f"Не нашла «{city}» на карте. Проверь название."
        if e.kind == "network":
            return "Не удалось связаться с сервисом геокодинга — проверьте интернет."
        return f"Не получилось сохранить: {e.message}"
    loc_label = saved["city"]
    if saved.get("country"):
        loc_label += f", {saved['country']}"
    return f"Запомнила: {loc_label}. Теперь знаю где ты живёшь."
