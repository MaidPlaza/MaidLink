from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from persona.evolution import ALL_TIER_NAMES
from app_paths import content_base

_CATALOG_DIR = content_base() / "scenario_catalog"
_LEGACY_DIR = content_base() / "scene_catalog"

SURFACES = ("entry", "proactive")
LEVELS = ("background", "circumstance", "event")
DEFAULT_LEVEL = "circumstance"

TRAITS: dict[str, str] = {
    "заботливая": "следит за его самочувствием и режимом",
    "ласковая": "открыто показывает привязанность",
    "прячет_чувства": "тепло под колкостью или холодом",
    "озорная": "дразнит, расшевеливает",
    "соперница": "вызовы, споры, «слабо?»",
    "затейница": "идеи и затеи",
    "сочиняет": "истории, строчки, легенды",
    "загадочная": "загадки, игры ума",
    "гордая": "хочет, чтобы заметили её дело",
    "сдержанная": "тихое присутствие без требований",
    "обидчивая": "дуется, но всё же пишет",
    "откровенная": "делится уязвимым о себе",
}

LEVEL_HEADERS = {
    "background": "Обстоятельства сейчас:",
    "circumstance": "Ситуация:",
    "event": "Сейчас происходит:",
}

_NOT_A_TASK = ("Это обстоятельства, а не поручение: веди разговор так, как он "
               "складывается, — {honorific} может увести его куда угодно.")
_MAY_END_HINT = ("Если сценарий естественно исчерпал себя — можешь вызвать "
                 "scenario_end; это не обязательно.")

MARKER = "scenario"


def _tier_idx(tier: str) -> int:
    try:
        return ALL_TIER_NAMES.index(tier)
    except ValueError:
        return -1


def tier_ge(cur: str, need: str) -> bool:
    return _tier_idx(cur) >= _tier_idx(need)


def _norm_text(v) -> "str | dict":
    if isinstance(v, dict):
        return {str(k): str(x).strip() for k, x in v.items()}
    return str(v or "").strip()


def resolve_text(v, backend: str = "") -> str:
    if isinstance(v, dict):
        return (v.get(backend) or v.get("default") or "").strip()
    return (v or "").strip()


def fill(text: str, *, name: str = "", honorific: str = "", gender: str = "female") -> str:
    if not text:
        return ""
    from persona.gender import fill_forms
    male = (gender or "").strip().lower() == "male"
    text = (text.replace("{name}", name or ("он" if male else "она"))
                .replace("{honorific}", honorific or "Господин"))
    return fill_forms(text, "male" if male else "female")


@dataclass
class Phase:
    text: "str | dict" = ""
    until_turn: int | None = None

    @classmethod
    def from_raw(cls, raw) -> "Phase":
        if isinstance(raw, dict):
            ut = raw.get("until_turn")
            return cls(text=_norm_text(raw.get("text", "")),
                       until_turn=int(ut) if ut is not None else None)
        return cls(text=_norm_text(raw))

    def text_for(self, backend: str = "") -> str:
        return resolve_text(self.text, backend)


def _parse_until(raw) -> object:
    if isinstance(raw, dict):
        if raw.get("turns") is not None:
            return {"turns": max(1, int(raw["turns"]))}
        if raw.get("seconds") is not None:
            return {"seconds": max(1.0, float(raw["seconds"]))}
        return "session_end"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return {"turns": max(1, int(raw))}
    return "session_end"


