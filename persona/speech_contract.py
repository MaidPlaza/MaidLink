from __future__ import annotations

import re

from persona import speech_guard as _sg

MAX_WORD_MARKERS = 3
ANTI_VOICE_PREFIXES = ("не твой голос", "не твои слова", "чужой голос", "не твоё")

_WORD_RX = re.compile(r"[\w\-]+", re.UNICODE)
_ADDRESS_WORDS = {"господин", "госпожа", "мастер", "хозяин", "хозяйка", "сэмпай"}


def _is_anti_voice(item: str) -> bool:
    return _sg._norm(item).startswith(ANTI_VOICE_PREFIXES)


def _clean(raw: str, hon: set[str]) -> str:
    m = _sg._norm(raw).strip(" .,!?;:")
    if not m:
        return ""
    if not _sg.is_symbol(m):
        words = _WORD_RX.findall(m)
        if len(words) > 4 or len(m) < 3 or m in _sg._STOP:
            return ""
        if len(words) == 1 and (words[0] in hon or words[0] in _ADDRESS_WORDS):
            return ""
    return m


def design_signature(data: dict) -> dict[str, list[str]]:
    style = data.get("speaking_style") or {}
    hon = _sg._honorific_forms(str(style.get("honorific") or ""))
    pets = [m for m in (_clean(str(x), hon) for x in style.get("pet_names") or []) if m]
    seals = [m for m in (_clean(str(x), hon) for x in style.get("seals") or []) if m]
    words: list[str] = []

    def add(raw: str) -> None:
        m = _clean(str(raw), hon)
        if not m or m in pets:
            return
        if _sg.is_symbol(m):
            if m not in seals:
                seals.append(m)
            return
        if m not in words:
            words.append(m)

    for raw in style.get("markers") or []:
        add(raw)
    for q in style.get("quirks") or []:
        q = str(q)
        if _is_anti_voice(q):
            continue
        for raw in _sg._QUOTE_RX.findall(q):
            add(raw)
    return {"words": words, "seals": seals, "pet_names": pets}


def design_markers(data: dict) -> tuple[list[str], list[str]]:
    sig = design_signature(data)
    return sig["words"], sig["seals"]


def quirk_quotes(data: dict) -> list[str]:
    style = data.get("speaking_style") or {}
    hon = _sg._honorific_forms(str(style.get("honorific") or ""))
    sig = design_signature(data)
    out: list[str] = []
    for q in style.get("quirks") or []:
        q = str(q)
        if _is_anti_voice(q):
            continue
        for raw in _sg._QUOTE_RX.findall(q):
            m = _clean(raw, hon)
            if (m and not _sg.is_symbol(m) and m not in sig["pet_names"]
                    and m not in sig["seals"] and m not in out):
                out.append(m)
    return out


def other_blocks(data: dict) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}

    def put(name: str, text) -> None:
        if isinstance(text, (list, dict)):
            text = str(text)
        text = str(text or "").strip()
        if text:
            blocks.setdefault(name, []).append(text)

    for axis, spec in (data.get("character_axes") or {}).items():
        for lvl in (spec or {}).get("levels") or []:
            if isinstance(lvl, dict):
                put("пример оси", lvl.get("example"))
                put("текст оси", lvl.get("text"))
    for axis, spec in (data.get("relationship_axes") or {}).items():
        for lvl in (spec or {}).get("levels") or []:
            if isinstance(lvl, dict):
                put("текст ступени отношений", lvl.get("text"))
    for state, st in (data.get("mood_styles") or {}).items():
        if isinstance(st, dict):
            put("тон настроения", st.get("tone"))
            for ex in st.get("examples") or []:
                put("пример настроения", ex)
    for quirk in data.get("speech_style_evolution") or []:
        if isinstance(quirk, dict):
            put("эволюция речи", quirk.get("text"))
            for form in (quirk.get("forms") or {}).values():
                put("эволюция речи", form)
    put("prompt_overrides", data.get("prompt_overrides"))
    put("response_style", data.get("response_style"))
    return blocks


def cross_block_hits(data: dict) -> list[tuple[str, str, str]]:
    words = design_signature(data)["words"]
    hits: list[tuple[str, str, str]] = []
    for name, texts in other_blocks(data).items():
        for t in texts:
            for m in words:
                if _sg.count_marker(t, m):
                    hits.append((m, name, t[:70]))
    return hits


def violations(data: dict) -> list[str]:
    out: list[str] = []
    words = design_signature(data)["words"]
    if len(words) > MAX_WORD_MARKERS:
        out.append(f"словечек {len(words)} > {MAX_WORD_MARKERS}: "
                   + ", ".join(f"«{w}»" for w in words)
                   + " (личное обращение → pet_names, печать → seals)")
    quoted = quirk_quotes(data)
    if quoted:
        out.append("цитаты в quirks (место словечек — speaking_style.markers; личное "
                   "обращение — pet_names): " + ", ".join(f"«{q}»" for q in quoted))
    for m, block, frag in cross_block_hits(data):
        out.append(f"«{m}» повторяется в блоке «{block}»: {frag}…")
    return out
