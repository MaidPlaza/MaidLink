from __future__ import annotations

from tools.registry import Tool, ToolContext, TIER_CONTEXTUAL


def _session_state(ctx: ToolContext):
    mem = getattr(ctx, "memory", None)
    return getattr(mem, "_session_state_ref", None) if mem is not None else None


def _scenario_end_handler(args: dict, ctx: ToolContext) -> str:
    state = _session_state(ctx)
    rec = state.get("scenario") if state is not None else None
    if not rec:
        return ("Сейчас никакого сценария нет — завершать нечего. Просто "
                "продолжай разговор.")
    if not getattr(rec.get("obj"), "model_may_end", False):
        return (f"Сценарий «{rec.get('title', rec.get('id'))}» закончится сам — "
                "завершать его не нужно. Просто продолжай разговор.")
    rec["end_requested"] = True
    return (f"Хорошо: сценарий «{rec.get('title', rec.get('id'))}» завершится после "
            "этой реплики. Ответь как обычно — комментировать завершение не нужно.")


SCENARIO_END_SCHEMA = {
    "name": "scenario_end",
    "description": ("Завершить текущий сценарий (обстоятельства из блока "
                    "<сценарий>), когда он естественно исчерпал себя. Не "
                    "обязателен: без вызова сценарий закончится сам."),
    "parameters": {"type": "object", "properties": {}},
}


SCENARIO_END_HELP = """scenario_end() — завершить текущий сценарий.

Сценарий — обстоятельства разговора из блока <сценарий> (перерыв, поздний
разговор…). Он и так закончится сам (конец разговора, время); вызов нужен,
только если ты считаешь, что ситуация естественно исчерпана — например, перерыв
кончился и ты возвращаешься к делам. Вызывать не обязательно; без активного
сценария вызов ничего не делает.
"""


SCENARIO_END_TOOL = Tool(
    name="scenario_end",
    schema=SCENARIO_END_SCHEMA,
    handler=_scenario_end_handler,
    summary="scenario_end() — завершить текущий сценарий, когда он естественно исчерпан (не обязателен).",
    help=SCENARIO_END_HELP,
    tier=TIER_CONTEXTUAL,
    capability="сценарии",
    triggers=[],
)
