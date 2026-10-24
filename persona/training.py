from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

REQUIRED_TRAINING: tuple[int, int] = (1, 1)

MANIFEST_KEY = "training"
DEFAULT_VERSION = (1, 1)

STATUS_OK = "ok"
STATUS_STEP_BEHIND = "step_behind"
STATUS_LEVEL_BEHIND = "level_behind"
STATUS_NEWER = "newer"

_VERSION_RX = re.compile(r"^\s*(\d+)\s*\.\s*(\d+|\*)\s*$")


def level_letter(level: int) -> str:
    if level < 1:
        return "?"
    out = ""
    n = level
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


@dataclass(frozen=True, order=True)
class TrainingVersion:
    level: int
    step: int

    @classmethod
    def parse(cls, text) -> "TrainingVersion":
        if isinstance(text, TrainingVersion):
            return text
        if isinstance(text, (tuple, list)) and len(text) == 2:
            return cls(int(text[0]), int(text[1]))
        if isinstance(text, dict):
            if "level" in text:
                return cls(int(text["level"]), int(text.get("step", 0)))
            text = text.get("version", "")
        m = _VERSION_RX.match(str(text or ""))
        if not m or m.group(2) == "*":
            raise ValueError(f"не версия обучения: {text!r} (ожидалось «уровень.ступень»)")
        return cls(int(m.group(1)), int(m.group(2)))

    def __str__(self) -> str:
        return f"{self.level}.{self.step}"

    @property
    def letter(self) -> str:
        return level_letter(self.level)

    @property
    def label(self) -> str:
        return f"{self.letter}{self.step}"

    @property
    def release(self) -> str:
        return f"0.{self.level}.{self.step}"

    def to_manifest(self) -> dict:
        return {"version": str(self), "level": self.level, "step": self.step,
                "letter": self.letter, "label": self.label}


def matches_from(spec: str, version: TrainingVersion) -> bool:
    m = _VERSION_RX.match(str(spec or ""))
    if not m:
        return False
    if int(m.group(1)) != version.level:
        return False
    return m.group(2) == "*" or int(m.group(2)) == version.step


def read_training(manifest: dict | None) -> TrainingVersion:
    block = (manifest or {}).get(MANIFEST_KEY)
    if not isinstance(block, dict):
        return TrainingVersion(*DEFAULT_VERSION)
    try:
        return TrainingVersion.parse(block)
    except (ValueError, TypeError):
        return TrainingVersion(*DEFAULT_VERSION)


def ensure_training_section(manifest: dict) -> bool:
    block = manifest.get(MANIFEST_KEY)
    if isinstance(block, dict) and "version" in block:
        return False
    manifest[MANIFEST_KEY] = {**TrainingVersion(*DEFAULT_VERSION).to_manifest(),
                              "history": []}
    return True


def set_training(manifest: dict, version: TrainingVersion) -> None:
    block = manifest.get(MANIFEST_KEY) if isinstance(manifest.get(MANIFEST_KEY), dict) else {}
    history = list(block.get("history") or [])
    manifest[MANIFEST_KEY] = {**version.to_manifest(), "history": history}


def append_history(manifest: dict, *, frm: TrainingVersion, to: TrainingVersion,
                   trainer: str, app_version: str, notes: str = "") -> None:
    if not isinstance(manifest.get(MANIFEST_KEY), dict):
        ensure_training_section(manifest)
    manifest[MANIFEST_KEY].setdefault("history", []).append({
        "from": str(frm), "to": str(to),
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trainer": trainer, "app_version": app_version, "notes": notes or "",
    })


def compare_with_required(version: TrainingVersion,
                          required: tuple[int, int] | TrainingVersion | None = None) -> str:
    req = TrainingVersion.parse(required if required is not None else REQUIRED_TRAINING)
    if version.level < req.level:
        return STATUS_LEVEL_BEHIND
    if version.level > req.level:
        return STATUS_NEWER
    if version.step < req.step:
        return STATUS_STEP_BEHIND
    return STATUS_OK


def describe_gap(version: TrainingVersion, required=None, *,
                 char_name: str = "персонаж") -> dict:
    req = TrainingVersion.parse(required if required is not None else REQUIRED_TRAINING)
    status = compare_with_required(version, req)
    if status == STATUS_LEVEL_BEHIND:
        msg = (f"{char_name}: нужно обучение — приложение требует подготовку {req.label}, "
               f"у файла {version.label}. Откройте тренер персонажа.")
    elif status == STATUS_NEWER:
        msg = (f"{char_name}: файл обучен до {version.label}, а приложение знает только "
               f"{req.label} — обновите приложение.")
    elif status == STATUS_STEP_BEHIND:
        msg = (f"{char_name}: доступна подготовка {req.label} (у файла {version.label}) — "
               f"можно доучить в тренере, работать будет и так.")
    else:
        msg = ""
    return {"status": status, "file": str(version), "file_label": version.label,
            "required": str(req), "required_label": req.label, "message": msg}