@dataclass
class Scenario:
    id: str
    title: str = ""
    surface: str = "entry"
    level: str = DEFAULT_LEVEL
    conditions: dict = field(default_factory=dict)
    trigger: object = "guaranteed"
    once: bool = False
    cooldown: float = 0.0
    priority: int = 0
    requires: dict = field(default_factory=dict)
    fits: dict = field(default_factory=dict)
    weight: float = 1.0
    initiate: bool = False
    outfit: str = ""
    note: "str | dict" = ""
    action: str = ""
    params: dict = field(default_factory=dict)
    memory_start: str = ""
    presence: list = field(default_factory=list)
    until: object = None
    model_may_end: bool = False
    memory_end: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        opening = d.get("opening") or {}
        if not isinstance(opening, dict):
            opening = {}
        end = d.get("end")
        if not isinstance(end, dict):
            end = {}
        presence = [Phase.from_raw(p) for p in (d.get("presence") or []) if p]
        until_raw = end.get("until")
        if until_raw is None:
            until_raw = "session_end" if presence else {"turns": 1}
        level = str(d.get("level") or DEFAULT_LEVEL)
        if level not in LEVELS:
            level = DEFAULT_LEVEL
        requires = d.get("requires") or {}
        fits = d.get("fits") or {}
        if not isinstance(fits, dict):
            fits = {}
        fits = {"traits": [str(t).strip() for t in (fits.get("traits") or []) if str(t).strip()],
                "quirks": [str(q).strip() for q in (fits.get("quirks") or []) if str(q).strip()],
                "axes": dict(fits.get("axes") or {})}
        unknown = [t for t in fits["traits"] if t not in TRAITS]
        if unknown:
            print(f"[scenarios] {d.get('id')}: черты вне словаря {unknown} — "
                  f"ни один персонаж их не знает")
        return cls(
            id=str(d["id"]),
            title=str(d.get("title") or "").strip(),
            surface=str(d.get("surface", "entry")),
            level=level,
            conditions=dict(d.get("conditions") or {}),
            trigger=d.get("trigger", "guaranteed"),
            once=bool(d.get("once", False)),
            cooldown=float(d.get("cooldown", 0.0) or 0.0),
            priority=int(d.get("priority", 0)),
            requires=dict(requires) if isinstance(requires, dict) else {},
            fits=fits if (fits["traits"] or fits["quirks"] or fits["axes"]) else {},
            weight=max(0.0, float(d.get("weight", 1.0) or 0.0)),
            initiate=bool(opening.get("initiate", d.get("initiate", False))),
            outfit=str(opening.get("outfit") or "").strip(),
            note=_norm_text(opening.get("note", d.get("prompt_note", ""))),
            action=str(opening.get("action") or d.get("action") or ""),
            params=dict(opening.get("params") or d.get("params") or {}),
            memory_start=str(opening.get("memory") or "").strip(),
            presence=presence,
            until=_parse_until(until_raw),
            model_may_end=bool(end.get("model_may_end", False)),
            memory_end=str(end.get("memory") or "").strip(),
        )

    @property
    def display_title(self) -> str:
        return self.title or self.id

    def note_for(self, backend: str = "") -> str:
        return resolve_text(self.note, backend)

    @property
    def prompt_note(self) -> "str | dict":
        return self.note

    def prompt_for(self, backend: str = "") -> str:
        return self.note_for(backend)

    def presence_for(self, turn: int, backend: str = "") -> str:
        for ph in self.presence:
            if ph.until_turn is None or turn <= ph.until_turn:
                return ph.text_for(backend)
        return ""

    def turn_limit(self) -> int | None:
        return self.until.get("turns") if isinstance(self.until, dict) else None

    def seconds_limit(self) -> float | None:
        return self.until.get("seconds") if isinstance(self.until, dict) else None

    def is_over(self, next_turn: int, elapsed_sec: float) -> bool:
        tl = self.turn_limit()
        if tl is not None and next_turn > tl:
            return True
        sl = self.seconds_limit()
        if sl is not None and elapsed_sec >= sl:
            return True
        return False


def render_block(sc: Scenario, turn: int, *, backend: str = "", honorific: str = "",
                 name: str = "", opening: bool | None = None,
                 gender: str = "female") -> str:
    if opening is None:
        opening = turn <= 1
    if opening:
        body = sc.note_for(backend) or sc.presence_for(max(1, turn), backend)
    else:
        body = sc.presence_for(turn, backend)
    body = fill(body, name=name, honorific=honorific, gender=gender)
    if not body:
        return ""
    header = LEVEL_HEADERS.get(sc.level, LEVEL_HEADERS[DEFAULT_LEVEL])
    lines = [f"{header}\n{body}"]
    if sc.turn_limit() != 1:
        lines.append(fill(_NOT_A_TASK, name=name, honorific=honorific, gender=gender))
    if sc.model_may_end and not opening and turn >= 2:
        lines.append(_MAY_END_HINT)
    return "\n".join(lines)


def start_marker_text(sc: Scenario, *, name: str = "", honorific: str = "",
                      gender: str = "female") -> str:
    body = fill(sc.memory_start, name=name, honorific=honorific, gender=gender)
    return (f"(Сценарий «{sc.display_title}» начался: {body})" if body
            else f"(Сценарий «{sc.display_title}» начался.)")


