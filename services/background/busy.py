from __future__ import annotations

HEAVY_FLAGS: tuple[tuple[str, str], ...] = (
    ("session_processing", "завершение сессии"),
    ("reflection_running", "рефлексия"),
    ("wardrobe_preparing", "подготовка костюма"),
    ("style_changing", "смена стиля"),
    ("background_job_running", "фоновый job"),
)


def session_engaged(state: dict) -> bool:
    hist = state.get("history")
    msgs = getattr(hist, "messages", None) or []
    for m in msgs:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        if role == "user":
            return True
    return False


def busy_with(state: dict, ignore: tuple[str, ...] = ()) -> str | None:
    for key, label in HEAVY_FLAGS:
        if key in ignore:
            continue
        val = state.get(key)
        if not val:
            continue
        if isinstance(val, str):
            return f"{label} ({val})"
        return label
    return None


ACTIVITY_TEXT = {
    "main chat": "Пишет ответ",
    "chat_stream": "Пишет ответ",
    "chat": "Думает",
    "retrieval": "Вспоминает",
    "draw_router": "Разбирает просьбу",
    "Оценка настроения": "Определяет настроение",
    "grammar polish": "Проверяет текст",
    "Быстрая экстракция (в чате)": "Запоминает детали",
    "Proactive session expiry": "Прощается",
    "Сцена: знакомство": "Готовит встречу",
    "Утренняя сводка": "Готовит утреннюю сводку",
    "Дневник": "Пишет дневник",
    "Рефлексия: новые интересы/идеи": "Размышляет о разговоре",
    "Сводка сессии": "Подводит итоги сессии",
    "Извлечение: правила": "Разбирает память",
    "Извлечение: предпочтения": "Разбирает память",
    "Habit extraction": "Ищет привычки",
    "Извлечение связей (session-end)": "Связывает записи",
    "Извлечение тем-мнений (session-end)": "Формирует мнения",
    "Memory consolidation": "Наводит порядок в памяти",
    "Оценка: как он ко мне": "Оценивает отношения",
    "Draw: tag selection": "Придумывает кадр",
    "Реакция на снимок": "Смотрит на снимок",
    "NSFW-подводка": "Готовит подводку к снимку",
}
ACTIVITY_PREFIX = (
    ("Interjection [timer]", "Реагирует на таймер"),
    ("Interjection [document]", "Читает документ"),
    ("Interjection [gacha]", "Реагирует на билет удачи"),
    ("Interjection", "Реагирует на напоминание"),
    ("Proactive", "Решает, стоит ли написать"),
    ("semantic:", "Выполняет просьбу"),
    ("Debug", "Отладка"),
    ("debug", "Отладка"),
)
ACTIVITY_DEFAULT = "Модель работает"

TOOL_TEXT = {
    "web_search": "Ищет в интернете", "search_images": "Ищет картинки",
    "open_url": "Открывает страницу", "play_video": "Включает видео",
    "show_image": "Показывает картинку", "search_anime_art": "Ищет аниме-арт",
    "set_image_source": "Меняет источник картинок",
    "get_time": "Смотрит на часы", "get_weather": "Смотрит погоду",
    "set_location": "Запоминает место",
    "search_memory": "Ищет в памяти", "get_details": "Вспоминает подробности",
    "get_lore": "Вспоминает лор", "get_help": "Читает справку",
    "write_note": "Работает с заметками", "append_note": "Работает с заметками",
    "delete_note": "Работает с заметками", "list_notes": "Работает с заметками",
    "set_reminder": "Работает с напоминаниями", "list_reminders": "Работает с напоминаниями",
    "cancel_reminder": "Работает с напоминаниями", "set_timer": "Ставит таймер",
    "plan_event": "Планирует", "update_event": "Планирует",
    "change_outfit": "Переодевается", "style_self": "Меняет образ",
    "list_outfits": "Смотрит гардероб", "draw": "Готовит снимок",
    "search_document": "Читает документ", "open_app": "Открывает приложение",
    "record_event": "Обновляет память", "track_loop": "Обновляет память",
    "close_loop": "Обновляет память", "link_entities": "Обновляет память",
    "upsert_entity": "Обновляет память", "end_session": "Завершает сессию",
    "configure_brief": "Настраивает сводку",
}

JOB_TEXT = {
    "proactive_scenarios": "Обдумывает, чем заняться",
    "memory_consolidation": "Наводит порядок в памяти",
    "outfit_prepare": "Готовит наряд",
    "memory_prune": "Чистит память",
    "reminder_history_cleanup": "Чистит историю напоминаний",
    "reminder_delivery": "Доставляет напоминание",
}


def activity_text(label) -> str:
    lbl = str(label or "").strip()
    if lbl in ACTIVITY_TEXT:
        return ACTIVITY_TEXT[lbl]
    for prefix, text in ACTIVITY_PREFIX:
        if lbl.startswith(prefix):
            return text
    return ACTIVITY_DEFAULT


def tool_text(name) -> str:
    n = str(name or "").strip()
    return TOOL_TEXT.get(n) or (f"Выполняет действие ({n})" if n else "Выполняет действие")


def _status_context(state: dict) -> dict:
    if state.get("reflection_running"):
        out = {"detail": "рефлексия"}
        st = state.get("reflection_step") or {}
        if st.get("idx") and st.get("total"):
            out["step"] = st["idx"]
            out["total"] = st["total"]
        return out
    if state.get("session_processing"):
        return {"detail": "закрытие сессии"}
    return {}


def app_status(state: dict) -> dict:
    tool = state.get("tool_activity")
    if tool:
        return {"code": "tool", "label": tool_text(tool), **_status_context(state)}
    act = state.get("llm_activity")
    if act:
        return {"code": "model", "label": activity_text(act), **_status_context(state)}
    if state.get("reflection_running"):
        out = {"code": "reflection", "label": "Рефлексия"}
        st = state.get("reflection_step") or {}
        if st.get("label"):
            out["detail"] = st["label"]
            if st.get("idx") and st.get("total"):
                out["step"] = st["idx"]
                out["total"] = st["total"]
        return out
    if state.get("session_processing"):
        return {"code": "session_end", "label": "Закрывает сессию"}
    _w = state.get("wardrobe_preparing")
    if _w:
        out = {"code": "wardrobe", "label": "Готовит наряд"}
        if isinstance(_w, str):
            out["detail"] = _w
        return out
    if state.get("style_changing"):
        return {"code": "style", "label": "Меняет стиль рисования"}
    if state.get("drawing_active"):
        return {"code": "drawing", "label": "Рисует снимок"}
    _b = state.get("background_job_running")
    if _b:
        name = _b if isinstance(_b, str) else ""
        return {"code": "background", "label": JOB_TEXT.get(name, "Фоновая задача")}
    if state.get("chat_turn_active"):
        return {"code": "chat", "label": "Активный диалог"}
    return {"code": "idle",
            "label": "Активная сессия" if session_engaged(state) else "Ожидание"}


def status_text(st: dict) -> str:
    text = str(st.get("label") or "")
    if st.get("detail"):
        text += f" · {st['detail']}"
    if st.get("step") and st.get("total"):
        text += f" {st['step']}/{st['total']}"
    return text
