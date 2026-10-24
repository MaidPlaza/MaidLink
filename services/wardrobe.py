from __future__ import annotations

import json
import time
from pathlib import Path

BASE_STEP = "base"


def outfit_basename(outfit_id: str) -> str:
    return f"portrait_{outfit_id}"


def required_steps() -> list[str]:
    from persona import mood as mood_mod
    return [BASE_STEP] + [name for name in mood_mod.MOOD_STATES
                          if name != mood_mod.NEUTRAL]


def step_filename(outfit_id: str, step: str) -> str:
    base = outfit_basename(outfit_id)
    return f"{base}.png" if step == BASE_STEP else f"{base}_{step}.png"


class Wardrobe:
    def __init__(self, char_dir: Path | str):
        self.dir = Path(char_dir)
        self.path = self.dir / "wardrobe.json"

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data.setdefault("queue", [])
        data.setdefault("sets", {})
        data.setdefault("style", "default")
        return data

    def _save(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    def files_done(self, outfit_id: str) -> int:
        return sum(1 for s in required_steps()
                   if (self.dir / step_filename(outfit_id, s)).exists())

    def is_prepared(self, outfit_id: str) -> bool:
        rec = self._load()["sets"].get(outfit_id) or {}
        if rec.get("prepared_at"):
            return (self.dir / step_filename(outfit_id, BASE_STEP)).exists()
        steps = required_steps()
        return self.files_done(outfit_id) == len(steps)

    def progress(self, outfit_id: str) -> tuple[int, int]:
        steps = required_steps()
        rec = self._load()["sets"].get(outfit_id) or {}
        done = len([s for s in rec.get("steps_done", []) if s in steps])
        if not done:
            done = self.files_done(outfit_id)
        return (min(done, len(steps)), len(steps))

    def queue(self) -> list[str]:
        return list(self._load()["queue"])

    def is_queued(self, outfit_id: str) -> bool:
        return outfit_id in self._load()["queue"]

    def enqueue(self, outfit_id: str) -> bool:
        data = self._load()
        if outfit_id in data["queue"] or self.is_prepared(outfit_id):
            return False
        data["queue"].append(outfit_id)
        self._save(data)
        return True

    def dequeue(self, outfit_id: str) -> None:
        data = self._load()
        if outfit_id in data["queue"]:
            data["queue"] = [o for o in data["queue"] if o != outfit_id]
            self._save(data)

    def head(self) -> str | None:
        q = self._load()["queue"]
        return q[0] if q else None

    def ensure_seed(self, outfit_id: str) -> int:
        data = self._load()
        rec = data["sets"].setdefault(outfit_id, {})
        if not rec.get("seed"):
            import random
            rec["seed"] = random.randint(0, 2 ** 63 - 1)
            rec["started_at"] = time.time()
            self._save(data)
        return int(rec["seed"])

    def next_step(self, outfit_id: str) -> str | None:
        rec = self._load()["sets"].get(outfit_id) or {}
        done = set(rec.get("steps_done", []))
        for s in required_steps():
            if s not in done:
                return s
        return None

    def mark_step(self, outfit_id: str, step: str) -> None:
        data = self._load()
        rec = data["sets"].setdefault(outfit_id, {})
        steps = rec.setdefault("steps_done", [])
        if step not in steps:
            steps.append(step)
        self._save(data)

    def mark_prepared(self, outfit_id: str) -> None:
        data = self._load()
        rec = data["sets"].setdefault(outfit_id, {})
        rec["prepared_at"] = time.time()
        data["queue"] = [o for o in data["queue"] if o != outfit_id]
        self._save(data)

    def reset(self, outfit_id: str) -> None:
        data = self._load()
        data["sets"].pop(outfit_id, None)
        self._save(data)

    def delete_set(self, outfit_id: str) -> int:
        removed = 0
        for s in required_steps():
            f = self.dir / step_filename(outfit_id, s)
            try:
                if f.exists():
                    f.unlink()
                    removed += 1
            except OSError as e:
                print(f"[wardrobe] delete {f.name} failed: {e}")
        data = self._load()
        data["sets"].pop(outfit_id, None)
        data["queue"] = [o for o in data["queue"] if o != outfit_id]
        self._save(data)
        return removed

    def get_style(self) -> str:
        return self._load().get("style", "default") or "default"

    def set_style(self, style_id: str) -> bool:
        style_id = (style_id or "default").strip() or "default"
        data = self._load()
        if data.get("style", "default") == style_id:
            return False
        data["style"] = style_id
        data["sets"] = {}
        data["queue"] = []
        self._save(data)
        return True

    def status(self, outfit_id: str, preparing_now: str | None = None) -> dict:
        done, total = self.progress(outfit_id)
        return {
            "prepared": self.is_prepared(outfit_id),
            "queued": self.is_queued(outfit_id),
            "preparing": preparing_now == outfit_id,
            "done": done,
            "total": total,
        }