def end_marker_text(sc: Scenario, *, name: str = "", honorific: str = "",
                    gender: str = "female") -> str:
    body = fill(sc.memory_end, name=name, honorific=honorific, gender=gender)
    return (f"(Сценарий «{sc.display_title}» завершён: {body})" if body
            else f"(Сценарий «{sc.display_title}» завершён.)")


@dataclass
class ScenarioContext:
    tier: str = "distant"
    relationship_level: float = 0.0
    session_count: int = 0
    first_ever: bool = False
    idle_gap_sec: float = 0.0
    time_of_day: str = ""
    mood_state: str = ""
    axis_values: dict = field(default_factory=dict)
    now: float = 0.0
    event_log: dict = field(default_factory=dict)
    today_md: str = ""
    anniversaries: dict = field(default_factory=dict)
    chance_scale: float = 1.0
    pair: str = ""
    outfits: dict = field(default_factory=dict)
    traits: frozenset = frozenset()
    quirks: frozenset = frozenset()
    rating: str = "sfw"
    contact_gap_sec: float | None = None


def parse_scenarios(entries) -> list[Scenario]:
    out: list[Scenario] = []
    for e in (entries or []):
        try:
            out.append(Scenario.from_dict(e))
        except Exception as ex:
            print(f"[scenarios] пропущен сценарий {e!r}: {ex}")
    return out


def _load_file(path: Path) -> list[Scenario]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"[scenarios] не загрузить {Path(path).name}: {type(e).__name__}: {e}")
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("scenarios")
    if entries is None:
        entries = data.get("scenes")
    return parse_scenarios(entries)


def _pack_files(p: Path) -> list[Path]:
    return sorted(p.glob("*.yaml"), key=lambda f: (f.name != "core.yaml", f.name))


def load_catalog(path: "Path | None" = None) -> list[Scenario]:
    if path is not None:
        p = Path(path)
        if not p.is_dir():
            return _load_file(p)
        files = _pack_files(p)
    else:
        files = _pack_files(_CATALOG_DIR) if _CATALOG_DIR.is_dir() else []
        if _LEGACY_DIR.is_dir():
            files += _pack_files(_LEGACY_DIR)
        try:
            from app_paths import PROJECT_ROOT
            from services import addons as _addons
            for key in ("scenario_catalog", "scene_catalog"):
                for ad in _addons.content_dirs(PROJECT_ROOT, key):
                    files += sorted(ad.glob("*.yaml"))
        except Exception:
            pass
    by_id: dict[str, Scenario] = {}
    order: list[str] = []
    for f in files:
        for s in _load_file(f):
            if s.id not in by_id:
                order.append(s.id)
            by_id[s.id] = s
    return [by_id[i] for i in order]


load_scenes = load_catalog


def merge_catalog(shared: list[Scenario], *, disable=None, custom=None) -> list[Scenario]:
    disabled = set(disable or [])
    custom = list(custom or [])
    custom_ids = {e.id for e in custom}
    out = [e for e in shared if e.id not in disabled and e.id not in custom_ids]
    out.extend(custom)
    return out


def _conditions_met(cond: dict, ctx: ScenarioContext) -> bool:
    if "first_ever" in cond and bool(cond["first_ever"]) != ctx.first_ever:
        return False
    if "pair" in cond:
        from persona.gender import pair_allows
        if not ctx.pair or not pair_allows(cond["pair"], ctx.pair):
            return False
    if "tier_ge" in cond and not tier_ge(ctx.tier, str(cond["tier_ge"])):
        return False
    if "tier_eq" in cond and ctx.tier != str(cond["tier_eq"]):
        return False
    if "session_count_ge" in cond and ctx.session_count < int(cond["session_count_ge"]):
        return False
    if "session_count_eq" in cond and ctx.session_count != int(cond["session_count_eq"]):
        return False
    if "idle_gap_ge" in cond and ctx.idle_gap_sec < float(cond["idle_gap_ge"]):
        return False
    if "time_of_day" in cond and ctx.time_of_day not in cond["time_of_day"]:
        return False
    if "mood_eq" in cond and ctx.mood_state != str(cond["mood_eq"]):
        return False
    if "mood_in" in cond and ctx.mood_state not in [str(m) for m in (cond["mood_in"] or [])]:
        return False
    if "rating_ge" in cond and _rating_idx(ctx.rating) < _rating_idx(str(cond["rating_ge"])):
        return False
    if "date_eq" in cond and (not ctx.today_md or ctx.today_md != str(cond["date_eq"])):
        return False
    if "anniversary_of" in cond:
        md = ctx.anniversaries.get(str(cond["anniversary_of"]))
        if not md or not ctx.today_md or ctx.today_md != md:
            return False
    if "axis_range" in cond and not _axes_in_range(cond["axis_range"], ctx.axis_values):
        return False
    return True


