import re
from dataclasses import dataclass, field


_SUFFIXES = (
    "ами", "ями", "ого", "его", "ому", "ему",
    "ой", "ей", "ом", "ем", "ам", "ям", "ах", "ях",
    "ов", "ев", "ою", "ею",
    "ы", "и", "у", "ю", "е", "а", "о",
)


def get_stem(name: str) -> str:
    for suffix in _SUFFIXES:
        if name.endswith(suffix) and len(name) - len(suffix) >= 3:
            return name[:-len(suffix)]
    return name


STOP_WORDS = {
    "привет", "здравствуй", "здравствуйте", "пожалуйста", "спасибо",
    "извини", "извините", "прости", "простите",
    "ладно", "хорошо", "ладненько", "окей",
    "кстати", "конечно", "наверное", "возможно", "может", "кажется",
    "думаю", "знаешь", "слушай", "смотри", "короче", "кажется",
    "сегодня", "вчера", "завтра", "потом", "сейчас", "утром", "вечером",
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    "как", "что", "где", "когда", "почему", "зачем", "сколько", "какой", "какая",
    "господин", "господи", "хозяин",
    "расскажи", "покажи", "объясни", "помоги", "подскажи", "посмотри",
    "напомни", "найди", "сделай", "скажи", "давай", "проверь",
    "нет", "да", "ага", "угу", "ну", "вот", "так", "тут", "там",
}


PERSON_VERB_PATTERNS = [
    r"{stem}\w*\s+(?:сказал[аи]?|говорил[аи]?|спросил[аи]?|ответил[аи]?)",
    r"{stem}\w*\s+(?:пришёл|пришла|пришли|приехал[аи]?|уехал[аи]?)",
    r"{stem}\w*\s+(?:позвонил[аи]?|написал[аи]?|прислал[аи]?)",
    r"{stem}\w*\s+(?:рассказал[аи]?|предложил[аи]?|попросил[аи]?)",
    r"{stem}\w*\s+(?:работает|учится|живёт|живет|любит|хочет|знает|думает)",
    r"(?:видел[аи]?|встретил[аи]?|знаю|помню)\s+{stem}\w*",
    r"(?:звонил[аи]?|писал[аи]?)\s+{stem}\w*",
]

PERSON_RELATION_PATTERNS = [
    r"(?:мой|моя|мои|моё)\s+(?:друг|подруга|брат|сестра|коллега|жена|муж|мама|папа|дочь|сын|начальник|босс)\s+{stem}\w*",
    r"(?:друг|подруга|брат|сестра|коллега|жена|муж)\s+{stem}\w*",
    r"зовут\s+{stem}\w*",
    r"звали\s+{stem}\w*",
    r"это\s+{stem}\w*",
    r"с\s+{stem}\w*(?:\s+(?:ходил|пошли|гуляли|работаю|учимся|дружим|встретились))",
    r"у\s+{stem}\w*(?:\s+(?:был[аи]?|есть|будет|день\s*рождения))",
]

PRONOUNS_RU = {"он", "она", "его", "её", "ее", "ему", "ей", "им", "ней", "них", "него", "неё"}

PLACE_PREPOSITION_PATTERNS = [
    r"[вВ]\s+{stem}\w*(?:\s|$|,|\.)",
    r"[иИ]з\s+{stem}\w*(?:\s|$|,|\.)",
    r"[дД]о\s+{stem}\w*(?:\s|$|,|\.)",
    r"(?:рядом\s+с|около|возле|недалеко\s+от)\s+{stem}\w*",
    r"(?:приехал[аи]?\s+(?:в|из)|уехал[аи]?\s+(?:в|из))\s+{stem}\w*",
]

PLACE_MARKER_PATTERNS = [
    r"(?:город|улица|район|площадь|станция|метро|парк|аэропорт)\s+{stem}\w*",
    r"{stem}\w*\s+—?\s*(?:город|район|улица|деревня|село|посёлок|область)",
]


_CANDIDATE_RE = re.compile(r'[А-ЯЁ][а-яё]{2,}')

_SENTENCE_START_RE = re.compile(r'(?:^|[.!?]\s+)([А-ЯЁ][а-яё]{2,})')


def extract_candidates(text: str) -> list[str]:
    if not text.strip():
        return []

    all_caps = set(_CANDIDATE_RE.findall(text))

    sentence_starters = set()
    for m in _SENTENCE_START_RE.finditer(text):
        sentence_starters.add(m.group(1))

    first_match = _CANDIDATE_RE.match(text.strip())
    if first_match:
        sentence_starters.add(first_match.group())

    candidates = []
    for word in all_caps:
        if word.lower() in STOP_WORDS:
            continue

        if word in sentence_starters:
            mid_sentence = re.search(r'(?<=[а-яё,]\s)' + re.escape(word), text)
            if not mid_sentence:
                pass

        candidates.append(word)

    return sorted(set(candidates))


