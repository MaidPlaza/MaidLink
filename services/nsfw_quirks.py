from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from services.nsfw_extra import CONTENT_KEY, CODE_ENTRY, SEPARATOR

LIBRARY_FILE = "quirks.yaml"
ID_PREFIX = "quirk_"
SPECIAL_SLOT = "Q"
ORDINARY_CAP = 3
SPECIAL_CAP = 1

RAISED_BY = ("explicit_image", "explicit_talk", "gesture_in_explicit")


@dataclass(frozen=True)
class Quirk:
    code: str
    text: str = ""
    description: str = ""
    effect: str = ""
    special: bool = False
    axis_range: dict = field(default_factory=dict)
    not_when: tuple = ()
    mood: tuple = ()
    mood_cues: tuple = ()
    gain_signals: tuple = ()
    need: int = 2
    chance: float = 0.5
    mark_days: float = 30.0
    ttl_days: float = 45.0
    requires_any: tuple = ()
    requires_all: tuple = ()
    aftereffect: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return ID_PREFIX + self.code

    @property
    def trigger_signals(self) -> list:
        return list(self.mood_cues)


def _parse(raw: dict) -> "Quirk | None":
    code = str(raw.get("code") or "").strip()
    if len(code) != 2 or code[0] not in ("q", SPECIAL_SLOT):
        print(f"[quirks] код {code!r} не по формату — запись пропущена")
        return None
    special = code[0] == SPECIAL_SLOT
    if bool(raw.get("special")) != special:
        print(f"[quirks] {code}: слот и признак special расходятся — пропуск")
        return None
    gain = raw.get("gain") or {}
    req = raw.get("requires") or {}
    from persona.character import AxisRange
    ax = {}
    for axis, b in (raw.get("axis_range") or {}).items():
        if isinstance(b, dict):
            ax[str(axis)] = AxisRange(min=b.get("min"), max=b.get("max"))
    return Quirk(
        code=code,
        text=str(raw.get("text") or "").strip(),
        description=" ".join(str(raw.get("description") or "").split()),
        effect=" ".join(str(raw.get("effect") or "").split()),
        special=special,
        axis_range=ax,
        not_when=tuple(str(x) for x in (raw.get("not_when") or [])),
        mood=tuple(str(x) for x in (raw.get("mood") or [])),
        mood_cues=tuple(str(x) for x in (raw.get("mood_cues") or [])),
        gain_signals=tuple(str(x) for x in (gain.get("signals") or [])),
        need=int(gain.get("need", 2) or 2),
        chance=float(gain.get("chance", 0.5) or 0.5),
        mark_days=float(gain.get("mark_days", 30) or 30),
        ttl_days=float(raw.get("ttl_days", 45) or 45),
        requires_any=tuple(str(x) for x in (req.get("any") or [])),
        requires_all=tuple(str(x) for x in (req.get("all") or [])),
        aftereffect=dict(raw.get("aftereffect") or {}),
    )


def _dirs(project_root: Path, *, enabled_only: bool = True) -> list[Path]:
    from services import addons
    if enabled_only:
        return addons.content_dirs(project_root, CONTENT_KEY)
    out: list[Path] = []
    for a in addons.discover(project_root):
        rel = a.content.get(CONTENT_KEY)
        if rel and a.root is not None and (a.root / rel).exists():
            out.append(a.root / rel)
    return out


_CACHE: dict[tuple, dict] = {}


def library(project_root: Path, *, enabled_only: bool = True) -> dict[str, Quirk]:
    paths = [d / LIBRARY_FILE for d in _dirs(project_root, enabled_only=enabled_only)]
    key = tuple((str(p), p.stat().st_mtime if p.exists() else 0.0) for p in paths)
    if key in _CACHE:
        return _CACHE[key]
    out: dict[str, Quirk] = {}
    for p in paths:
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as e:
            print(f"[quirks] {p.name}: {e!r} — пропущен")
            continue
        for raw in data.get("quirks") or []:
            q = _parse(raw) if isinstance(raw, dict) else None
            if q is not None:
                out[q.code] = q
    _CACHE[key] = out
    return out


def clear_cache() -> None:
    _CACHE.clear()


def innate_codes(code_string: str) -> tuple[str, ...]:
    body = (code_string or "").strip()[1:]
    seg = body.split(SEPARATOR)
    if len(seg) < 3:
        return ()
    chunk = seg[2]
    if len(chunk) % 2:
        print(f"[quirks] нечётная длина участка «{chunk}» — пропущен")
        return ()
    return tuple(chunk[i:i + 2] for i in range(0, len(chunk), 2))


def encode_innate(codes) -> str:
    return "".join(str(c) for c in codes)


def carried(project_root: Path, *, code_string: str = "", identity=None,
            enabled_only: bool = True) -> list[Quirk]:
    lib = library(project_root, enabled_only=enabled_only)
    if not lib:
        return []
    codes: list[str] = list(innate_codes(code_string))
    for at in (getattr(identity, "active_traits", None) or []):
        tid = str(getattr(at, "trait_id", "") or "")
        if tid.startswith(ID_PREFIX):
            codes.append(tid[len(ID_PREFIX):])
    seen, picked = set(), []
    order = list(lib)
    for c in codes:
        q = lib.get(c)
        if q is None or c in seen:
            continue
        seen.add(c)
        picked.append(q)
    picked.sort(key=lambda q: (not q.special, order.index(q.code)))
    return picked


