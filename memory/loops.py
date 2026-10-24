from __future__ import annotations

import re

from memory.entity_schema import normalize_alias

LOOP_TYPE = "петля"

LOOP_KIND_GOAL = "цель"
LOOP_KIND_PROMISE = "обещание"
LOOP_KIND_SITUATION = "ситуация"
LOOP_KINDS = (LOOP_KIND_GOAL, LOOP_KIND_PROMISE, LOOP_KIND_SITUATION)

_KIND_ALIAS = {
    "цель": LOOP_KIND_GOAL, "мечта": LOOP_KIND_GOAL, "стремление": LOOP_KIND_GOAL,
    "хочет": LOOP_KIND_GOAL, "планирует": LOOP_KIND_GOAL,
    "обещание": LOOP_KIND_PROMISE, "обещал": LOOP_KIND_PROMISE,
    "обещала": LOOP_KIND_PROMISE, "обязательство": LOOP_KIND_PROMISE,
    "ситуация": LOOP_KIND_SITUATION, "тема": LOOP_KIND_SITUATION,
    "процесс": LOOP_KIND_SITUATION, "история": LOOP_KIND_SITUATION,
}

LOOP_SUBJ_MINE = "моё"
LOOP_SUBJ_USER = "пользователь"
LOOP_SUBJECTS = (LOOP_SUBJ_MINE, LOOP_SUBJ_USER)

_SUBJ_ALIAS = {
    "моё": LOOP_SUBJ_MINE, "мое": LOOP_SUBJ_MINE, "я": LOOP_SUBJ_MINE,
    "персонаж": LOOP_SUBJ_MINE, "себя": LOOP_SUBJ_MINE, "свое": LOOP_SUBJ_MINE,
    "пользователь": LOOP_SUBJ_USER, "пользователя": LOOP_SUBJ_USER,
    "господин": LOOP_SUBJ_USER, "хозяин": LOOP_SUBJ_USER, "юзер": LOOP_SUBJ_USER,
}

LOOP_SAL_ACTIVE = "активная"
LOOP_SAL_AMBIENT = "фоновая"
LOOP_SALIENCE = (LOOP_SAL_ACTIVE, LOOP_SAL_AMBIENT)

_SAL_ALIAS = {
    "активная": LOOP_SAL_ACTIVE, "активный": LOOP_SAL_ACTIVE, "важная": LOOP_SAL_ACTIVE,
    "фоновая": LOOP_SAL_AMBIENT, "фоновый": LOOP_SAL_AMBIENT, "фон": LOOP_SAL_AMBIENT,
    "пассивная": LOOP_SAL_AMBIENT, "тихая": LOOP_SAL_AMBIENT,
}

LOOP_STATUS_OPEN = "открыто"
LOOP_CLOSED_STATUSES = ("достигнуто", "выполнено", "отменено", "неактуально")

_IMPORTANCE_WORD = {
    "низкая": 0.35, "низкий": 0.35, "low": 0.35,
    "средняя": 0.6, "средний": 0.6, "medium": 0.6,
    "высокая": 0.9, "высокий": 0.9, "high": 0.9,
}


def _norm(text, table, default=""):
    raw = normalize_alias(text)
    if not raw:
        return default
    if raw in table:
        return table[raw]
    for alias, val in table.items():
        if len(alias) >= 4 and alias in raw:
            return val
    return default


def normalize_loop_kind(text: str) -> str:
    return _norm(text, _KIND_ALIAS, "")


def normalize_loop_subject(text: str) -> str:
    return _norm(text, _SUBJ_ALIAS, LOOP_SUBJ_USER)


def normalize_loop_salience(text: str) -> str:
    return _norm(text, _SAL_ALIAS, "")


def default_salience(kind: str, subject: str) -> str:
    return LOOP_SAL_AMBIENT if kind == LOOP_KIND_SITUATION else LOOP_SAL_ACTIVE


def default_importance(kind: str, subject: str) -> float:
    if subject == LOOP_SUBJ_MINE:
        return 0.8
    if kind == LOOP_KIND_SITUATION:
        return 0.4
    return 0.6


def importance_from_word(text: str, kind: str, subject: str) -> float:
    raw = normalize_alias(text)
    if raw in _IMPORTANCE_WORD:
        return _IMPORTANCE_WORD[raw]
    try:
        v = float(text)
        if 0.0 <= v <= 1.0:
            return v
    except (TypeError, ValueError):
        pass
    return default_importance(kind, subject)