RATINGS = ("sfw", "suggestive", "nsfw")


def _rating_idx(r: str) -> int:
    try:
        return RATINGS.index((r or "sfw").strip().lower())
    except ValueError:
        return len(RATINGS)


def _axes_in_range(axes: dict, values: dict) -> bool:
    for axis, rng in (axes or {}).items():
        v = values.get(axis)
        if v is None:
            return False
        rng = rng or {}
        lo, hi = rng.get("min"), rng.get("max")
        if lo is not None and v < float(lo):
            return False
        if hi is not None and v > float(hi):
            return False
    return True


def fits_character(sc: Scenario, ctx: ScenarioContext) -> bool:
    if not sc.fits:
        return True
    want_t = sc.fits.get("traits") or []
    want_q = sc.fits.get("quirks") or []
    if want_t or want_q:
        if not ((set(want_t) & set(ctx.traits or ()))
                or (set(want_q) & set(ctx.quirks or ()))):
            return False
    return _axes_in_range(sc.fits.get("axes") or {}, ctx.axis_values)


def _requires_met(sc: Scenario, ctx: ScenarioContext) -> bool:
    want = sc.requires.get("outfit_prepared") if sc.requires else None
    if want:
        if not ctx.outfits or str(want) not in ctx.outfits:
            return False
    return True


def _fire_ok(sc: Scenario, ctx: ScenarioContext) -> bool:
    log = ctx.event_log.get(sc.id) or {}
    if sc.once and int(log.get("count", 0)) > 0:
        return False
    if sc.cooldown and (ctx.now - float(log.get("last_fired_at", 0.0))) < sc.cooldown:
        return False
    return True


def eligible(sc: Scenario, ctx: ScenarioContext) -> bool:
    return (fits_character(sc, ctx) and _conditions_met(sc.conditions, ctx)
            and _requires_met(sc, ctx) and _fire_ok(sc, ctx))


def _chance(sc: Scenario) -> float:
    if isinstance(sc.trigger, dict):
        return max(0.0, min(1.0, float(sc.trigger.get("chance", 1.0))))
    return 1.0


INITIATIVE_CHANCE_STRENGTH = 0.6


def chance_scale_from_initiative(value: float,
                                 strength: float = INITIATIVE_CHANCE_STRENGTH) -> float:
    v = max(0.0, min(1.0, value))
    s = max(0.0, min(1.0, strength))
    return 1.0 + s * (v - 0.5) * 2.0


def select(scenarios: list[Scenario], ctx: ScenarioContext, surface: str,
           *, roll=random.random) -> Scenario | None:
    cands = sorted((s for s in scenarios if s.surface == surface and eligible(s, ctx)),
                   key=lambda s: s.priority, reverse=True)
    for s in cands:
        c = _chance(s)
        if c < 1.0 and ctx.chance_scale != 1.0:
            c = max(0.0, min(1.0, c * ctx.chance_scale))
        if c >= 1.0 or roll() < c:
            return s
    return None


select_scene = select


def proactive_candidates(scenarios: list[Scenario], ctx: ScenarioContext) -> list[Scenario]:
    return [s for s in scenarios
            if s.surface == "proactive" and s.weight > 0 and eligible(s, ctx)]


def pick_proactive(scenarios: list[Scenario], ctx: ScenarioContext,
                   *, rng: random.Random | None = None) -> Scenario | None:
    cands = proactive_candidates(scenarios, ctx)
    if not cands:
        return None
    return (rng or random).choices(cands, weights=[s.weight for s in cands], k=1)[0]


def mark_fired(event_log: dict, scenario_id: str, now: float) -> None:
    rec = event_log.setdefault(scenario_id, {"count": 0, "last_fired_at": 0.0})
    rec["count"] = int(rec.get("count", 0)) + 1
    rec["last_fired_at"] = float(now)
