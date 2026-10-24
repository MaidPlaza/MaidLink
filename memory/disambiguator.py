import re


AMBIGUOUS_WORDS = {
    "надежда": "чувство",
    "вера": "чувство",
    "любовь": "чувство",
    "радость": "чувство",
    "роман": "литература",
    "марк": "валюта",
    "максим": "оружие",
    "лев": "животное",
    "роза": "цветок",
    "лилия": "цветок",
    "марта": "месяц",
    "май": "месяц",
    "регина": "титул",
    "виктория": "победа",
    "валентина": None,
    "артём": None,
    "полина": None,
}


NAME_CONTEXT_PATTERNS = [
    r"{word}\s+(?:сказал[аи]?|говорил[аи]?|спросил[аи]?|ответил[аи]?|пришёл|пришла)",
    r"{word}\s+(?:позвонил[аи]?|написал[аи]?|рассказал[аи]?)",
    r"{word}\s+(?:работает|учится|живёт|живет|любит|хочет|знает)",
    r"(?:мой|моя|мои)\s+(?:друг|подруга|сестра|брат|коллега|жена|муж|мама|папа)\s+{word}",
    r"(?:друг|подруга|сестра|брат|коллега)\s+{word}",
    r"зовут\s+{word}",
    r"звали\s+{word}",
    r"это\s+{word}",
    r"(?:видел[аи]?|встретил[аи]?)\s+{word}",
    r"с\s+{word}\w*\s+(?:ходил|пошли|гуляли|работаю)",
    r"у\s+{word}\w*\s+(?:был[аи]?|есть|будет)",
    r"{word}\w*(?:'?[сн])\s",
]

NOUN_CONTEXT_PATTERNS = [
    r"(?:моя|мой|эта|этот|та|тот|какая|какой)\s+{stem}\w*",
    r"(?:нет|без|ради)\s+{stem}\w*",
    r"(?:чувство|ощущение)\s+{stem}\w*",
    r"{stem}\w*\s+(?:угасла|исчезла|пропала|вернулась|осталась)",
    r"(?:большая|маленькая|старая|новая|последняя|первая)\s+{stem}\w*",
]


def disambiguate(word: str, context: str) -> str:
    lower = word.lower()

    if lower not in AMBIGUOUS_WORDS:
        return "not_ambiguous"

    name_score = 0
    noun_score = 0

    from memory.entity_detector import get_stem
    stem = get_stem(lower)

    for pattern in NAME_CONTEXT_PATTERNS:
        regex = pattern.replace("{word}", re.escape(word))
        if re.search(regex, context, re.IGNORECASE):
            name_score += 1

    for pattern in NOUN_CONTEXT_PATTERNS:
        regex = pattern.replace("{word}", re.escape(word)).replace("{stem}", re.escape(stem))
        if re.search(regex, context, re.IGNORECASE):
            noun_score += 1

    mid_sentence = re.search(r'(?<=[а-яё,]\s)' + re.escape(word), context)
    if mid_sentence:
        name_score += 1

    only_at_start = not mid_sentence and re.search(r'(?:^|[.!?]\s+)' + re.escape(word), context)
    if only_at_start and noun_score == 0 and name_score == 0:
        return "ambiguous"

    if name_score > noun_score:
        return "name"
    if noun_score > name_score:
        return "noun"

    return "ambiguous"


def is_ambiguous_word(word: str) -> bool:
    return word.lower() in AMBIGUOUS_WORDS
