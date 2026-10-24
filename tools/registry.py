from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from persona.prompt_context import ContextSpec

if TYPE_CHECKING:
    from memory.unified import UnifiedMemory
    from config import WeatherConfig
    from persona.character_context import CharacterContext


TIER_CORE = "core"
TIER_CONTEXTUAL = "contextual"
TIER_RARE = "rare"


@dataclass
class ToolContext:
    memory: "UnifiedMemory | None" = None
    weather_config: "WeatherConfig | None" = None
    debug: bool = False

    pending_actions: list[dict] = field(default_factory=list)

    drawing_catalog: Any = None
    drawing_max_rating: str = "sfw"
    drawing_renderer_id: str = "sdxl"
    drawing_outfit_change_min_tier: str = "warming"
    wardrobe: Any = None
    current_outfit_id: str = ""
    default_outfit_id: str = ""
    identity: Any = None
    document: Any = None

    persona: "CharacterContext | None" = None

    recent_dialogue: list[dict] = field(default_factory=list)
    recent_events: list = field(default_factory=list)


Handler = Callable[[dict, ToolContext], str]


@dataclass
class Tool:
    name: str
    schema: dict
    handler: Handler
    summary: str
    help: str
    tier: str = TIER_CONTEXTUAL
    capability: str = "misc"
    triggers: list[str] = field(default_factory=list)
    context_needs: ContextSpec = field(default_factory=ContextSpec.none)
    pref_theme: str = ""
    pref_hint: str = ""

    @property
    def as_openai_schema(self) -> dict:
        return {"type": "function", "function": self.schema}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} already registered")
        self._tools[tool.name] = tool
        return tool

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def pref_theme_routes(self) -> list[tuple[str, str]]:
        return [(t.pref_theme, t.pref_hint or t.pref_theme)
                for t in self._tools.values() if getattr(t, "pref_theme", "")]

    def select_active(
        self,
        query: str = "",
        query_embedding: list[float] | None = None,
    ) -> list[Tool]:
        return [t for t in self._tools.values()
                if t.tier in (TIER_CORE, TIER_CONTEXTUAL)]

    def schemas_for(self, tools: list[Tool]) -> list[dict]:
        return [t.as_openai_schema for t in tools]

    def handle(self, name: str, arguments: dict, ctx: ToolContext) -> str | None:
        tool = self._tools.get(name)
        if not tool:
            return f"Инструмент «{name}» не найден. Вызови get_help() для списка."
        self._fill_context(tool, ctx)
        return tool.handler(arguments or {}, ctx)

    def _fill_context(self, tool: Tool, ctx: ToolContext) -> None:
        needs = tool.context_needs
        if not (needs.persona or needs.dialogue > 0 or needs.recent_events > 0):
            return
        mem = ctx.memory
        state = getattr(mem, "_session_state_ref", None) if mem is not None else None
        if needs.persona and ctx.persona is None and state is not None:
            ctx.persona = state.get("persona")
        if needs.dialogue > 0 and state is not None:
            hist = state.get("history")
            if hist is not None:
                ctx.recent_dialogue = hist.get_last_n(needs.dialogue)
        if needs.recent_events > 0 and mem is not None:
            ctx.recent_events = mem.get_recent_events(needs.recent_events)

