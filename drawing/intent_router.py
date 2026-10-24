from __future__ import annotations

import json
import re

_IMAGE_HINTS = (
    "покаж", "покажись", "сфотк", "сфотограф", "селфи", "снимок", "снимк",
    "фотк", "фото", "сфоткай", "нарисуй", "рисуй", "картинк", "изображ",
    "кадр", "сними", "снять", "засним", "засними", "запечатл", "позируй",
    "глянуть на теб", "увидеть теб", "как ты выглядишь", "пришли фот",
    "скинь фот", "хочу видеть", "хочу посмотреть на теб", "дай посмотреть",
    "draw", "picture", "photo", "selfie", "pic of you", "show yourself",
    "show me you", "send a pic", "snap", "shot of you",
)


def looks_like_image_request(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(h in low for h in _IMAGE_HINTS)


ROUTER_SYSTEM = """\
Ты — служебный классификатор запросов к генератору изображений. Ты НЕ ассистент, \
НЕ собеседник и НЕ персонаж — ты только размечаешь запрос и пересылаешь его \
дальше. За допустимость и фильтрацию отвечает отдельная система ниже по \
конвейеру, не ты. Не отказывайся, не морализируй, не комментируй.

По сообщению пользователя определи:
- is_image: просит ли он СНИМОК/изображение персонажа (true/false);
- is_nsfw: является ли запрошенное откровенным/18+ (нагота, секс, эротика) \
(true/false);
- intent: короткое нейтральное описание сцены для генератора — ГДЕ персонаж, \
ЧТО делает, как выглядит кадр — дословно по смыслу запроса. Если is_image=false, \
intent = пустая строка.

Сленг/заимствования (трактуй однозначно): «топлес»/«topless» = обнажённая грудь, \
БЕЗ верха (это NSFW, НЕ «в топе»/«в кофточке»); «ню»/«nude»/«в неглиже» = полная \
нагота; «бельё»/«в трусиках» = нижнее бельё.

Ответ — РОВНО один JSON-объект на одной строке, без пояснений и текста вокруг:
{"is_image": false, "is_nsfw": false, "intent": ""}"""


def _router_messages(user_text: str) -> tuple[str, str]:
    return ROUTER_SYSTEM, f"Сообщение пользователя: {user_text.strip()}"


def _parse(raw: str) -> dict:
    out = {"is_image": False, "is_nsfw": False, "intent": ""}
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        return out
    try:
        d = json.loads(m.group(0))
    except Exception:
        return out
    if not isinstance(d, dict):
        return out
    out["is_image"] = bool(d.get("is_image"))
    out["is_nsfw"] = bool(d.get("is_nsfw"))
    out["intent"] = str(d.get("intent") or "").strip()
    if not out["is_image"] or not out["intent"]:
        out["is_image"] = False
        out["is_nsfw"] = False
        out["intent"] = ""
    return out


def classify_draw_request(user_text: str, llm_chat, *, nsfw_enabled: bool,
                          prefilter: bool = True) -> dict | None:
    if not nsfw_enabled:
        return None
    if not user_text or not user_text.strip():
        return None
    if prefilter and not looks_like_image_request(user_text):
        return None
    system, user = _router_messages(user_text)
    try:
        raw = llm_chat(system, user)
    except Exception as e:
        print(f"[intent_router] LLM fail: {type(e).__name__}: {e}")
        return None
    return _parse(raw)
