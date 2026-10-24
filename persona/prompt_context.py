from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextSpec:
    behavior_rules: bool = True
    tools_guidance: bool = True

    persona: bool = False

    memory_context: bool = False
    recent_thought: bool = False
    recent_events: int = 0
    reflections: int = 0

    dialogue: int = 0
    last_session: bool = False
    greeting: bool = False

    drawing: bool = False

    mood: bool = False

    @classmethod
    def full_chat(cls, *, is_new_session: bool) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            memory_context=True,
            recent_thought=True,
            drawing=True,
            mood=True,
            last_session=True,
            greeting=is_new_session,
            dialogue=0,
            recent_events=4,
        )

    @classmethod
    def image_reaction(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            tools_guidance=False,
            persona=True,
            dialogue=6,
            drawing=True,
            mood=True,
        )

    @classmethod
    def nsfw_reaction(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            tools_guidance=False,
            persona=True,
            dialogue=6,
            mood=True,
        )

    @classmethod
    def action_confirmation(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            dialogue=6,
            mood=True,
        )

    @classmethod
    def opinion(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
        )

    @classmethod
    def proactive(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            memory_context=True,
            last_session=True,
            recent_events=5,
        )

    @classmethod
    def proactive_decision(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            last_session=True,
            reflections=12,
            mood=True,
            drawing=True,
        )

    @classmethod
    def morning_brief(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            mood=True,
        )

    @classmethod
    def interjection(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            mood=True,
        )

    @classmethod
    def reminder(cls) -> "ContextSpec":
        return cls(
            behavior_rules=True,
            persona=True,
            last_session=True,
            dialogue=4,
        )

    @classmethod
    def none(cls) -> "ContextSpec":
        return cls(behavior_rules=False)
