import re
from dataclasses import dataclass


ENTITY_MARKERS = [
    r"зовут\s+[А-ЯЁ]",
    r"(?:мой|моя|мои|моё)\s+(?:друг|подруга|сестра|брат|коллега|жена|муж|мама|папа|дочь|сын|начальник|босс)",
    r"(?:друг|подруга|брат|сестра|коллега)\s+[А-ЯЁ]",
    r"(?:работает|учится|живёт|живет)\s+(?:в|на|у)",
    r"(?:познакомился|познакомилась)\s+с",
    r"(?:есть|был[аи]?)\s+(?:друг|подруга|сестра|брат|коллега|сосед|соседка)",
    r"[А-ЯЁ][а-яё]+\s+—\s+(?:мой|моя|это)",
]

EVENT_MARKERS = [
    r"(?:вчера|сегодня|позавчера|на\s+(?:прошлой|этой)\s+неделе|недавно|давно|на\s+днях)",
    r"(?:случилось|произошло|получилось|удалось|вышло)",
    r"(?:ходил[аи]?|пошли|сходил[аи]?|побывал[аи]?)\s+(?:в|на|к)",
    r"(?:встретил[аи]?|увидел[аи]?|нашёл|нашла|узнал[аи]?|обнаружил[аи]?)",
    r"(?:купил[аи]?|продал[аи]?|получил[аи]?|потерял[аи]?|сломал[аи]?)",
    r"(?:начал[аи]?|закончил[аи]?|бросил[аи]?|решил[аи]?)",
    r"(?:переехал[аи]?|уволился|уволилась|устроился|устроилась)",
    r"(?:поссорились|помирились|расстались|встречаемся)",
    r"(?:был[аи]?\s+(?:в|на)|ездил[аи]?\s+(?:в|на|к))",
]

PREFERENCE_MARKERS = [
    r"(?:нравится|не\s+нравится|нравилось|не\s+нравилось)",
    r"(?:люблю|обожаю|ненавижу|терпеть\s+не\s+могу)",
    r"(?:предпочитаю|не\s+выношу|не\s+переношу)",
    r"(?:мой|моя|моё)\s+любим(?:ый|ая|ое|ые)",
    r"(?:лучшее|лучший|лучшая|худшее|худший|худшая)",
    r"(?:интересуюсь|увлекаюсь|занимаюсь)",
    r"(?:боюсь|не\s+люблю|раздражает|бесит)",
    r"(?:мечтаю|хочу\s+(?:попробовать|научиться|посетить|купить))",
    r"(?:вкусн|классн|отличн|ужасн|отвратительн)\w+",
]


@dataclass
class ClassificationResult:
    type: str
    confidence: float
    markers_found: list[str]


def classify_text(text: str) -> ClassificationResult | None:
    if not text or not text.strip():
        return None

    text_lower = text.lower()

    entity_hits = _count_matches(text, ENTITY_MARKERS)
    event_hits = _count_matches(text, EVENT_MARKERS)
    pref_hits = _count_matches(text, PREFERENCE_MARKERS)

    total = entity_hits[0] + event_hits[0] + pref_hits[0]
    if total == 0:
        return None

    scores = [
        ("сущность", entity_hits[0], entity_hits[1]),
        ("событие", event_hits[0], event_hits[1]),
        ("предпочтение", pref_hits[0], pref_hits[1]),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    best_type, best_score, best_markers = scores[0]

    if best_score == 0:
        return None

    confidence = min(0.95, 0.3 + best_score * 0.2)

    if len(text) > 100:
        confidence = min(0.95, confidence + 0.1)

    if len(scores) > 1 and scores[1][1] > 0:
        ratio = scores[1][1] / best_score if best_score > 0 else 0
        if ratio > 0.7:
            confidence *= 0.7

    return ClassificationResult(
        type=best_type,
        confidence=round(confidence, 2),
        markers_found=best_markers,
    )


def classify_messages(messages: list[dict]) -> list[dict]:
    hints = []
    for msg in messages:
        if msg.get("role") != "user":
            continue
        result = classify_text(msg["content"])
        if result and result.confidence >= 0.4:
            hints.append({
                "message": msg["content"][:80],
                "type": result.type,
                "confidence": result.confidence,
            })
    return hints


def _count_matches(text: str, patterns: list[str]) -> tuple[int, list[str]]:
    total = 0
    matched = []
    for pattern in patterns:
        hits = len(re.findall(pattern, text, re.IGNORECASE))
        if hits:
            total += hits
            matched.append(pattern[:40])
    return total, matched
