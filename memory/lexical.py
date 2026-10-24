from __future__ import annotations

import math
import re

_TOKEN_RX = re.compile(r"[а-яёa-z0-9]+")

_RU_ENDINGS = (
    "иями", "ями", "ами", "иях", "ией", "иям",
    "ого", "его", "ому", "ему", "ыми", "ими", "ешь", "ишь",
    "ах", "ях", "ов", "ев", "ей", "ий", "ый", "ой", "ая", "яя",
    "ое", "ее", "ые", "ие", "ем", "ом", "ам", "ям", "ум", "ут",
    "ют", "ат", "ят", "ла", "ло", "ли", "ть",
    "а", "я", "о", "е", "у", "ю", "ы", "и", "ь", "й",
)


def stem(word: str) -> str:
    for end in _RU_ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: len(word) - len(end)]
    return word


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower().replace("ё", "е")
    return [stem(t) for t in _TOKEN_RX.findall(low)]


def bm25_scores(query_tokens: list[str], docs: list[list[str]],
                k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    if not n or not query_tokens:
        return [0.0] * n
    avg_len = sum(len(d) for d in docs) / n or 1.0
    q_unique = list(dict.fromkeys(query_tokens))
    df = {t: sum(1 for d in docs if t in d) for t in q_unique}
    idf = {t: math.log(1.0 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in q_unique}
    scores: list[float] = []
    for d in docs:
        if not d:
            scores.append(0.0)
            continue
        norm = k1 * (1 - b + b * len(d) / avg_len)
        s = 0.0
        for t in q_unique:
            tf = d.count(t)
            if not tf:
                continue
            s += idf[t] * (tf * (k1 + 1)) / (tf + norm)
        scores.append(s)
    return scores


def rrf_merge(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    out: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            out[idx] = out.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return out
