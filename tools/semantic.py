from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from services.log_privacy import priv
from tools.registry import TIER_CONTEXTUAL, Tool, ToolContext


@dataclass
class SemanticResult:
    message: str = ""
    ok: bool = True
    facts: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class SemanticDeps:
    memory: Any = None
    now: float = 0.0
    debug: bool = False
    persona: Any = None
    extra: dict = field(default_factory=dict)


BuildSystem = Callable[[SemanticDeps], str]
Executor = Callable[[dict, SemanticDeps], SemanticResult]
Parser = Callable[[str], Optional[dict]]


@dataclass
class SemanticToolDef:
    name: str
    build_extract_system: BuildSystem
    executor: Executor
    parse: Parser
    fail_message: str = "Не разобрала запрос — переформулируй, пожалуйста."


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


_PROCESSORS: dict[str, SemanticToolDef] = {}


def register_processor(defn: SemanticToolDef) -> None:
    _PROCESSORS[defn.name] = defn


def get_processor(name: str) -> Optional[SemanticToolDef]:
    return _PROCESSORS.get(name)


def registered_names() -> list[str]:
    return list(_PROCESSORS.keys())


_THIN_SCHEMA_DESC = (
    "Что ты хочешь — короткой фразой на естественном языке (русский ОК). "
    "Систему деталей оформит отдельный обработчик; тебе формат знать не нужно."
)

_DEFAULT_ACK = (
    "Принято — обрабатываю запрос, результат придёт через пару секунд. СЕЙЧАС "
    "напиши КОРОТКУЮ реплику в характере (например «Сейчас сделаю~»). НЕ вызывай "
    "инструмент ещё раз — вызов уже принят."
)


def _make_handler(name: str, ack: str, min_len: int, empty_hint: str) -> Callable:
    def handler(args: dict, ctx: ToolContext) -> str:
        intent = (args.get("intent") or "").strip()
        if not intent or len(intent) < min_len:
            return empty_hint
        for a in ctx.pending_actions:
            if a.get("kind") == "semantic" and a.get("tool") == name:
                return ("Запрос УЖЕ принят — повторный вызов не нужен. Просто "
                        "ответь короткой репликой в характере.")
        ctx.pending_actions.append({"kind": "semantic", "tool": name, "intent": intent})
        return ack
    return handler


def make_semantic_tool(
    *,
    name: str,
    summary: str,
    help: str,
    description: str,
    build_extract_system: BuildSystem,
    executor: Executor,
    parse: Parser = extract_json,
    triggers: Optional[list[str]] = None,
    capability: str = "misc",
    tier: str = TIER_CONTEXTUAL,
    ack: str = _DEFAULT_ACK,
    fail_message: str = "Не разобрала запрос — переформулируй, пожалуйста.",
    intent_arg_desc: str = _THIN_SCHEMA_DESC,
    min_intent_len: int = 3,
    empty_hint: Optional[str] = None,
) -> Tool:
    register_processor(SemanticToolDef(
        name=name, build_extract_system=build_extract_system,
        executor=executor, parse=parse, fail_message=fail_message,
    ))
    if empty_hint is None:
        empty_hint = (f"{name} вызван без intent. Впиши одной фразой, что нужно "
                      f"(например для напоминания: «напомни завтра в 15:00 про "
                      f"врача»). Если инструмент не нужен — просто ответь словами.")
    return Tool(
        name=name,
        schema={
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "description": intent_arg_desc},
                },
                "required": ["intent"],
            },
        },
        handler=_make_handler(name, ack, min_intent_len, empty_hint),
        summary=summary,
        help=help,
        tier=tier,
        capability=capability,
        triggers=list(triggers or []),
    )


def process_semantic_action(action: dict, *, llm_chat: Callable[[str, str], str],
                            deps: SemanticDeps) -> SemanticResult:
    name = action.get("tool", "")
    intent = (action.get("intent") or "").strip()
    defn = _PROCESSORS.get(name)
    if defn is None:
        return SemanticResult(ok=False, message="",
                              data={"error": f"semantic tool {name!r} не зарегистрирован"})
    if not intent:
        return SemanticResult(ok=False, message="")

    try:
        system = defn.build_extract_system(deps)
        raw = llm_chat(system, intent)
    except Exception as e:
        return SemanticResult(ok=False, message="",
                              data={"error": f"extract LLM: {type(e).__name__}: {e}"})

    parsed = defn.parse(raw or "")
    if parsed is None:
        if deps.debug:
            print(f"[semantic:{name}] extract не распарсился: {priv(raw or '', 160)}")
        return SemanticResult(ok=False, message=defn.fail_message,
                              data={"raw": (raw or "")[:300]})
    try:
        return defn.executor(parsed, deps)
    except Exception as e:
        return SemanticResult(ok=False, message=defn.fail_message,
                              data={"error": f"executor: {type(e).__name__}: {e}",
                                    "parsed": parsed})