HEADER = ("Твои причуды — какая ты в интимном и откровенном. Не жди, пока "
          "разговор туда придёт: они ведут тебя сами — задают, к чему ты "
          "клонишь, чего добиваешься и где не уступаешь. Отыгрывай их, а не "
          "объявляй: вслух не называй и не объясняй. Где каждая молчит — "
          "сказано под ней:")


def render_block(quirks, *, gender: str = "female") -> str:
    from persona.gender import fill_forms
    quirks = [q for q in quirks if q.text or q.effect]
    if not quirks:
        return ""
    lines = [HEADER]
    for q in quirks:
        lines.append(f"  - {fill_forms(q.text, gender)}" if q.text else "  -")
        if q.effect:
            lines.append(f"    Проявление: {fill_forms(q.effect, gender)}")
        if q.not_when:
            lines.append("    Не проявляется: "
                         + "; ".join(fill_forms(x, gender) for x in q.not_when))
    return "\n".join(lines)


def mood_cues_of(quirks, *, gender: str = "female") -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for q in quirks:
        if not q.mood or not q.mood_cues:
            continue
        from persona.gender import fill_forms
        cue = "; ".join(fill_forms(str(s).strip(), gender)
                        for s in q.mood_cues[:2] if str(s).strip())
        if not cue:
            continue
        for state in q.mood:
            bucket = out.setdefault(str(state), [])
            if cue not in bucket:
                bucket.append(cue)
    return out


def aftereffect_for(quirks, raised_by: str):
    from persona import aftereffects as _ae
    for q in quirks:
        raw = q.aftereffect or {}
        if str(raw.get("raised_by") or "") != raised_by:
            continue
        obj = _ae.parse(raw, id=q.id, source="quirks")
        if obj is not None:
            return obj
    return None


def _axis_values(identity) -> dict:
    from persona.vulnerability_catalog import _current_axis_values
    return _current_axis_values(identity) if identity is not None else {}


def _active_ids(identity) -> set:
    return {str(getattr(at, "trait_id", "") or "")
            for at in (getattr(identity, "active_traits", None) or [])}


def candidates(project_root: Path, *, code_string: str = "", identity=None,
               enabled_only: bool = True) -> list[Quirk]:
    lib = library(project_root, enabled_only=enabled_only)
    if not lib:
        return []
    from persona.vulnerability_catalog import is_eligible
    have = carried(project_root, code_string=code_string, identity=identity,
                   enabled_only=enabled_only)
    have_codes = {q.code for q in have}
    ordinary_left = ORDINARY_CAP - sum(1 for q in have if not q.special)
    special_left = SPECIAL_CAP - sum(1 for q in have if q.special)
    axes = _axis_values(identity)
    owned = {q.id for q in have} | _active_ids(identity)

    out = []
    for code, q in lib.items():
        if code in have_codes:
            continue
        if (special_left if q.special else ordinary_left) <= 0:
            continue
        if not is_eligible(q, axes):
            continue
        if q.requires_all and not set(q.requires_all).issubset(owned):
            continue
        if q.requires_any and not (set(q.requires_any) & owned):
            continue
        out.append(q)
    return out


def _fresh_marks(progress: dict, code: str, q: Quirk, now: float) -> int:
    rec = progress.get(code) or {}
    last = float(rec.get("last_at") or 0.0)
    if last and (now - last) > q.mark_days * 86400.0:
        return 0
    return int(rec.get("count") or 0)


def apply_verdicts(project_root: Path, *, identity, verdicts, code_string: str = "",
                   now: float | None = None, rng=None,
                   enabled_only: bool = True) -> list:
    import random as _random
    import time as _time
    from persona.character import ActiveTrait

    lib = library(project_root, enabled_only=enabled_only)
    if not lib or not verdicts:
        return []
    now = _time.time() if now is None else now
    rng = rng or _random
    progress = dict(getattr(identity, "quirk_progress", None) or {})
    have = carried(project_root, code_string=code_string, identity=identity,
                   enabled_only=enabled_only)
    ordinary_left = ORDINARY_CAP - sum(1 for q in have if not q.special)
    special_left = SPECIAL_CAP - sum(1 for q in have if q.special)

    gained = []
    for tid, source_event in verdicts:
        code = str(tid)[len(ID_PREFIX):] if str(tid).startswith(ID_PREFIX) else str(tid)
        q = lib.get(code)
        if q is None:
            continue
        if (special_left if q.special else ordinary_left) <= 0:
            print(f"[quirks] {code}: потолок занят — метка не ставится")
            continue
        roll = rng.random()
        if roll >= q.chance:
            print(f"[quirks] {code}: бросок {roll:.2f} ≥ {q.chance:.2f} — мимо")
            continue
        count = _fresh_marks(progress, code, q, now) + 1
        progress[code] = {"count": count, "last_at": now}
        if count < q.need:
            print(f"[quirks] {code}: метка {count}/{q.need} "
                  f"(бросок {roll:.2f} < {q.chance:.2f})")
            continue
        identity.active_traits.append(ActiveTrait(
            trait_id=q.id, activated_at=now, source_event=source_event or ""))
        progress.pop(code, None)
        gained.append(q)
        if q.special:
            special_left -= 1
        else:
            ordinary_left -= 1
        print(f"[quirks] {code}: ПРИОБРЕТЕНА ({count}/{q.need} меток) — {q.text!r}")

    identity.quirk_progress = progress
    return gained
