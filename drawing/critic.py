from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Verdict:
    verdict: str
    issues: list[str] = field(default_factory=list)
    severity: str = "minor"
    regen_hint: str | None = None
    confidence: float = 0.5
    raw_response: str = ""

    def should_regen(self, soft_threshold: float) -> bool:
        if self.verdict == "reject":
            return True
        if self.verdict != "regen":
            return False
        if self.severity == "minor":
            return False
        return self.confidence >= soft_threshold


VERDICT_OK = "ok"
VERDICT_REGEN = "regen"
VERDICT_REJECT = "reject"
VALID_VERDICTS = {VERDICT_OK, VERDICT_REGEN, VERDICT_REJECT}


class VisionCritic:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def judge(
        self,
        image_path: Path,
        *,
        expected_outfit: str = "",
        expected_scene: str = "",
        expected_pose: str = "",
        max_rating: str = "sfw",
    ) -> Verdict:
        try:
            img_bytes = image_path.read_bytes()
        except OSError as e:
            return Verdict(
                verdict=VERDICT_OK, confidence=0.0,
                issues=[f"не удалось прочитать файл: {e}"],
                raw_response="(read error)",
            )
        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        system_prompt = self._build_system_prompt(
            expected_outfit=expected_outfit,
            expected_scene=expected_scene,
            expected_pose=expected_pose,
            max_rating=max_rating,
        )

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Проверь эту картинку и дай verdict."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
            ],
        }]

        try:
            response = self.llm_client.chat(
                messages=messages,
                system=system_prompt,
                thinking=False,
                label="Vision critic",
            )
        except Exception as e:
            print(f"[critic] LLM error: {e}; считаем ok чтобы не блокировать")
            return Verdict(
                verdict=VERDICT_OK, confidence=0.0,
                issues=[f"vision LLM error: {type(e).__name__}"],
                raw_response="(LLM error)",
            )

        return _parse_verdict(response)

    @staticmethod
    def _build_system_prompt(
        *,
        expected_outfit: str,
        expected_scene: str,
        expected_pose: str,
        max_rating: str,
    ) -> str:
        nsfw_warn = ""
        if max_rating == "sfw":
            nsfw_warn = (
                "\n  - ВАЖНО: текущий NSFW-уровень = sfw. Если на картинке "
                "проскочило что-то откровенное (обнажённость, эротическая поза) — "
                "это reject с severity=major."
            )
        elif max_rating == "suggestive":
            nsfw_warn = (
                "\n  - NSFW-уровень = suggestive. Лёгкая обнажённость допустима, "
                "явная эротика — reject."
            )
        return f"""Ты — критик изображения. Тебе показывают картинку и описание что должно быть.

Твоя задача — оценить:
  1. Анатомические артефакты (лишние/потерянные пальцы, искажённое лицо, склейки)
  2. Соответствие описанию (тот ли костюм, сцена, поза)
  3. NSFW-проскоки (если запрашивался sfw, а на картинке откровенность){nsfw_warn}

<ожидалось>
  Костюм: {expected_outfit or "(не указан)"}
  Сцена:  {expected_scene or "(не указана)"}
  Поза:   {expected_pose or "(не указана)"}
</ожидалось>

<возможные_verdict>
  "ok"     — картинка нормальная, отдаём как есть
  "regen"  — есть видимая проблема (артефакт / несоответствие), стоит перегенерировать
  "reject" — severe (NSFW проскок где запрещено, грубая аномалия) — обязательно регенерируем
</возможные_verdict>

<правила>
  - Будь СНИСХОДИТЕЛЕН. Картинка не обязана 100% совпадать с описанием —
    модель не perfect, мелкие расхождения — норма.
  - severity ВАЖНА (определяет будет ли retry):
    * severity="major" — БЛОКИРУЮЩЕЕ (triggers retry):
        - Анатомия: лишние/отсутствующие пальцы, искажённое лицо, склейки
        - NSFW проскок где запрещено
        - КОСТЮМ КАТЕГОРИЧЕСКИ НЕ ТОТ: ожидался maid (фартук+чепчик),
          а нарисован casual T-shirt; ожидался формальный, а пляжный, и т.п.
          Это касается КЛЮЧЕВОГО типа одежды, не деталей.
    * severity="minor" — НЕ блокирующее (retry не будет):
        - Поза слегка не та (looking_back → стоит в профиль)
        - Детали костюма отличаются (тот же класс одежды, но другой цвет/крой)
        - "Виден только торс вместо по пояс" — framing
        - Фон проще ожидаемого (вместо library — нейтральный)
        - Жест/предмет не совпал (heart_hands не получился — рисунок норм без)
  - КОСТЮМ vs ДЕТАЛИ КОСТЮМА:
        ожидался "maid_classic" → нарисован цивильный кэжуал = MAJOR
        ожидался "maid_classic" → нарисован maid но без чепчика = MINOR
        ожидался "sundress" → нарисовано летнее платье другого фасона = MINOR (тот же класс)
        ожидался "yukata_summer" → нарисовано вестерн платье = MAJOR
  - НАЗВАНИЕ ассета может быть поэтичным/собственным («Морозная форма») и НЕ
    описывать вид. Сверяй картинку с частью «(выглядит как: …)» — это и есть
    ожидаемый вид. Совпадает с ней → костюм ТОТ, что бы ни значило название.
  - Поза или руки, СКРЫТЫЕ кадрированием (например «руки за спиной» при поясном
    кадре — рук просто не видно), — НЕ несоответствие. Несоответствие позы —
    только когда видно ЯВНО другое.
  - Если ты в сомнениях между minor и major — выбирай minor.
  - confidence — уверенность в самом вердикте (0.0-1.0). Низкий если сомневаешься.
</правила>

<формат>
Ответь СТРОГО JSON-объектом:
{{"verdict": "ok" | "regen" | "reject",
  "issues": ["короткое описание проблемы 1", ...],
  "severity": "minor" | "major",
  "regen_hint": "подсказка для следующей попытки" | null,
  "confidence": 0.0..1.0}}
</формат>
"""


