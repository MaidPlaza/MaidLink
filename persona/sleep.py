import json
import time
from dataclasses import dataclass, field

from persona.character import Character
from persona.character_context import resolve_honorific, CharacterContext


SIGNIFICANCE_IMPORTANCE = {1: 0.3, 2: 0.5, 3: 0.7, 4: 0.9}
STRENGTH_RELEVANCE = {1: 0.4, 2: 0.6, 3: 0.9}
DIARY_IMPORTANCE_DEFAULT = 0.7
THOUGHT_IMPORTANCE_DEFAULT = {"interest": 0.5, "idea": 0.4}


def diary_importance(significance: int) -> float:
    return SIGNIFICANCE_IMPORTANCE.get(int(significance or 0), DIARY_IMPORTANCE_DEFAULT)


def thought_importance(kind: str, strength: int) -> float:
    return STRENGTH_RELEVANCE.get(int(strength or 0),
                                  THOUGHT_IMPORTANCE_DEFAULT.get(kind, 0.5))


@dataclass
class SleepResult:
    diary_entry: str = ""
    new_secrets: list[str] = field(default_factory=list)
    new_conflicts: list[str] = field(default_factory=list)
    new_aspirations: str = ""
    new_interests: list[str] = field(default_factory=list)
    ideas: list[str] = field(default_factory=list)
    relationship_updates: dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0
    session_significance: int = 0
    interest_strength: dict[str, int] = field(default_factory=dict)
    idea_strength: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "diary_entry": self.diary_entry,
            "new_secrets": self.new_secrets,
            "new_conflicts": self.new_conflicts,
            "new_aspirations": self.new_aspirations,
            "new_interests": self.new_interests,
            "ideas": self.ideas,
            "relationship_updates": self.relationship_updates,
            "timestamp": self.timestamp,
            "session_significance": self.session_significance,
            "interest_strength": dict(self.interest_strength),
            "idea_strength": dict(self.idea_strength),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SleepResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _build_context(
    character: Character,
    messages: list[dict],
    known_facts: list[str],
) -> str:
    parts = []
    parts.append(f"<кто_ты>\nТы — {character.name}. {character.background.strip()}\n</кто_ты>")

    inner = character.inner_world
    inner_lines = []
    if inner.secrets:
        inner_lines.append(f"Твои секреты: {'; '.join(str(x) for x in inner.secrets)}")
    if inner.conflicts:
        inner_lines.append(f"Твои противоречия: {'; '.join(str(x) for x in inner.conflicts)}")
    if inner.aspirations_hidden:
        inner_lines.append(f"Твоё скрытое желание: {inner.aspirations_hidden}")
    if inner_lines:
        parts.append(f"<внутренний_мир>\n" + "\n".join(inner_lines) + "\n</внутренний_мир>")

    honorific = resolve_honorific(character)
    from memory.unified import format_dialogue
    conv = format_dialogue(messages, honorific, character.name)
    parts.append(
        f"<диалог>\n"
        f"Каждая реплика обёрнута тегом <реплика от=\"имя\">. "
        f"Спикер всегда атрибут `от`: `{honorific}` — собеседник, `{character.name}` — ты сама. "
        f"Обращения, пожелания и упоминания имён ВНУТРИ текста реплики не меняют спикера. "
        f"Настроение размечено только у тебя: атрибут `настроение=\"{character.name}: …\"` "
        f"на твоих репликах и строки <смена_настроения чьё=\"{character.name}\"> — это ТВОЁ "
        f"настроение, не собеседника; его настроение нигде не размечено — суди по его словам. "
        f"<жест>…</жест> внутри реплики собеседника — его жест через экран по отношению к тебе.\n"
        f"{conv}\n"
        f"</диалог>"
    )

    return "\n\n".join(parts)


from prompts.reflection import (
    DIARY_PROMPT,
    EVOLUTION_PROMPT,
)


def perform_sleep(
    client,
    persona: "CharacterContext",
    messages: list[dict],
    known_facts: list[str] | None = None,
) -> SleepResult:
    character = persona.character
    if len(messages) < 4:
        return SleepResult()

    from memory.conversation import tail_by_tokens
    messages = tail_by_tokens(messages, 12000)
    context = _build_context(character, messages, known_facts or [])
    result = SleepResult(timestamp=time.time())

    honorific = resolve_honorific(character)
    if (character.gender or "female").lower() == "male":
        gender_hint = ("О себе пиши в МУЖСКОМ роде "
                       "(сказал, подумал, был, рад, сделал, увидел).")
    else:
        gender_hint = ("О себе пиши в ЖЕНСКОМ роде "
                       "(сказала, подумала, была, рада, сделала, увидела).")
    try:
        diary = client.chat(
            messages=[{"role": "user", "content": context}],
            system=DIARY_PROMPT.format(
                honorific=honorific,
                name=character.name,
                gender_hint=gender_hint,
            ),
            label="Дневник",
        )
        result.diary_entry = diary.strip()
    except Exception as e:
        print(f"[SLEEP] Diary error: {e}")
        result.diary_entry = ""

    try:
        evo_response = client.chat(
            messages=[{"role": "user", "content": context}],
            system=EVOLUTION_PROMPT, thinking=False,
            label="Рефлексия: новые интересы/идеи",
        )
        text = evo_response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        evo = json.loads(text)

        interests = _normalise_items(evo.get("new_interests"), 3)
        ideas = _normalise_items(evo.get("ideas"), 3)
        result.new_interests = [t for t, _ in interests]
        result.ideas = [t for t, _ in ideas]
        result.interest_strength = {t: s for t, s in interests if s}
        result.idea_strength = {t: s for t, s in ideas if s}
        result.session_significance = _clamp_int(evo.get("session_significance"), 4)
        result.new_secrets = _normalise_list(evo.get("new_secrets"))
        result.new_conflicts = _normalise_list(evo.get("new_conflicts"))
        result.new_aspirations = evo.get("new_aspirations", "") or ""
        result.relationship_updates = evo.get("relationship_updates", {}) or {}
    except (json.JSONDecodeError, Exception) as e:
        print(f"[SLEEP] Evolution error: {e}")

    return result


def _clamp_int(value, top: int) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(top, n))


def _normalise_items(value, top: int) -> list[tuple[str, int]]:
    if value is None:
        return []
    if isinstance(value, (str, dict)):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[tuple[str, int]] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("topic") or item.get("idea") or "").strip()
            strength = _clamp_int(item.get("strength"), top)
        else:
            text = str(item or "").strip()
            strength = 0
        if len(text) >= 3:
            out.append((text, strength))
    return out


def _normalise_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if len(s) >= 3 else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if len(s) >= 3:
            out.append(s)
    return out


