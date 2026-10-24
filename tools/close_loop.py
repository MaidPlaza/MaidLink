from __future__ import annotations

import re

from memory.loops import LOOP_CLOSED_STATUSES, LOOP_STATUS_OPEN, LOOP_TYPE
from services.log_privacy import priv
from tools.semantic import SemanticDeps, SemanticResult, make_semantic_tool

_RECORD_ID_RE = re.compile(r"^r\d+$")
_DEFAULT_RESOLUTION = {"цель": "достигнуто", "обещание": "выполнено"}


def _is_open_loop(r) -> bool:
    return (getattr(r, "type", "") == LOOP_TYPE
            and (getattr(r, "details", {}) or {}).get("status", LOOP_STATUS_OPEN)
            == LOOP_STATUS_OPEN)


def _find_open_loop(mem, target: str):
    from memory.loops import match_loop_target
    open_loops = [r for r in getattr(mem, "records", []) if _is_open_loop(r)]
    return match_loop_target(target, open_loops)


def _normalize_resolution(text: str, kind: str) -> str:
    t = (text or "").strip().lower()
    for r in LOOP_CLOSED_STATUSES:
        if r in t:
            return r
    return _DEFAULT_RESOLUTION.get(kind, "неактуально")


def _build_close_extract_system(deps: SemanticDeps) -> str:
    return (
        "Ты — точный парсер ЗАКРЫТИЯ петли (цели/обещания/тянущейся ситуации). Из "
        "фразы извлеки, КАКУЮ петлю закрыть и ЧЕМ она кончилась. Верни СТРОГО JSON.\n\n"
        "Верни ровно такой вид:\n"
        '{"target": "<коротко, по чему узнать петлю>", '
        '"resolution": "достигнуто|выполнено|отменено|неактуально"}\n\n'
        "Правила:\n"
        "- resolution: достигнуто — цель достигнута; выполнено — обещание сдержано; "
        "отменено — отменили/передумали; неактуально — потеряло смысл/завершилось само.\n"
        "- target — короткая зацепка, по которой найти петлю: «про шарф», «поиск "
        "работы», «накопить на машину», «звонок маме».\n"
        "- Только если в фразе ЕСТЬ закрытие/завершение чего-то. Иначе target \"\".\n"
        "Только JSON."
    )


def _close_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла закрыть.")
    target = str(parsed.get("target") or "").strip()
    if not target:
        return SemanticResult(ok=False, message="Не поняла, какую петлю закрыть — уточни?")
    loop = _find_open_loop(mem, target)
    if loop is None:
        return SemanticResult(ok=False,
                              message=f"Не нашла открытую петлю по «{target}».")

    kind = (loop.details or {}).get("kind", "")
    resolution = _normalize_resolution(parsed.get("resolution"), kind)
    loop.details["status"] = resolution
    loop.type = "событие"
    mem.save()
    if deps.debug:
        print(f"[semantic:close_loop] «{priv(loop.title)}» → {resolution} (петля→событие)")

    facts = f"Закрыто ({resolution}): «{loop.title}». Теперь это в истории."
    return SemanticResult(message=facts, facts=facts,
                          data={"record_id": loop.record_id, "resolution": resolution})


CLOSE_LOOP_HELP = """close_loop(intent) — закрыть открытую «петлю», когда она
завершилась: цель достигнута, обещание выполнено, ситуация отменена/неактуальна.

Опиши ОДНОЙ фразой, что закрылось. Система найдёт нужную петлю и переведёт её в
историю (станет прошлым событием).

Примеры intent:
  - «Господин накопил на машину — цель достигнута»
  - «Господин позвонил маме, обещание выполнено»
  - «поиск работы закончился, он нашёл место»
  - «с переездом передумали, неактуально»

Резолюции: достигнуто (цель), выполнено (обещание), отменено, неактуально.
После закрытия петля перестаёт «висеть» (уходит из обязательств/тем).
"""


CLOSE_LOOP_TOOL = make_semantic_tool(
    name="close_loop",
    description=(
        "Закрыть открытую «петлю», когда она завершилась: цель достигнута, "
        "обещание выполнено, ситуация отменена/неактуальна — «накопил на машину», "
        "«позвонил маме», «нашёл работу», «с переездом передумали». Петля уходит "
        "в историю (станет прошлым событием)."
    ),
    intent_arg_desc=(
        "Что завершилось, одной фразой: «Господин накопил на машину», «позвонил "
        "маме», «поиск работы закончился — нашёл место»."
    ),
    summary=(
        "close_loop(intent) — закрыть завершившуюся петлю (цель достигнута / "
        "обещание выполнено / отменено); уходит в историю."
    ),
    help=CLOSE_LOOP_HELP,
    build_extract_system=_build_close_extract_system,
    executor=_close_executor,
    triggers=[
        "выполнил", "выполнила", "достиг", "достигла", "получилось", "удалось",
        "нашёл работу", "нашла работу", "накопил", "переехал", "переехала",
        "закончил", "завершил", "справился", "справилась", "передумал",
        "передумала", "отменил", "отменила", "больше не нужно", "уже неактуально",
        "сдержал слово", "обещание выполнено", "цель достигнута",
    ],
    capability="карточки_сущностей",
    ack=("Закрытие петли ПРИНЯТО (подтверждение с итогом придёт СЛЕДУЮЩЕЙ репликой). "
         "СЕЙЧАС ответь ОЧЕНЬ коротко в характере — например «Отлично~», «Рада за "
         "тебя~». НЕ перечисляй детали. НЕ вызывай close_loop снова."),
    fail_message="Не разобрала, что именно закрылось — скажи иначе: что завершилось?",
    empty_hint=("close_loop вызван без intent. Впиши одной фразой, что завершилось — "
                "например «Господин накопил на машину». Если закрывать нечего — ответь словами."),
)
