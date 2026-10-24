from __future__ import annotations

import time
from dataclasses import dataclass

AXIS_BAND_DEFAULT = 0.25
AXIS_BEYOND = 0.15
INNER_EDGE_DAMP = 0.3
OUTER_DAMP = 0.3
GOAL_BEYOND_DAMP = 0.35
AXIS_RELAX = 0.01
AXIS_GOAL_DRIP = 0.01
GOAL_DRIP_BY_RESPECT = (0.0, 0.5, 1.0, 2.0, 3.0)
GOAL_OVERRIDE_STAGE = 4
AXIS_MIGRATION_TAG = "band_2026_09_28"


@dataclass(frozen=True)
class AxisFrame:
    norm: float
    band_lo: float
    band_hi: float
    floor: float
    ceiling: float
    frozen: bool = False

    @property
    def reach_lo(self) -> float:
        return max(self.floor, self.band_lo - AXIS_BEYOND)

    @property
    def reach_hi(self) -> float:
        return min(self.ceiling, self.band_hi + AXIS_BEYOND)


def axis_frame(character, axis: str) -> AxisFrame:
    norm = float((getattr(character, "axis_initial_values", {}) or {}).get(axis, 0.5))
    band = float((getattr(character, "axis_bands", {}) or {}).get(axis, AXIS_BAND_DEFAULT))
    floor = float((getattr(character, "axis_min_values", {}) or {}).get(axis, 0.0))
    ceiling = float((getattr(character, "axis_max_values", {}) or {}).get(axis, 1.0))
    floor = max(0.0, min(1.0, floor))
    ceiling = max(floor, min(1.0, ceiling))
    lo = max(floor, min(ceiling, norm - band))
    hi = max(floor, min(ceiling, norm + band))
    frozen = axis in (getattr(character, "frozen_axes", set()) or set())
    return AxisFrame(norm=norm, band_lo=lo, band_hi=hi, floor=floor, ceiling=ceiling,
                     frozen=frozen)


def goal_dir(identity, axis: str) -> int:
    g = (getattr(identity, "axis_goals", {}) or {}).get(axis) or {}
    try:
        d = int(g.get("dir", 0))
    except (TypeError, ValueError):
        return 0
    return 1 if d > 0 else (-1 if d < 0 else 0)


def resistance(value: float, direction: float, frame: AxisFrame, goal: int = 0) -> float:
    if direction == 0:
        return 0.0
    up = direction > 0
    toward_norm = (up and value < frame.norm) or ((not up) and value > frame.norm)
    if toward_norm:
        return 1.0
    edge = frame.band_hi if up else frame.band_lo
    width = abs(edge - frame.norm)
    outside = (value - edge) if up else (edge - value)
    if outside < 0:
        if width <= 1e-9:
            return INNER_EDGE_DAMP
        d = min(1.0, abs(value - frame.norm) / width)
        damp = 1.0 - (1.0 - INNER_EDGE_DAMP) * d
    else:
        damp = OUTER_DAMP * max(0.0, 1.0 - outside / AXIS_BEYOND)
    if goal == (1 if up else -1):
        damp = max(damp, GOAL_BEYOND_DAMP)
    return max(0.0, min(1.0, damp))


def relax(st, frame: AxisFrame, goal: int = 0) -> float:
    v = float(st.axis_value)
    if v > frame.band_hi and goal != 1:
        new = max(frame.band_hi, v - AXIS_RELAX)
    elif v < frame.band_lo and goal != -1:
        new = min(frame.band_lo, v + AXIS_RELAX)
    else:
        return 0.0
    st.axis_value = new
    return new - v


def apply_axis_step(st, delta: float, frame: AxisFrame, goal: int = 0) -> float:
    from persona.evolution import (AXIS_APPLIED_CAP, AXIS_MOMENTUM_DECAY,
                                   AXIS_MOMENTUM_THRESHOLD)
    if frame.frozen:
        return 0.0
    if delta == 0.0:
        st.axis_momentum *= AXIS_MOMENTUM_DECAY
        return relax(st, frame, goal)
    st.axis_momentum += delta
    if abs(st.axis_momentum) < AXIS_MOMENTUM_THRESHOLD:
        return 0.0
    raw = st.axis_momentum * 0.5
    raw = max(-AXIS_APPLIED_CAP, min(AXIS_APPLIED_CAP, raw))
    st.axis_momentum -= raw
    applied = raw * resistance(float(st.axis_value), raw, frame, goal)
    old = float(st.axis_value)
    st.axis_value = max(frame.floor, min(frame.ceiling, old + applied))
    if st.axis_value >= frame.ceiling or st.axis_value <= frame.floor:
        st.axis_momentum = 0.0
    return st.axis_value - old