_MD_CODEBLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_json(text: str) -> str | None:
    if not text:
        return None
    m = _MD_CODEBLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return None


def _parse_verdict(response: str) -> Verdict:
    raw = _extract_json(response)
    if raw is None:
        return Verdict(
            verdict=VERDICT_OK, confidence=0.0,
            issues=["в ответе критика не найден JSON"],
            raw_response=response[:500],
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return Verdict(
            verdict=VERDICT_OK, confidence=0.0,
            issues=[f"невалидный JSON в ответе критика: {e}"],
            raw_response=response[:500],
        )

    verdict_str = str(data.get("verdict", "")).lower().strip()
    if verdict_str not in VALID_VERDICTS:
        return Verdict(
            verdict=VERDICT_OK, confidence=0.0,
            issues=[f"неизвестный verdict: {verdict_str!r}"],
            raw_response=response[:500],
        )

    issues_raw = data.get("issues") or []
    issues = [str(i) for i in issues_raw if i] if isinstance(issues_raw, list) else []

    severity = str(data.get("severity", "minor")).lower().strip()
    if severity not in ("minor", "major"):
        severity = "minor"

    regen_hint = data.get("regen_hint")
    if regen_hint is not None:
        regen_hint = str(regen_hint).strip() or None

    try:
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    return Verdict(
        verdict=verdict_str,
        issues=issues,
        severity=severity,
        regen_hint=regen_hint,
        confidence=confidence,
        raw_response=response[:500],
    )


def request_apology(llm_client, *, system_prompt: str,
                    refusal_style_hint: str | None = None) -> str:
    style_line = f"\nСтиль отказа: {refusal_style_hint}" if refusal_style_hint else ""
    user = (
        "Ты только что попыталась нарисовать картинку, но результат не получился "
        "хорошим (артефакты, проблемы с композицией). Скажи это пользователю в своём "
        "стиле — 1-2 фразы. Не извиняйся формально, не объясняй технические причины; "
        f"просто что сегодня не вышло красиво, может попробуем позже.{style_line} "
        "Не начинай со своего имени."
    )
    try:
        response = llm_client.chat(
            messages=[{"role": "user", "content": user}],
            system=system_prompt, thinking=False, label="Drawing: apology",
        )
        return (response or "").strip()
    except Exception as e:
        print(f"[critic] apology LLM error: {e}")
        return "Что-то у меня сегодня не получается красиво нарисовать — давай попробуем позже."