def is_open(record) -> bool:
    return (getattr(record, "details", {}) or {}).get("status", LOOP_STATUS_OPEN) == LOOP_STATUS_OPEN


_TITLE_STOP = {
    "и", "в", "на", "с", "к", "у", "о", "об", "по", "за", "до", "от", "не", "что",
    "как", "для", "про", "из", "же", "бы", "ли", "а", "но", "то", "это", "его",
    "ее", "их", "ему", "ей", "им", "мне", "мой", "моя", "мое", "свой", "своя",
    "свое", "себе", "себя", "the", "a", "to", "of",
}


def loop_title_tokens(text: str) -> set[str]:
    from memory.lexical import tokenize
    return {t for t in tokenize(text or "") if t and t not in _TITLE_STOP}


def same_loop_title(a: str, b: str) -> bool:
    na, nb = normalize_alias(a), normalize_alias(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = loop_title_tokens(a), loop_title_tokens(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 2 and small <= big:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def match_loop_target(target: str, loops) -> object | None:
    t = (target or "").strip().strip("«»\"'").strip()
    if not t:
        return None
    if re.fullmatch(r"r\d+", t):
        return next((r for r in loops if getattr(r, "record_id", "") == t), None)
    tl = normalize_alias(t)
    for r in loops:
        if normalize_alias(getattr(r, "title", "") or "") == tl:
            return r
    tt = loop_title_tokens(t)
    if not tt:
        return None
    scored = []
    for r in loops:
        title_t = loop_title_tokens(getattr(r, "title", "") or "")
        desc_t = loop_title_tokens(str((getattr(r, "details", {}) or {}).get("description") or ""))
        s = sum(1.0 if tok in title_t else (0.7 if tok in desc_t else 0.0) for tok in tt) / len(tt)
        if s > 0:
            scored.append((s, r))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 1e-9:
        return None
    return scored[0][1]


LOOP_CHECKIN_BASE_INTERVAL = 2 * 86400.0
LOOP_CHECKIN_THRESHOLD = 0.30


def loop_readiness(loop, now: float) -> float:
    d = (getattr(loop, "details", {}) or {})
    if (getattr(loop, "type", "") != LOOP_TYPE
            or d.get("status", LOOP_STATUS_OPEN) != LOOP_STATUS_OPEN
            or d.get("salience") != LOOP_SAL_ACTIVE):
        return 0.0
    raised = int(d.get("raised_count", 0) or 0)
    last = float(d.get("last_raised_at") or getattr(loop, "created_at", 0.0) or 0.0)
    age = max(0.0, now - last)
    interval = LOOP_CHECKIN_BASE_INTERVAL * (1 + raised)
    staleness = min(1.0, age / interval) if interval > 0 else 1.0
    importance = float(getattr(loop, "importance", 0.5) or 0.5)
    damp = 1.0 / (1.0 + raised)
    return importance * staleness * damp


def select_loop_for_checkin(records, now: float, threshold: float | None = None):
    thr = LOOP_CHECKIN_THRESHOLD if threshold is None else threshold
    best, best_score = None, -1.0
    for r in (records or []):
        if getattr(r, "is_forgotten", False):
            continue
        s = loop_readiness(r, now)
        if s <= 0.0 and threshold == 0.0 and _is_active_open_loop(r):
            s = 0.0
        elif s <= 0.0:
            continue
        if s > best_score:
            best, best_score = r, s
    return best if (best is not None and best_score >= thr) else None


def _is_active_open_loop(r) -> bool:
    d = getattr(r, "details", {}) or {}
    return (getattr(r, "type", "") == LOOP_TYPE
            and d.get("status", LOOP_STATUS_OPEN) == LOOP_STATUS_OPEN
            and d.get("salience") == LOOP_SAL_ACTIVE)


def mark_loop_raised(loop, now: float) -> None:
    d = loop.details if getattr(loop, "details", None) is not None else {}
    d["last_raised_at"] = float(now)
    d["raised_count"] = int(d.get("raised_count", 0) or 0) + 1
    loop.details = d


def refresh_loop_interest(loop, now: float) -> None:
    d = loop.details if getattr(loop, "details", None) is not None else {}
    d["raised_count"] = 0
    d["last_raised_at"] = float(now)
    d.pop("my_opinion", None)
    loop.details = d
