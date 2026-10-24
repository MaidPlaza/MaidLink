from dataclasses import dataclass, field
from pathlib import Path

import yaml


CURRENT_GENERATION = "Link"
KNOWN_GENERATIONS = (CURRENT_GENERATION,)

DEFAULT_LANGUAGE = "ru"
KNOWN_LANGUAGES = (DEFAULT_LANGUAGE,)


def registry_number(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def passport_issues(data: dict, *, require_generation: bool = False,
                    require_language: bool = False) -> list[str]:
    issues = []
    number = data.get("number")
    if number is not None and registry_number(number) is None:
        issues.append(f"number: целое ≥ 1 без кавычек и нулей впереди, а не {number!r}")
    gen = data.get("generation")
    if gen is None:
        if require_generation:
            issues.append(f"нет generation (текущее поколение — {CURRENT_GENERATION})")
    elif not isinstance(gen, str) or gen.strip() not in KNOWN_GENERATIONS:
        issues.append(f"generation: одно из {list(KNOWN_GENERATIONS)}, а не {gen!r}")
    lang = data.get("language")
    if lang is None:
        if require_language:
            issues.append(f"нет language (код языка ISO 639-1, сейчас — {DEFAULT_LANGUAGE})")
    elif not isinstance(lang, str) or lang.strip() not in KNOWN_LANGUAGES:
        issues.append(f"language: одно из {list(KNOWN_LANGUAGES)}, а не {lang!r}")
    return issues


_PROFANITY_KINDS = {
    "mat": "mat", "мат": "mat",
    "crude": "crude", "просторечие": "crude", "крепкое": "crude",
    "slang": "slang", "сленг": "slang",
    "euphemism": "euphemism", "эвфемизмы": "euphemism", "эвфемизм": "euphemism",
    "stylized": "stylized", "стилизованные": "stylized", "проклятия": "stylized",
}
_PROFANITY_TARGETS = {
    "world": "world", "мир": "world", "обстоятельства": "world",
    "banter": "banter", "подначка": "banter", "собеседник": "banter",
}


def _parse_profanity(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = {"level": raw}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k, v in raw.items():
        if k == "detect":
            out["detect"] = [str(x).strip().lower() for x in (v or []) if str(x).strip()]
        else:
            out[str(k)] = str(v).strip() if v is not None else ""
    level = (out.get("level") or "none").strip().lower()
    out["level"] = level
    kind = _PROFANITY_KINDS.get((out.get("kind") or "").strip().lower())
    out["kind"] = kind or ("mat" if level == "strong" else "crude")
    out["target"] = _PROFANITY_TARGETS.get((out.get("target") or "").strip().lower(), "world")
    out["from_tier"] = (out.get("from_tier") or "distant").strip().lower()
    return out


@dataclass
class SpeakingStyle:
    honorific: str = "Господин"
    sentence_endings: list[str] = field(default_factory=lambda: ["~", "!"])
    speech_level: str = "polite"
    quirks: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    seals: list[str] = field(default_factory=list)
    pet_names: list[str] = field(default_factory=list)
    profanity: dict = field(default_factory=dict)
    address_form: str = ""
    address_form_intimate: str = ""


@dataclass
class Capabilities:
    description: str = ""
    rules: list[str] = field(default_factory=list)


@dataclass
class EmotionalTrigger:
    trigger: str = ""
    affects: dict[str, float] = field(default_factory=dict)
    multiplier: float = 1.0


@dataclass
class ArchetypeReaction:
    trigger: str = ""
    response: str = ""


@dataclass
class AxisLevel:
    value: float = 0.5
    text: str = ""
    example: str = ""


@dataclass
class SpeechEvolutionQuirk:
    kind: str = "gradient"
    driven_by: str = "rel_me_to_master"
    forms: dict[str, str] = field(default_factory=dict)
    active_tiers: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class Vulnerability:
    topic: str = ""
    reaction: str = ""


@dataclass
class AxisRange:
    min: float | None = None
    max: float | None = None

    def contains(self, value: float) -> bool:
        if self.min is not None and value < self.min:
            return False
        if self.max is not None and value > self.max:
            return False
        return True


@dataclass
class ConditionalVulnerability:
    id: str
    text: str
    description: str = ""
    axis_range: dict[str, AxisRange] = field(default_factory=dict)
    trigger_signals: list[str] = field(default_factory=list)
    effect: str = ""
    mood: list[str] = field(default_factory=list)
    ttl_days: float = 0.0
    universal: bool = False


@dataclass
class ConditionalVulnerabilities:
    opt_in: list[str] = field(default_factory=list)
    custom: list[ConditionalVulnerability] = field(default_factory=list)


@dataclass
class ConditionalStrength:
    id: str
    text: str
    description: str = ""
    axis_range: dict[str, AxisRange] = field(default_factory=dict)
    trigger_signals: list[str] = field(default_factory=list)
    effect: str = ""
    mood: list[str] = field(default_factory=list)
    ttl_days: float = 0.0


@dataclass
class ConditionalStrengths:
    opt_in: list[str] = field(default_factory=list)
    custom: list[ConditionalStrength] = field(default_factory=list)


MECHANIC_RANGES: dict[str, tuple[float, float]] = {"progression_speed": (0.25, 3.0)}


def _clamp_mechanic(key: str, v: float) -> float:
    lo, hi = MECHANIC_RANGES.get(key, (0.0, 1.0))
    return max(lo, min(hi, v))


@dataclass
class CharacterScenarios:
    traits: list[str] = field(default_factory=list)
    disable: list[str] = field(default_factory=list)
    custom: list[dict] = field(default_factory=list)


CharacterScenes = CharacterScenarios


@dataclass
class ActiveTrait:
    trait_id: str
    activated_at: float
    source_event: str = ""

    def to_dict(self) -> dict:
        return {
            "trait_id": self.trait_id,
            "activated_at": self.activated_at,
            "source_event": self.source_event,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActiveTrait":
        return cls(
            trait_id=data.get("trait_id", ""),
            activated_at=float(data.get("activated_at", 0.0)),
            source_event=data.get("source_event", ""),
        )


@dataclass
class InnerWorld:
    aspirations_visible: str = ""
    aspirations_hidden: str = ""
    secrets: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class Relationship:
    name: str = ""
    attitude: str = ""
    notes: str = ""


@dataclass
class OutfitPolicy:
    tag_tier_gates: dict[str, str] = field(default_factory=dict)
    blocked_tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> "OutfitPolicy":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            tag_tier_gates={
                str(k): str(v) for k, v in (data.get("tag_tier_gates") or {}).items()
            },
            blocked_tags=[str(t) for t in (data.get("blocked_tags") or [])],
        )

    def to_dict(self) -> dict:
        return {
            "tag_tier_gates": dict(self.tag_tier_gates),
            "blocked_tags": list(self.blocked_tags),
        }


@dataclass
class MoodStyle:
    tone: str = ""
    examples: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: "dict | None") -> "MoodStyle":
        if not isinstance(data, dict):
            return cls()
        return cls(
            tone=(data.get("tone") or "").strip(),
            examples=[str(e).strip()
                      for e in (data.get("examples") or []) if str(e).strip()],
        )


@dataclass
class Character:
    name: str
    archetype: str
    speaking_style: SpeakingStyle
    personality_base: dict[str, float]
    background: str
    behavioral_rules: list[str]
    capabilities: Capabilities = field(default_factory=Capabilities)
    archetype_intensity: float = 0.7
    appearance: str = ""
    age: str = ""
    compact_prompt: bool = False
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    emotional_triggers: list[EmotionalTrigger] = field(default_factory=list)
    archetype_reactions: list[ArchetypeReaction] = field(default_factory=list)
    axis_levels: dict[str, list[AxisLevel]] = field(default_factory=dict)
    axis_initial_values: dict[str, float] = field(default_factory=dict)
    frozen_axes: set[str] = field(default_factory=set)
    axis_min_values: dict[str, float] = field(default_factory=dict)
    axis_max_values: dict[str, float] = field(default_factory=dict)
    axis_bands: dict[str, float] = field(default_factory=dict)
    relationship_axis_levels: dict[str, list[AxisLevel]] = field(default_factory=dict)
    relationship_axis_initial_values: dict[str, float] = field(default_factory=dict)
    mechanic_thresholds: dict[str, float] = field(default_factory=dict)
    speech_style_evolution: list[SpeechEvolutionQuirk] = field(default_factory=list)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    conditional_vulnerabilities: ConditionalVulnerabilities = field(
        default_factory=ConditionalVulnerabilities
    )
    conditional_strengths: ConditionalStrengths = field(
        default_factory=ConditionalStrengths
    )
    scenarios: CharacterScenarios = field(default_factory=CharacterScenarios)
    outfit_policy: OutfitPolicy = field(default_factory=OutfitPolicy)
    inner_world: InnerWorld = field(default_factory=InnerWorld)
    relationships: list[Relationship] = field(default_factory=list)
    core_identity: str = ""
    character_axes: dict[str, dict] = field(default_factory=dict)
    mood_styles: dict[str, MoodStyle] = field(default_factory=dict)
    mood_temperament: str = ""
    mood_profile: dict[str, str] = field(default_factory=dict)
    draw_ideas: dict[str, list[str]] = field(default_factory=dict)
    avatar_portrait: str = ""
    avatar_chat: str = ""
    accent_color: str = ""
    subtitle: str = ""
    short_description: str = ""
    profile_description: str = ""
    number: int | None = None
    generation: str = CURRENT_GENERATION
    language: str = DEFAULT_LANGUAGE
    use_actions: bool = True
    gender: str = "female"
    user_gender: str = "male"
    response_style: str = ""
    prompt_overrides: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Character":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        style_data = data.get("speaking_style", {})
        style = SpeakingStyle(
            honorific=style_data.get("honorific", "Господин"),
            sentence_endings=style_data.get("sentence_endings", ["~", "!"]),
            speech_level=style_data.get("speech_level", "polite"),
            quirks=style_data.get("quirks", []),
            markers=[str(m).strip() for m in (style_data.get("markers") or [])
                     if str(m).strip()],
            seals=[str(m).strip() for m in (style_data.get("seals") or [])
                   if str(m).strip()],
            pet_names=[str(m).strip() for m in (style_data.get("pet_names") or [])
                       if str(m).strip()],
            profanity=_parse_profanity(style_data.get("profanity")),
            address_form=(style_data.get("address_form", "") or "").strip(),
            address_form_intimate=(style_data.get("address_form_intimate", "") or "").strip(),
        )

        caps_data = data.get("capabilities", {})
        caps = Capabilities(
            description=caps_data.get("description", ""),
            rules=caps_data.get("rules", []),
        )

        triggers = [
            EmotionalTrigger(
                trigger=t.get("trigger", ""),
                affects=t.get("affects", {}),
                multiplier=t.get("multiplier", 1.0),
            )
            for t in data.get("emotional_triggers", [])
        ]

        archetype_reactions = [
            ArchetypeReaction(
                trigger=r.get("trigger", ""),
                response=r.get("response", ""),
            )
            for r in data.get("archetype_reactions", [])
            if r.get("trigger") and r.get("response")
        ]

        axis_levels: dict[str, list[AxisLevel]] = {}
        axis_initial_values: dict[str, float] = {}
        axis_min_values: dict[str, float] = {}
        axis_max_values: dict[str, float] = {}
        axis_bands: dict[str, float] = {}
        frozen_axes: set[str] = set()
        for axis_name, body in (data.get("character_axes") or {}).items():
            if not isinstance(body, dict):
                continue
            init = body.get("initial_value")
            if init is not None:
                try:
                    axis_initial_values[axis_name] = max(0.0, min(1.0, float(init)))
                except (TypeError, ValueError):
                    pass
            if body.get("frozen"):
                frozen_axes.add(axis_name)
            min_v = body.get("min_value")
            if min_v is not None:
                try:
                    axis_min_values[axis_name] = max(0.0, min(1.0, float(min_v)))
                except (TypeError, ValueError):
                    pass
            max_v = body.get("max_value")
            if max_v is not None:
                try:
                    axis_max_values[axis_name] = max(0.0, min(1.0, float(max_v)))
                except (TypeError, ValueError):
                    pass
            band = body.get("band")
            if band is not None:
                try:
                    axis_bands[axis_name] = max(0.0, min(0.5, float(band)))
                except (TypeError, ValueError):
                    pass
            raw_levels = body.get("levels") or []
            parsed: list[AxisLevel] = []
            for entry in raw_levels:
                if not isinstance(entry, dict):
                    continue
                try:
                    val = float(entry.get("value"))
                except (TypeError, ValueError):
                    continue
                text = (entry.get("text") or "").strip()
                if not text:
                    continue
                example = (entry.get("example") or "").strip()
                parsed.append(AxisLevel(value=max(0.0, min(1.0, val)), text=text, example=example))
            if parsed:
                parsed.sort(key=lambda lvl: lvl.value)
                axis_levels[axis_name] = parsed

        rel_axis_levels: dict[str, list[AxisLevel]] = {}
        rel_axis_initial_values: dict[str, float] = {}
        for axis_name, body in (data.get("relationship_axes") or {}).items():
            if not isinstance(body, dict):
                continue
            init = body.get("initial_value")
            if init is not None:
                try:
                    rel_axis_initial_values[axis_name] = max(0.0, min(1.0, float(init)))
                except (TypeError, ValueError):
                    pass
            parsed_r: list[AxisLevel] = []
            for entry in (body.get("levels") or []):
                if not isinstance(entry, dict):
                    continue
                try:
                    val = float(entry.get("value"))
                except (TypeError, ValueError):
                    continue
                text = (entry.get("text") or "").strip()
                if not text:
                    continue
                parsed_r.append(AxisLevel(value=max(0.0, min(1.0, val)), text=text))
            if parsed_r:
                parsed_r.sort(key=lambda lvl: lvl.value)
                rel_axis_levels[axis_name] = parsed_r

        speech_evolution: list[SpeechEvolutionQuirk] = []
        for q in (data.get("speech_style_evolution") or []):
            if not isinstance(q, dict):
                continue
            kind = (q.get("kind") or "gradient").strip().lower()
            driven_by = (q.get("driven_by") or "rel_me_to_master").strip()

            if kind == "gradient":
                _legacy_form_keys = {"низкая": "low", "средняя": "medium", "высокая": "high"}
                forms_raw = q.get("forms") or {}
                forms = {}
                for k, v in forms_raw.items():
                    if not str(v).strip():
                        continue
                    key = str(k).strip()
                    forms[_legacy_form_keys.get(key, key)] = str(v).strip()
                if forms and driven_by:
                    speech_evolution.append(SpeechEvolutionQuirk(
                        kind="gradient",
                        driven_by=driven_by,
                        forms=forms,
                    ))
            elif kind == "tier_specific":
                active_tiers = [str(t).strip() for t in (q.get("active_tiers") or []) if str(t).strip()]
                text = (q.get("text") or "").strip()
                if active_tiers and text:
                    speech_evolution.append(SpeechEvolutionQuirk(
                        kind="tier_specific",
                        driven_by="rel_me_to_master",
                        active_tiers=active_tiers,
                        text=text,
                    ))

        vulns = [
            Vulnerability(topic=v.get("topic", ""), reaction=v.get("reaction", ""))
            for v in data.get("vulnerabilities", [])
        ]

        cv_data = data.get("conditional_vulnerabilities") or {}
        cv_opt_in = list(cv_data.get("opt_in") or [])
        cv_custom_raw = cv_data.get("custom") or []
        cv_custom: list[ConditionalVulnerability] = []
        for entry in cv_custom_raw:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            ar_raw = entry.get("axis_range") or {}
            axis_range: dict[str, AxisRange] = {}
            for axis_name, bounds in ar_raw.items():
                if not isinstance(bounds, dict):
                    continue
                axis_range[axis_name] = AxisRange(
                    min=bounds.get("min"),
                    max=bounds.get("max"),
                )
            cv_custom.append(ConditionalVulnerability(
                id=entry["id"],
                text=entry.get("text", ""),
                axis_range=axis_range,
                trigger_signals=list(entry.get("trigger_signals") or []),
                effect=entry.get("effect", ""),
                ttl_days=float(entry.get("ttl_days") or 0.0),
            ))
        conditional_vulns = ConditionalVulnerabilities(
            opt_in=cv_opt_in,
            custom=cv_custom,
        )

        cs_data = data.get("conditional_strengths") or {}
        cs_opt_in = list(cs_data.get("opt_in") or [])
        cs_custom_raw = cs_data.get("custom") or []
        cs_custom: list[ConditionalStrength] = []
        for entry in cs_custom_raw:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            ar_raw = entry.get("axis_range") or {}
            axis_range: dict[str, AxisRange] = {}
            for axis_name, bounds in ar_raw.items():
                if not isinstance(bounds, dict):
                    continue
                axis_range[axis_name] = AxisRange(
                    min=bounds.get("min"),
                    max=bounds.get("max"),
                )
            cs_custom.append(ConditionalStrength(
                id=entry["id"],
                text=entry.get("text", ""),
                axis_range=axis_range,
                trigger_signals=list(entry.get("trigger_signals") or []),
                effect=entry.get("effect", ""),
                ttl_days=float(entry.get("ttl_days") or 0.0),
            ))
        conditional_strengths = ConditionalStrengths(
            opt_in=cs_opt_in,
            custom=cs_custom,
        )

        sc_data = (data.get("scenarios") or data.get("scenes")
                   or data.get("events") or {})
        scenarios = CharacterScenarios(
            traits=[str(x).strip() for x in (sc_data.get("traits") or []) if str(x).strip()],
            disable=[str(x) for x in (sc_data.get("disable") or []) if x],
            custom=[e for e in (sc_data.get("custom") or []) if isinstance(e, dict)],
        )

        inner_data = data.get("inner_world", {})
        inner = InnerWorld(
            aspirations_visible=inner_data.get("aspirations_visible", ""),
            aspirations_hidden=inner_data.get("aspirations_hidden", ""),
            secrets=inner_data.get("secrets", []),
            conflicts=inner_data.get("conflicts", []),
        )

        rels_data = data.get("relationships", {})
        rels = [
            Relationship(name=name, attitude=info.get("attitude", ""), notes=info.get("notes", ""))
            for name, info in rels_data.items()
        ]

        from persona.mood import migrate_state
        ms_raw = data.get("mood_styles") or {}
        mood_styles: dict[str, MoodStyle] = {}
        for state, ms_data in sorted(ms_raw.items(),
                                     key=lambda kv: migrate_state(kv[0]) != kv[0],
                                     reverse=True):
            if isinstance(ms_data, dict):
                mood_styles[migrate_state(state)] = MoodStyle.from_dict(ms_data)

        return cls(
            name=data["name"],
            archetype=data.get("archetype", ""),
            speaking_style=style,
            personality_base=data.get("personality_base", {}),
            background=data.get("background", ""),
            behavioral_rules=data.get("behavioral_rules", []),
            capabilities=caps,
            archetype_intensity=data.get("archetype_intensity", 0.7),
            appearance=data.get("appearance", ""),
            age=data.get("age", ""),
            compact_prompt=data.get("compact_prompt", False),
            likes=data.get("likes", []),
            dislikes=data.get("dislikes", []),
            emotional_triggers=triggers,
            archetype_reactions=archetype_reactions,
            axis_levels=axis_levels,
            axis_initial_values=axis_initial_values,
            frozen_axes=frozen_axes,
            axis_min_values=axis_min_values,
            axis_max_values=axis_max_values,
            axis_bands=axis_bands,
            relationship_axis_levels=rel_axis_levels,
            relationship_axis_initial_values=rel_axis_initial_values,
            speech_style_evolution=speech_evolution,
            vulnerabilities=vulns,
            conditional_vulnerabilities=conditional_vulns,
            conditional_strengths=conditional_strengths,
            scenarios=scenarios,
            outfit_policy=OutfitPolicy.from_dict(data.get("outfit_policy")),
            inner_world=inner,
            relationships=rels,
            core_identity=data.get("core_identity", ""),
            avatar_portrait=data.get("avatar_portrait", ""),
            avatar_chat=data.get("avatar_chat", ""),
            accent_color=data.get("accent_color", ""),
            subtitle=data.get("subtitle", ""),
            short_description=data.get("short_description", ""),
            profile_description=str(data.get("profile_description", "") or "").strip(),
            number=registry_number(data.get("number")),
            generation=str(data.get("generation") or "").strip() or CURRENT_GENERATION,
            language=str(data.get("language") or "").strip() or DEFAULT_LANGUAGE,
            use_actions=data.get("use_actions", True),
            gender=data.get("gender", "female"),
            user_gender=data.get("user_gender", "male"),
            response_style=data.get("response_style", ""),
            prompt_overrides=data.get("prompt_overrides", ""),
            character_axes=data.get("character_axes", {}),
            mood_styles=mood_styles,
            mood_temperament=data.get("mood_temperament", ""),
            mood_profile={
                str(k).strip(): str(v).strip()
                for k, v in (data.get("mood_profile") or {}).items()
                if str(v or "").strip()
            },
            draw_ideas={
                k: [str(x) for x in ((data.get("draw_ideas") or {}).get(k) or []) if x]
                for k in ("fits", "avoid")
                if isinstance(data.get("draw_ideas"), dict)
            },
            mechanic_thresholds={
                str(k): _clamp_mechanic(str(k), float(v))
                for k, v in (data.get("mechanic_thresholds") or {}).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            },
        )
