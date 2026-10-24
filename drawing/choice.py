from __future__ import annotations

from dataclasses import dataclass, field

from drawing.assets import VALID_ASPECTS, DEFAULT_ASPECT


class ChoiceValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Choice:
    outfit_id: str = ""
    scene_id: str = ""
    pose_id: str = ""
    modifiers: dict[str, str] = field(default_factory=dict)
    aspect: str = ""
    requested_unavailable: bool = False
    refusal_reason: str | None = None

    def is_refusal(self) -> bool:
        return self.requested_unavailable or bool(self.refusal_reason)

    def is_generate(self) -> bool:
        return (
            not self.requested_unavailable
            and not self.refusal_reason
            and bool(self.outfit_id)
            and bool(self.scene_id)
            and bool(self.pose_id)
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Choice":
        if not isinstance(data, dict):
            raise ChoiceValidationError(f"Choice JSON не dict: {type(data).__name__}")

        requested_unavailable = bool(data.get("requested_unavailable", False))
        refusal_reason = data.get("refusal_reason")
        if refusal_reason is not None and not isinstance(refusal_reason, str):
            raise ChoiceValidationError(
                f"refusal_reason должно быть строкой или null, не {type(refusal_reason).__name__}"
            )

        modifiers = data.get("modifiers") or {}
        if not isinstance(modifiers, dict):
            raise ChoiceValidationError(
                f"modifiers должно быть dict, не {type(modifiers).__name__}"
            )
        modifiers = {str(k): str(v) for k, v in modifiers.items() if v}

        aspect_raw = str(data.get("aspect") or "").strip().lower()
        aspect = aspect_raw if aspect_raw in VALID_ASPECTS else ""

        choice = cls(
            outfit_id=str(data.get("outfit_id") or "").strip(),
            scene_id=str(data.get("scene_id") or "").strip(),
            pose_id=str(data.get("pose_id") or "").strip(),
            modifiers=modifiers,
            aspect=aspect,
            requested_unavailable=requested_unavailable,
            refusal_reason=refusal_reason,
        )

        if not choice.is_refusal() and not choice.is_generate():
            missing = [
                name for name, val in (
                    ("outfit_id", choice.outfit_id),
                    ("scene_id", choice.scene_id),
                    ("pose_id", choice.pose_id),
                )
                if not val
            ]
            raise ChoiceValidationError(
                f"Choice не refusal но отсутствуют поля: {missing}"
            )

        return choice