def describe_frame(frame: AxisFrame) -> str:
    return f"норма {frame.norm:.2f}, полоса {frame.band_lo:.2f}–{frame.band_hi:.2f}"


def migrate_axes_to_band(identity, character, *, tag: str = AXIS_MIGRATION_TAG) -> list[str]:
    log = getattr(identity, "event_log", None)
    if log is None:
        identity.event_log = log = {}
    if log.get("axis_band_migration") == tag:
        return []
    moved: list[str] = []
    for st in getattr(identity, "self_statements", []) or []:
        if not st.id.startswith("axis_"):
            continue
        axis = st.id[len("axis_"):]
        frame = axis_frame(character, axis)
        if frame.frozen:
            continue
        v = float(st.axis_value)
        target = None
        if v > frame.reach_hi:
            target = frame.band_hi
        elif v < frame.reach_lo:
            target = frame.band_lo
        if target is None or abs(target - v) < 1e-9:
            continue
        st.history.append({"migration": tag, "value_before": v, "value_after": target,
                           "reason": "оси характера: возврат в полосу дуги вокруг нормы",
                           "timestamp": time.time()})
        st.axis_value = target
        st.axis_momentum = 0.0
        moved.append(axis)
    log["axis_band_migration"] = tag
    return moved


def set_axis_goal(identity, axis: str, direction: int, *, source: str = "chat",
                  note: str = "") -> bool:
    goals = getattr(identity, "axis_goals", None)
    if goals is None:
        identity.axis_goals = goals = {}
    d = 1 if direction > 0 else (-1 if direction < 0 else 0)
    if d == 0:
        return goals.pop(axis, None) is not None
    cur = goals.get(axis) or {}
    if int(cur.get("dir", 0) or 0) == d and len(goals) == 1:
        return False
    for other in [k for k in goals if k != axis]:
        goals.pop(other, None)
    goals[axis] = {"dir": d, "since": time.time(), "source": source, "note": note}
    return True


def goal_respect_stage(character, identity) -> int | None:
    try:
        from persona.relationship_axes import REL_AXIS_RESPECT, axis_stage_index
        return axis_stage_index(character, identity, REL_AXIS_RESPECT)
    except Exception:
        return None


def goal_drip_rate(character, identity) -> float:
    stage = goal_respect_stage(character, identity)
    if stage is None:
        return AXIS_GOAL_DRIP
    stage = max(0, min(len(GOAL_DRIP_BY_RESPECT) - 1, int(stage)))
    return AXIS_GOAL_DRIP * GOAL_DRIP_BY_RESPECT[stage]


def goal_overrides_natural(character, identity) -> bool:
    stage = goal_respect_stage(character, identity)
    return stage is not None and int(stage) >= GOAL_OVERRIDE_STAGE


def apply_goal_drip(identity, character) -> dict[str, float]:
    goals = getattr(identity, "axis_goals", None) or {}
    if not goals:
        return {}
    rate = goal_drip_rate(character, identity)
    if rate <= 0.0:
        return {}
    override = goal_overrides_natural(character, identity)
    stmts = {s.id[len("axis_"):]: s for s in getattr(identity, "self_statements", []) or []
             if str(getattr(s, "id", "")).startswith("axis_")}
    moved: dict[str, float] = {}
    for axis, g in list(goals.items()):
        st = stmts.get(axis)
        d = goal_dir(identity, axis)
        if st is None or d == 0:
            continue
        frame = axis_frame(character, axis)
        if frame.frozen:
            continue
        old = float(st.axis_value)
        step = rate * d * (1.0 if override else resistance(old, d, frame, d))
        new = max(frame.floor, min(frame.ceiling, old + step))
        if abs(new - old) < 1e-9:
            continue
        st.axis_value = new
        st.source = "evolved"
        hist = getattr(st, "history", None)
        if isinstance(hist, list):
            hist.append({"delta": 0.0, "applied": new - old, "value_before": old,
                         "value_after": new, "momentum_after": float(getattr(st, "axis_momentum", 0.0)),
                         "reason": "пожелание Господина: капля к цели", "evidence": "",
                         "stimulus": "", "timestamp": time.time()})
        moved[axis] = new - old
    return moved