@dataclass
class SignalScore:
    person_score: int = 0
    place_score: int = 0
    person_signals: list[str] = field(default_factory=list)
    place_signals: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.person_score + self.place_score

    @property
    def entity_type(self) -> str:
        if self.total == 0:
            return "unknown"
        if self.person_score > self.place_score:
            return "person"
        if self.place_score > self.person_score:
            return "place"
        return "unknown"

    @property
    def confidence(self) -> float:
        if self.total == 0:
            return 0.1
        dominant = max(self.person_score, self.place_score)
        return min(0.95, 0.3 + dominant * 0.15)


def score_candidate(name: str, text: str) -> SignalScore:
    score = SignalScore()
    stem = get_stem(name)

    stem_re = re.escape(stem)

    for pattern in PERSON_VERB_PATTERNS:
        regex = pattern.replace("{stem}", stem_re)
        matches = len(re.findall(regex, text, re.IGNORECASE))
        if matches:
            score.person_score += matches * 2
            score.person_signals.append(f"verb ({matches}x)")

    for pattern in PERSON_RELATION_PATTERNS:
        regex = pattern.replace("{stem}", stem_re)
        matches = len(re.findall(regex, text, re.IGNORECASE))
        if matches:
            score.person_score += matches * 3
            score.person_signals.append(f"relation ({matches}x)")

    lines = text.split("\n")
    name_lower = name.lower()
    stem_lower = stem.lower()
    name_lines = []
    for i, line in enumerate(lines):
        if name_lower in line.lower() or stem_lower in line.lower():
            name_lines.append(i)

    pronoun_hits = 0
    for idx in name_lines:
        window = " ".join(lines[max(0, idx - 1): idx + 2]).lower()
        for pronoun in PRONOUNS_RU:
            if re.search(r'\b' + pronoun + r'\b', window):
                pronoun_hits += 1
                break
    if pronoun_hits:
        score.person_score += pronoun_hits
        score.person_signals.append(f"pronoun ({pronoun_hits}x)")

    for pattern in PLACE_PREPOSITION_PATTERNS:
        regex = pattern.replace("{stem}", stem_re)
        matches = len(re.findall(regex, text, re.IGNORECASE))
        if matches:
            score.place_score += matches * 2
            score.place_signals.append(f"preposition ({matches}x)")

    for pattern in PLACE_MARKER_PATTERNS:
        regex = pattern.replace("{stem}", stem_re)
        matches = len(re.findall(regex, text, re.IGNORECASE))
        if matches:
            score.place_score += matches * 2
            score.place_signals.append(f"marker ({matches}x)")

    return score


@dataclass
class DetectionResult:
    matched: list = field(default_factory=list)
    candidates: list = field(default_factory=list)


def detect_entities(text: str, records: list) -> DetectionResult:
    result = DetectionResult()

    if not text or not text.strip():
        return result

    candidates = extract_candidates(text)
    if not candidates:
        return result

    matched_ids = set()

    for name in candidates:
        from memory.disambiguator import disambiguate, is_ambiguous_word
        if is_ambiguous_word(name):
            verdict = disambiguate(name, text)
            if verdict == "noun":
                continue

        score = score_candidate(name, text)
        stem = get_stem(name)

        if is_ambiguous_word(name) and score.total == 0:
            continue

        matched_record = _match_record(name, stem, records)

        if matched_record and id(matched_record) not in matched_ids:
            matched_record.details["_fresh"] = True
            result.matched.append(matched_record)
            matched_ids.add(id(matched_record))
        elif score.total > 0:
            result.candidates.append({
                "name": name,
                "type": score.entity_type,
                "confidence": score.confidence,
                "signals": score.person_signals + score.place_signals,
            })
        else:
            result.candidates.append({
                "name": name,
                "type": "unknown",
                "confidence": 0.1,
                "signals": [],
            })

    return result


def _match_record(name: str, stem: str, records: list):
    name_lower = name.lower()
    stem_lower = stem.lower()

    for r in records:
        if r.type not in ("сущность", "событие"):
            continue

        r_title = r.title.lower()

        if r_title == name_lower:
            return r

        if name_lower in r_title or r_title in name_lower:
            return r

        r_stem = get_stem(r.title).lower()
        if len(stem_lower) >= 3 and len(r_stem) >= 3:
            if stem_lower == r_stem:
                return r
            min_len = min(len(stem_lower), len(r_stem))
            prefix = min(min_len, max(4, min_len - 1))
            if stem_lower[:prefix] == r_stem[:prefix]:
                return r

    return None
