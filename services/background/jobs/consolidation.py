from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from persona.character_context import resolve_honorific
from services.background.jobs.base import (
    BackgroundJob,
    JobContext,
    JobResult,
)


from prompts.reflection import (
    CONSOLIDATION_PROMPT,
)


@dataclass(frozen=True)
class ConsolidationConfig:
    hard_min_interval_sec: float = 1 * 3600

    min_interval_sec: float = 24 * 3600

    importance_threshold: float = 2.5

    max_reflections: int = 20

    min_reflections: int = 3


class MemoryConsolidationJob(BackgroundJob):
    name = "memory_consolidation"
    requires_llm = True
    min_interval_sec = 24 * 3600
    estimated_duration_sec = 30.0
    status_label = "SLEEPING"
    status_priority = 2
    status_reason = "обдумывает воспоминания"

    def __init__(self, config: ConsolidationConfig = ConsolidationConfig()) -> None:
        self._cfg = config
        self.min_interval_sec = config.min_interval_sec

    def should_run(self, ctx: JobContext) -> bool:
        age = time.time() - ctx.last_run_at
        if age < self._cfg.hard_min_interval_sec:
            return False

        importance_sum = self._fresh_importance_sum(ctx)
        if importance_sum >= self._cfg.importance_threshold:
            return True

        return age >= self._cfg.min_interval_sec

    def _fresh_importance_sum(self, ctx: JobContext) -> float:
        state = ctx.state
        memory = state.get("memory")
        if memory is None:
            return 0.0
        threshold = ctx.last_run_at
        total = 0.0
        for r in getattr(memory, "records", []):
            if getattr(r, "type", "") != "рефлексия":
                continue
            if getattr(r, "is_forgotten", False):
                continue
            if (r.created_at or 0.0) <= threshold:
                continue
            total += float(getattr(r, "importance", 0.0) or 0.0)
        return total

    async def run(self, ctx: JobContext) -> JobResult:
        state = ctx.state
        memory = state.get("memory")
        character = state.get("character")
        identity = state.get("identity")
        client = state.get("client")

        if memory is None or character is None or client is None:
            return JobResult.skipped(reason="state incomplete (no memory/character/client)")

        fresh_refls = self._collect_fresh_reflections(ctx)
        if len(fresh_refls) < self._cfg.min_reflections:
            return JobResult.skipped(
                reason=f"too few new reflections ({len(fresh_refls)} < {self._cfg.min_reflections})",
                fresh_count=len(fresh_refls),
            )

        if ctx.should_abort():
            return JobResult.aborted("analyzer stop before LLM call")

        material_text = self._render_material(fresh_refls, identity)
        honorific = resolve_honorific(character)
        if (character.gender or "female").lower() == "male":
            gender_hint = ("О себе пиши в МУЖСКОМ роде "
                           "(сказал, подумал, был, рад, сделал, увидел).")
        else:
            gender_hint = ("О себе пиши в ЖЕНСКОМ роде "
                           "(сказала, подумала, была, рада, сделала, увидела).")
        system_prompt = CONSOLIDATION_PROMPT.format(
            char_name=character.name,
            honorific=honorific,
            gender_hint=gender_hint,
        )

        import asyncio
        loop = asyncio.get_event_loop()
        ctx.log(f"calling LLM (material: {len(fresh_refls)} reflections, "
                f"~{len(material_text)} chars)")
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.chat(
                    messages=[{"role": "user", "content": material_text}],
                    system=system_prompt,
                    thinking=True,
                    label="Memory consolidation",
                ),
            )
        except Exception as e:
            return JobResult.failed(f"LLM call: {type(e).__name__}: {e}")

        if ctx.should_abort():
            return JobResult.aborted("analyzer stop after LLM call")

        from memory.unified import _parse_llm_json
        data = _parse_llm_json(response or "")
        if data is None:
            return JobResult.failed(f"invalid JSON: {(response or '')[:200]}")

        patterns = data.get("patterns") or []
        diary = (data.get("diary") or "").strip()
        if not isinstance(patterns, list):
            patterns = []

        saved_patterns = 0
        for p in patterns:
            if not isinstance(p, dict):
                continue
            title = (p.get("title") or "").strip()
            description = (p.get("description") or "").strip()
            if not title or not description:
                continue
            memory.add_record(
                type="обобщение",
                title=title,
                details={
                    "description": description,
                    "source": "consolidation",
                    "consolidated_at": time.time(),
                },
                importance=0.6,
                embed_text=f"{title}\n{description}",
            )
            saved_patterns += 1

        saved_diary = False
        if diary:
            memory.add_reflection(diary, 0.7, "diary_consolidation")
            saved_diary = True

        topic_views = 0
        persona = state.get("persona")
        if persona is not None:
            try:
                from memory.topic_extraction import form_topic_opinions_from_material
                tv = await loop.run_in_executor(
                    None, lambda: form_topic_opinions_from_material(
                        client, persona, memory, material_text))
                topic_views = int((tv or {}).get("saved", 0))
                if topic_views:
                    ctx.log(f"topic opinions formed: {topic_views}")
            except Exception as e:
                ctx.log(f"WARN topic opinions failed: {e!r}")

        inferred_prefs = {"general": 0, "entity": 0, "topic": 0}
        try:
            inferred_prefs = await loop.run_in_executor(
                None, lambda: memory.infer_preferences_from_material(material_text, honorific))
            if any(inferred_prefs.values()):
                ctx.log(f"inferred preferences: {inferred_prefs}")
        except Exception as e:
            ctx.log(f"WARN infer preferences failed: {e!r}")

        if (saved_patterns == 0 and not saved_diary and topic_views == 0
                and not any(inferred_prefs.values())):
            return JobResult.skipped(
                reason="LLM returned no usable patterns or diary",
                response_preview=(response or "")[:100],
            )

        try:
            cleaned = await loop.run_in_executor(
                None, lambda: memory.consolidate_preferences_rules(honorific))
            if cleaned.get("changed"):
                ctx.log(f"prefs/rules cleanup: {cleaned}")
        except Exception as e:
            ctx.log(f"WARN prefs/rules cleanup failed: {e!r}")

        try:
            ctx.save_memory()
        except Exception as e:
            ctx.log(f"WARN save_memory failed: {e!r}")

        ctx.log(f"OK: {saved_patterns} pattern(s), diary={'yes' if saved_diary else 'no'}, "
                f"topic_views={topic_views}, inferred_prefs={inferred_prefs}")
        return JobResult.ok(
            patterns=saved_patterns,
            diary=saved_diary,
            topic_views=topic_views,
            inferred_prefs=inferred_prefs,
            material_reflections=len(fresh_refls),
            material_importance_sum=round(self._fresh_importance_sum(ctx), 2),
        )

    def _collect_fresh_reflections(self, ctx: JobContext) -> list[Any]:
        memory = ctx.state.get("memory")
        if memory is None:
            return []
        threshold = ctx.last_run_at
        refls = [
            r for r in getattr(memory, "records", [])
            if getattr(r, "type", "") == "рефлексия"
            and not getattr(r, "is_forgotten", False)
            and (r.created_at or 0.0) > threshold
        ]
        refls.sort(key=lambda r: r.created_at or 0.0)
        return refls[: self._cfg.max_reflections]

    def _render_material(self, refls: list[Any], identity: Any) -> str:
        try:
            from memory.unified import relative_time as _rt
            relative_time = _rt
        except ImportError:
            relative_time = lambda _t: ""

        lines = ["<рефлексии>"]
        for r in refls:
            ts = relative_time(r.created_at) if r.created_at else ""
            desc = (
                r.details.get("description")
                or r.details.get("brief")
                or r.title
            )
            prefix = f"({ts}) " if ts else ""
            lines.append(f"- {prefix}{desc}")
        lines.append("</рефлексии>")

        last_summary = ""
        last_mood = ""
        if identity is not None:
            last_summary = getattr(identity, "last_session_summary", "") or ""
            last_mood = getattr(identity, "last_session_mood", "") or ""
        if last_summary or last_mood:
            lines.append("")
            lines.append("<последняя_сессия>")
            if last_summary:
                lines.append(f"Сводка: {last_summary}")
            if last_mood:
                lines.append(f"Настроение: {last_mood}")
            lines.append("</последняя_сессия>")

        return "\n".join(lines)
