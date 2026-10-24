import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from services.log_privacy import priv


def _parse_llm_json(text: str, debug: bool = False) -> dict | None:
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        if debug:
            print(f"[MEM] JSON not found in: {priv(text, 100)}")
        return None

    text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fixed = re.sub(r',\s*}', '}', text)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    fixed2 = fixed
    while fixed2.count('{') > fixed2.count('}'):
        fixed2 += '}'
    while fixed2.count('[') > fixed2.count(']'):
        last_brace = fixed2.rfind('}')
        if last_brace > 0:
            fixed2 = fixed2[:last_brace] + ']' + fixed2[last_brace:]
        else:
            fixed2 += ']'
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError as e:
        if debug:
            print(f"[MEM] JSON parse failed: {e}")
            print(f"[MEM] Raw: {priv(text, 200)}")
        return None


EXTRACT_TOKEN_BUDGET = 8000


SERVICE_NOTE_PREFIXES = ("(снимок не был отправлен", "(новый снимок не был отправлен")


def is_service_note(m: dict) -> bool:
    mood = m.get("mood") or {}
    if mood.get("kind") == "marker" and mood.get("marker") == "fake_action":
        return True
    content = m.get("content")
    return (m.get("role") == "user" and isinstance(content, str)
            and content.lstrip().startswith(SERVICE_NOTE_PREFIXES))


def format_dialogue(messages: list[dict], honorific: str, char_name: str) -> str:
    user_label = honorific or "Пользователь"
    assistant_label = char_name or "Ассистент"
    parts: list[str] = []
    for m in messages:
        if is_service_note(m):
            continue
        role = m.get("role")
        content = _flatten_dialogue_content(m.get("content", ""))
        mood = m.get("mood") or {}
        if mood.get("kind") == "marker":
            if mood.get("marker") == "mood" and mood.get("to"):
                parts.append(
                    f'<смена_настроения чьё="{assistant_label}">'
                    f'{mood.get("from") or "ровное"} → {mood["to"]}'
                    f'</смена_настроения>')
            elif mood.get("marker") == "scenario" and mood.get("title"):
                attr = "начался" if mood.get("event") == "start" else "завершён"
                body = (mood.get("text") or "").strip()
                parts.append(f'<сценарий {attr}="{mood["title"]}">{body}</сценарий>'
                             if body else f'<сценарий {attr}="{mood["title"]}"/>')
            else:
                parts.append(content)
            continue
        if role == "user":
            speaker = user_label
            from services import gestures as _gestures
            content = _gestures.render_transcript(content)
        elif role == "assistant":
            if not (content or "").strip() and m.get("tool_calls"):
                continue
            speaker = assistant_label
        else:
            continue
        attr = ""
        if role == "assistant" and mood.get("state"):
            try:
                from persona.mood import intensity_word
                word = intensity_word(float(mood.get("intensity") or 0.0))
                attr = f' настроение="{assistant_label}: {mood["state"]} ({word})"'
            except Exception:
                attr = f' настроение="{assistant_label}: {mood["state"]}"'
        parts.append(f'<реплика от="{speaker}"{attr}>\n{content}\n</реплика>')
    return "\n".join(parts)


def _flatten_dialogue_content(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    out: list[str] = []
    for chunk in content:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") == "text":
            t = (chunk.get("text") or "").strip()
            if t:
                out.append(t)
        elif chunk.get("type") == "image_url":
            out.append("*изображение*")
    return "\n".join(out)


def relative_time(timestamp: float) -> str:
    from datetime import datetime
    if not timestamp:
        return ""
    now = time.time()
    diff = now - timestamp
    if diff < 60:
        return "только что"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m} мин. назад"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h} ч. назад"
    days = int(diff // 86400)
    if days == 1:
        return "вчера"
    if days == 2:
        return "позавчера"
    if days < 7:
        return f"{days} дн. назад"
    if days < 14:
        return "неделю назад"
    if days < 30:
        w = days // 7
        return f"{w} нед. назад"
    if days < 60:
        return "месяц назад"
    months = days // 30
    return f"{months} мес. назад"


def absolute_time(timestamp: float) -> str:
    from datetime import datetime
    if not timestamp:
        return ""
    dt = datetime.fromtimestamp(timestamp)
    months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{dt.day} {months[dt.month - 1]} {dt.year}, {dt.hour}:{dt.minute:02d}"


TYPE_LABELS = {
    "навык": "навык",
    "сущность": "сущность",
    "событие": "событие",
    "событие_план": "запланированное",
    "предпочтение": "предпочтение",
    "рефлексия": "рефлексия",
    "лор": "лор",
    "петля": "петля",
}

SEARCHABLE_TYPES = ("сущность", "событие", "событие_план", "предпочтение",
                    "рефлексия", "навык", "лор", "петля", "заметка")

TYPE_SYNONYMS = {
    "дневник": "рефлексия", "дневники": "рефлексия", "рефлексии": "рефлексия",
    "мысли": "рефлексия", "диарий": "рефлексия",
    "план": "событие_план", "планы": "событие_план",
    "запланированное": "событие_план",
    "человек": "сущность", "люди": "сущность", "персона": "сущность",
    "карточка": "сущность", "место": "сущность", "организация": "сущность",
    "события": "событие",
    "предпочтения": "предпочтение",
    "навыки": "навык",
    "петли": "петля",
    "заметки": "заметка", "блокнот": "заметка", "список": "заметка",
    "списки": "заметка",
}


def normalize_search_type(raw: str | None) -> str | None:
    if not raw:
        return None
    t = unicodedata.normalize("NFC", str(raw)).strip().lower()
    t = TYPE_SYNONYMS.get(t, t)
    return t if t in SEARCHABLE_TYPES else None


def parse_when(word: str) -> tuple[float, float] | None:
    if not word:
        return None
    w = unicodedata.normalize("NFC", str(word)).strip().lower()
    now = time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                            0, 0, 0, 0, 0, -1))
    day = 86400.0
    if w in ("сегодня", "today"):
        return (midnight, midnight + day)
    if w in ("вчера", "yesterday"):
        return (midnight - day, midnight)
    if w == "позавчера":
        return (midnight - 2 * day, midnight - day)
    if w in ("неделя", "неделю", "week"):
        return (now - 7 * day, now + 60)
    if w in ("месяц", "month"):
        return (now - 30 * day, now + 60)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", w)
    if m:
        try:
            start = time.mktime((int(m.group(1)), int(m.group(2)),
                                 int(m.group(3)), 0, 0, 0, 0, 0, -1))
            return (start, start + day)
        except (ValueError, OverflowError):
            return None
    return None


from prompts.reflection import (
    _EXTRACT_PREAMBLE,
    _ENTITIES_TASK,
    _EVENTS_TASK,
    ENTITIES_EXTRACT_PROMPT,
    EVENTS_EXTRACT_PROMPT,
)


_EVENT_IMPORTANCE_WORDS = {
    "низкая": 0.3, "низкий": 0.3, "low": 0.3,
    "средняя": 0.5, "средний": 0.5, "medium": 0.5,
    "высокая": 0.7, "высокий": 0.7, "high": 0.7,
}
EVENT_IMPORTANCE_DEFAULT = 0.4


def _event_importance(raw) -> float:
    if raw is None or raw == "":
        return EVENT_IMPORTANCE_DEFAULT
    if isinstance(raw, (int, float)):
        return float(raw) if 0.0 <= float(raw) <= 1.0 else EVENT_IMPORTANCE_DEFAULT
    w = unicodedata.normalize("NFC", str(raw)).strip().lower()
    if w in _EVENT_IMPORTANCE_WORDS:
        return _EVENT_IMPORTANCE_WORDS[w]
    try:
        v = float(w.replace(",", "."))
        return v if 0.0 <= v <= 1.0 else EVENT_IMPORTANCE_DEFAULT
    except ValueError:
        return EVENT_IMPORTANCE_DEFAULT


def _record_search_text(record) -> str:
    parts = [record.title or ""]
    for k, v in (record.details or {}).items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(str(x) for x in v[:12] if isinstance(x, (str, int, float)))
        elif isinstance(v, dict):
            parts.extend(str(x) for x in v.values() if isinstance(x, (str, int, float)))
    return " ".join(p for p in parts if p)


def cosine_similarity(a, b):
    if a is None or b is None or len(a) != len(b) or not len(a):
        return 0.0
    a, b = np.array(a), np.array(b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / norm) if norm > 0 else 0.0


_next_record_id = 0

def _gen_record_id() -> str:
    global _next_record_id
    _next_record_id += 1
    return f"r{_next_record_id}"


def _sync_id_counter(records) -> None:
    global _next_record_id
    for r in records:
        rid = getattr(r, "record_id", None)
        if rid is None and isinstance(r, dict):
            rid = r.get("record_id")
        if isinstance(rid, str) and rid.startswith("r"):
            try:
                num = int(rid[1:])
            except ValueError:
                continue
            if num >= _next_record_id:
                _next_record_id = num + 1


@dataclass
class MemoryRecord:
    type: str
    title: str
    record_id: str = ""
    details: dict = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    importance: float = 0.5
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0
    links: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.record_id:
            self.record_id = _gen_record_id()

    @property
    def decay_rate(self) -> float:
        if self.type in ("событие", "рефлексия"):
            return max(0.01, 0.2 * (1.0 - self.importance))
        if self.type == "сущность":
            from memory.entity_schema import PINNED_RELATIONS, normalize_relation
            d = self.details or {}
            if d.get("entity_type") == "профиль":
                return 0.0
            if normalize_relation(d.get("relation_to_user", "")) in PINNED_RELATIONS:
                return 0.0
            return max(0.003, 0.04 * (1.0 - self.importance))
        if self.type == "петля":
            return 0.0
        if self.type == "заметка":
            return 0.0
        return 0.0

    @property
    def effective_importance(self) -> float:
        if self.decay_rate == 0:
            return self.importance
        reference = max(self.created_at, self.last_accessed or 0.0)
        days = (time.time() - reference) / 86400
        return self.importance * math.exp(-self.decay_rate * days)

    @property
    def is_forgotten(self) -> bool:
        return self.effective_importance < 0.05

    @property
    def search_label(self) -> str:
        return f"[{self.type}] {self.title}"

    def to_dict(self) -> dict:
        return {
            "type": self.type, "title": self.title, "record_id": self.record_id,
            "details": self.details, "embedding": self.embedding,
            "importance": self.importance, "created_at": self.created_at,
            "last_accessed": self.last_accessed, "access_count": self.access_count,
            "links": list(self.links),
        }

    @staticmethod
    def from_dict(d: dict) -> "MemoryRecord":
        return MemoryRecord(**{k: v for k, v in d.items() if k in MemoryRecord.__dataclass_fields__})

    def format_details(self) -> str:
        lines = [f"[{self.record_id}] [{self.type}] {self.title}"]
        if self.created_at:
            rel = relative_time(self.created_at)
            abs_t = absolute_time(self.created_at)
            time_labels = {
                "сущность": "Впервые узнала",
                "событие": "Когда произошло",
                "событие_план": "Когда создала запись",
                "предпочтение": "Когда узнала",
                "рефлексия": "Когда записала",
            }
            label = time_labels.get(self.type, "")
            if label:
                lines.append(f"{label}: {rel} ({abs_t})")
        if self.type == "событие_план":
            due = self.details.get("due_date", "")
            status = self.details.get("status", "ожидает")
            if due:
                lines.append(f"Запланировано на: {due}")
            lines.append(f"Статус: {status}")
        for k, v in self.details.items():
            if k.startswith("_"):
                continue
            if isinstance(v, list):
                lines.append(f"{k}: {', '.join(str(x) for x in v)}")
            elif isinstance(v, dict):
                inner = ", ".join(f"{ik}={iv}" for ik, iv in v.items() if not str(ik).startswith("_"))
                lines.append(f"{k}: {{{inner}}}")
            elif v:
                lines.append(f"{k}: {v}")
        if self.links:
            lines.append(f"links: {', '.join(self.links)}")
        return "\n".join(lines)


class UnifiedMemory:
    USER_PROFILE_ENTITY_TYPE = "профиль"

    MAX_GENERAL_PREFERENCES = 10
    MAX_RULES = 6
    MAX_ENTITY_PREFERENCES = 3

    def __init__(self, storage, path: str, client):
        self._storage = storage
        self._path = path
        self._client = client
        self.records: list[MemoryRecord] = []
        self.traits: dict[str, float] = {}
        self.debug: bool = True
        self.weather_config = None
        self.user_honorific: str = "Господин"
        self.honorific_override: str = ""
        self.address_form_override: str = ""
        self.pending_actions: list[dict] = []

    def _find_user_profile(self) -> "MemoryRecord | None":
        for r in self.records:
            if r.is_forgotten:
                continue
            if r.type != "сущность":
                continue
            if (r.details or {}).get("entity_type") == self.USER_PROFILE_ENTITY_TYPE:
                return r
        return None

    def get_user_profile(self) -> dict:
        r = self._find_user_profile()
        if not r:
            return {}
        return {k: v for k, v in r.details.items() if k != "entity_type"}

    def update_user_profile(self, field: str, value) -> "MemoryRecord":
        r = self._find_user_profile()
        now = time.time()
        if r is None:
            r = MemoryRecord(
                type="сущность",
                title=f"Профиль {self.user_honorific}",
                details={
                    "entity_type": self.USER_PROFILE_ENTITY_TYPE,
                    field: value,
                    "_updated_at": now,
                },
                importance=0.9,
                created_at=now,
            )
            self.records.append(r)
        else:
            r.details[field] = value
            r.details["_updated_at"] = now
        return r

    def load_address_overrides(self, character=None) -> None:
        r = self._find_user_profile()
        if r is not None:
            self.honorific_override = (r.details.get("honorific_override") or "").strip()
            self.address_form_override = (r.details.get("address_form_override") or "").strip()
        if character is not None:
            from persona.character_context import resolve_honorific
            self.user_honorific = resolve_honorific(character, override=self.honorific_override)

    def set_address_override(self, *, character=None, form: str = "",
                             honorific: str = "", persist: bool = True) -> bool:
        changed = False
        f = (form or "").strip().lower()
        if f in ("ты", "вы") and self.address_form_override != f:
            self.address_form_override = f
            changed = True
        h = (honorific or "").strip()
        if h and self.honorific_override != h:
            self.honorific_override = h
            changed = True
        if character is not None:
            from persona.character_context import resolve_honorific
            self.user_honorific = resolve_honorific(character, override=self.honorific_override)
        if persist and changed:
            if self.address_form_override:
                self.update_user_profile("address_form_override", self.address_form_override)
            if self.honorific_override:
                self.update_user_profile("honorific_override", self.honorific_override)
        return changed

    def _refers_to_user(self, name: str) -> bool:
        from memory.entity_schema import normalize_alias
        n = normalize_alias(name)
        if not n:
            return False
        refs = {
            normalize_alias(self.user_honorific or "Господин"),
            "господин", "хозяин", "госпожа", "хозяйка",
            "пользователь", "юзер",
        }
        return n in refs

    def _route_user_facts_to_profile(self, details: dict) -> None:
        for k in ("occupation", "age"):
            v = details.get(k)
            if v:
                self.update_user_profile(k, v)
        loc = details.get("location")
        if isinstance(loc, dict) and loc.get("city"):
            self.update_user_profile("location", loc)
        elif isinstance(loc, str) and loc.strip():
            cur = self.get_user_profile().get("location")
            if not (isinstance(cur, dict) and cur.get("city")):
                self.update_user_profile("location", {"city": loc.strip()})
        for list_k in ("traits", "notes"):
            v = details.get(list_k)
            if isinstance(v, list) and v:
                cur = self.get_user_profile().get(list_k) or []
                if not isinstance(cur, list):
                    cur = [cur]
                merged = list(dict.fromkeys(
                    [*cur, *[str(x) for x in v if str(x).strip()]]))
                self.update_user_profile(list_k, merged)

    def find_entity(self, name: str, entity_type: str | None = None) -> "MemoryRecord | None":
        from memory.entity_schema import is_entity_card, normalize_alias
        if not name:
            return None
        needle = normalize_alias(name)
        for r in self.records:
            if r.is_forgotten or not is_entity_card(r):
                continue
            if entity_type and r.details.get("entity_type") != entity_type:
                continue
            if normalize_alias(r.title) == needle:
                return r
            for a in r.details.get("aliases", []) or []:
                if normalize_alias(a) == needle:
                    return r
        return None

    def upsert_entity(self, entity_type: str, name: str, **fields) -> "MemoryRecord":
        from memory.entity_schema import (
            ALL_ENTITY_TYPES, is_entity_card, normalize_alias, normalize_relation,
        )
        if entity_type not in ALL_ENTITY_TYPES:
            raise ValueError(f"unknown entity_type {entity_type!r}")
        if not name or not name.strip():
            raise ValueError("name is required")

        if fields.get("relation_to_user"):
            fields["relation_to_user"] = normalize_relation(fields["relation_to_user"])

        existing: "MemoryRecord | None" = None
        rid = fields.pop("record_id", None)
        if rid:
            for r in self.records:
                if r.record_id == rid and is_entity_card(r):
                    existing = r
                    break
        if existing is None:
            existing = self.find_entity(name, entity_type=entity_type)

        if existing is None:
            needle = normalize_alias(name)
            for r in self.records:
                if r.is_forgotten or r.type != "сущность":
                    continue
                if (r.details or {}).get("entity_type"):
                    continue
                if normalize_alias(r.title) == needle:
                    r.details["entity_type"] = entity_type
                    existing = r
                    break

        now = time.time()
        list_fields = {"aliases", "notes", "traits"}

        if existing is None:
            details: dict = {"entity_type": entity_type, "_updated_at": now}
            for k, v in fields.items():
                if v is None or v == "":
                    continue
                if k in list_fields and isinstance(v, str):
                    details[k] = [v]
                else:
                    details[k] = v
            importance = 0.7 if entity_type != self.USER_PROFILE_ENTITY_TYPE else 0.9
            rec = MemoryRecord(
                type="сущность",
                title=name.strip(),
                details=details,
                importance=importance,
                created_at=now,
            )
            if self._client is not None:
                alias_text = " ".join(details.get("aliases", []) or [])
                rec.embedding = self._client.embed(f"{name} {alias_text}".strip())
            self.records.append(rec)
            return rec

        for k, v in fields.items():
            if v is None or v == "":
                continue
            if k in list_fields:
                current = list(existing.details.get(k) or [])
                incoming = v if isinstance(v, list) else [v]
                seen_norm = {normalize_alias(str(x)) for x in current}
                for item in incoming:
                    key = normalize_alias(str(item))
                    if key and key not in seen_norm:
                        current.append(item)
                        seen_norm.add(key)
                existing.details[k] = current
            else:
                existing.details[k] = v
        existing.details["_updated_at"] = now
        return existing

    def rename_entity(self, record_id: str, new_title: str) -> bool:
        from memory.entity_schema import is_entity_card, normalize_alias
        if not new_title or not new_title.strip():
            return False
        for r in self.records:
            if r.record_id != record_id or not is_entity_card(r):
                continue
            old_title = r.title
            if normalize_alias(old_title) == normalize_alias(new_title):
                return False
            aliases = list(r.details.get("aliases") or [])
            if old_title and not any(normalize_alias(a) == normalize_alias(old_title) for a in aliases):
                aliases.append(old_title)
            r.details["aliases"] = aliases
            r.details["_updated_at"] = time.time()
            r.title = new_title.strip()
            return True
        return False

    def get_entity_events(self, record_id: str) -> list["MemoryRecord"]:
        from memory.entity_schema import is_entity_card
        out: list[MemoryRecord] = []
        seen: set = set()
        for r in self.records:
            if (r.is_forgotten or r.record_id == record_id
                    or is_entity_card(r) or r.type == "петля"):
                continue
            hit = record_id in (r.links or [])
            if not hit:
                for e in (r.details.get("relations") or []):
                    if e.get("target") == record_id:
                        hit = True
                        break
            if hit and r.record_id not in seen:
                seen.add(r.record_id)
                out.append(r)
        out.sort(key=lambda r: r.created_at or 0.0, reverse=True)
        return out

    def get_event_roles(self, record_id: str) -> list:
        rec = self._by_id(record_id)
        if rec is None:
            return []
        out: list = []
        for e in (rec.details.get("relations") or []):
            tgt = self._by_id(e.get("target"))
            if tgt is not None and not tgt.is_forgotten:
                out.append((e.get("predicate"), tgt))
        return out

    def get_open_loops(self, subject: str | None = None,
                       salience: str | None = None) -> list["MemoryRecord"]:
        from memory.loops import LOOP_TYPE, LOOP_STATUS_OPEN
        out = []
        for r in self.records:
            if r.type != LOOP_TYPE or r.is_forgotten:
                continue
            d = r.details or {}
            if d.get("status", LOOP_STATUS_OPEN) != LOOP_STATUS_OPEN:
                continue
            if subject is not None and d.get("subject") != subject:
                continue
            if salience is not None and d.get("salience") != salience:
                continue
            out.append(r)
        out.sort(key=lambda r: (r.importance, r.created_at or 0.0), reverse=True)
        return out

    def get_entity_loops(self, record_id: str) -> list["MemoryRecord"]:
        from memory.loops import LOOP_TYPE, LOOP_STATUS_OPEN
        out = []
        for r in self.records:
            if r.type != LOOP_TYPE or r.is_forgotten or r.record_id == record_id:
                continue
            if (r.details or {}).get("status", LOOP_STATUS_OPEN) != LOOP_STATUS_OPEN:
                continue
            hit = record_id in (r.links or [])
            if not hit:
                for e in (r.details.get("relations") or []):
                    if e.get("target") == record_id:
                        hit = True
                        break
            if hit:
                out.append(r)
        out.sort(key=lambda r: r.importance, reverse=True)
        return out

    def load(self):
        if not self._storage:
            return
        try:
            data = self._storage.load(self._path)
            if data:
                self.records = [MemoryRecord.from_dict(r) for r in data.get("records", [])]
                self.traits = data.get("traits", {})
                _sync_id_counter(self.records)
                active = sum(1 for r in self.records if not r.is_forgotten)
                print(f"[MEM] Loaded {len(self.records)} records ({active} active)")
        except Exception:
            self.records = []
            self.traits = {}

    def load_records(self, record_dicts: list[dict]) -> None:
        self.records = [MemoryRecord.from_dict(r) for r in (record_dicts or [])]
        _sync_id_counter(self.records)

    def save(self):
        if not self._storage:
            return
        data = {
            "records": [r.to_dict() for r in self.records],
            "traits": self.traits,
        }
        self._storage.save(data, self._path)

    _DUMP_SECTION_ORDER = ("сущность", "петля", "предпочтение", "событие",
                           "событие_план", "рефлексия", "лор", "навык")

    def dump_readable(self) -> str:
        alive: dict[str, list[MemoryRecord]] = {}
        forgotten: list[MemoryRecord] = []
        for r in self.records:
            (forgotten if r.is_forgotten else
             alive.setdefault(r.type, [])).append(r)

        def _fmt(r: MemoryRecord) -> str:
            eff = r.effective_importance
            status = f"важность: {r.importance:.2f}"
            if r.decay_rate > 0:
                status += f" (сейчас {eff:.2f})"
            if r.access_count:
                status += f" · доставалась {r.access_count} раз"
                if r.last_accessed:
                    status += f", последний — {absolute_time(r.last_accessed)}"
            return f"{r.format_details()}\n{status}"

        by_type = ", ".join(f"{t}: {len(rs)}"
                            for t, rs in sorted(alive.items(),
                                                key=lambda kv: -len(kv[1])))
        n_alive = sum(len(rs) for rs in alive.values())
        lines = [f"Записей: {n_alive} живых + {len(forgotten)} забытых "
                 f"= {len(self.records)}"]
        if by_type:
            lines.append(f"По типам: {by_type}")
        section_types = [t for t in self._DUMP_SECTION_ORDER if t in alive]
        section_types += sorted(t for t in alive if t not in self._DUMP_SECTION_ORDER)
        for t in section_types:
            rs = sorted(alive[t], key=lambda r: r.created_at)
            lines.append(f"\n{'=' * 12} {t.upper()} ({len(rs)}) {'=' * 12}")
            lines.append(f"\n{'-' * 40}\n".join(_fmt(r) for r in rs))
        if forgotten:
            forgotten.sort(key=lambda r: r.created_at)
            lines.append(f"\n{'=' * 12} ЗАБЫТЫЕ ({len(forgotten)}) {'=' * 12}")
            lines.append(f"\n{'-' * 40}\n".join(_fmt(r) for r in forgotten))
        return "\n".join(lines) + "\n"

    def find_by_relation(self, category: str) -> list[MemoryRecord]:
        from memory.entity_schema import is_entity_card, normalize_relation
        cat = normalize_relation(category)
        if not cat:
            return []
        out = [
            r for r in self.records
            if is_entity_card(r) and not r.is_forgotten
            and normalize_relation((r.details or {}).get("relation_to_user", "")) == cat
        ]
        out.sort(key=lambda r: r.created_at or 0.0, reverse=True)
        now = time.time()
        for r in out:
            r.last_accessed = now
            r.access_count += 1
        return out

    def _by_id(self, record_id: str) -> "MemoryRecord | None":
        return next((r for r in self.records if r.record_id == record_id), None)

    def add_relation(self, subject_id: str, predicate: str, target_id: str) -> bool:
        from memory.entity_schema import normalize_any_predicate
        pred = normalize_any_predicate(predicate)
        if not pred or not subject_id or not target_id or subject_id == target_id:
            return False
        subj, tgt = self._by_id(subject_id), self._by_id(target_id)
        if subj is None or tgt is None:
            return False
        rels = subj.details.setdefault("relations", [])
        edge = {"predicate": pred, "target": target_id}
        if edge not in rels:
            rels.append(edge)
        return True

    def get_entity_relations(self, record_id: str) -> list:
        rec = self._by_id(record_id)
        if rec is None:
            return []
        out: list = []
        seen: set = set()
        for e in (rec.details.get("relations") or []):
            tgt = self._by_id(e.get("target"))
            if tgt is not None and not tgt.is_forgotten:
                key = (e.get("predicate"), tgt.record_id, "out")
                if key not in seen:
                    seen.add(key)
                    out.append((e.get("predicate"), tgt, "out"))
        for r in self.records:
            if r.record_id == record_id or r.is_forgotten:
                continue
            for e in (r.details.get("relations") or []):
                if e.get("target") == record_id:
                    key = (e.get("predicate"), r.record_id, "in")
                    if key not in seen:
                        seen.add(key)
                        out.append((e.get("predicate"), r, "in"))
        return out

    def find_related(self, record_id: str, predicate: str | None = None) -> list["MemoryRecord"]:
        from memory.entity_schema import normalize_any_predicate
        pred = normalize_any_predicate(predicate) if predicate else None
        found: list = []
        seen: set = set()
        for p, other, _dir in self.get_entity_relations(record_id):
            if pred is not None and p != pred:
                continue
            if other.record_id in seen:
                continue
            seen.add(other.record_id)
            found.append(other)
        now = time.time()
        for r in found:
            r.last_accessed = now
            r.access_count += 1
        return found

    def _link_episode_to_entities(self, episode: "MemoryRecord",
                                  target_ids: list[str]) -> None:
        from memory.entity_schema import infer_event_role, is_entity_card
        if episode is None:
            return
        rels = episode.details.setdefault("relations", [])
        for tid in (target_ids or []):
            tgt = self._by_id(tid)
            if tgt is None or tgt.record_id == episode.record_id:
                continue
            tgt_etype = ((tgt.details or {}).get("entity_type", "")
                         if is_entity_card(tgt) else "")
            edge = {"predicate": infer_event_role(episode.type, tgt_etype),
                    "target": tid}
            if edge not in rels:
                rels.append(edge)

    def search(self, query: str, top_k: int = 8,
               type_filter: str | None = None) -> list[MemoryRecord]:
        if not self.records:
            return []
        query = (query or "").strip()

        if query.startswith("связь:"):
            return self.find_by_relation(query.split(":", 1)[1].strip())[:top_k]

        time_range: tuple[float, float] | None = None
        while True:
            if query.startswith("тип:"):
                raw = query.split(":", 1)[1].strip()
                head, _, rest = raw.partition(" ")
                tf = normalize_search_type(head)
                if tf is None:
                    return []
                type_filter, query = tf, rest.strip()
                continue
            if query.startswith("когда:"):
                raw = query.split(":", 1)[1].strip()
                head, _, rest = raw.partition(" ")
                tr = parse_when(head)
                if tr is not None:
                    time_range = tr
                    query = rest.strip()
                else:
                    query = f"{head} {rest}".strip()
                continue
            break
        if type_filter is not None:
            type_filter = normalize_search_type(type_filter)
            if type_filter is None:
                return []

        pool = [r for r in self.records
                if not r.is_forgotten and (r.type == type_filter
                                           if type_filter else r.type != "лор")]
        if time_range is not None:
            _t0, _t1 = time_range
            pool = [r for r in pool if _t0 <= (r.created_at or 0) < _t1]

        def _touch(rs: list[MemoryRecord]) -> list[MemoryRecord]:
            now = time.time()
            for r in rs:
                r.last_accessed = now
                r.access_count += 1
            return rs

        if (type_filter or time_range) and not query:
            return _touch(sorted(pool, key=lambda r: r.created_at,
                                 reverse=True)[:top_k])
        if not query:
            return []

        from memory.lexical import bm25_scores, rrf_merge, tokenize

        embedding: list[float] = []
        if self._client is not None:
            try:
                embedding = self._client.embed(query) or []
            except Exception:
                embedding = []

        q_tokens = tokenize(query)
        doc_tokens = [tokenize(_record_search_text(record)) for record in pool]
        bm = bm25_scores(q_tokens, doc_tokens)
        bm_rank = [i for i in sorted(range(len(pool)), key=lambda i: bm[i],
                                     reverse=True) if bm[i] > 0][:20]

        sims: list[float] = [0.0] * len(pool)
        if embedding:
            for i, record in enumerate(pool):
                if record.embedding:
                    sims[i] = cosine_similarity(embedding, record.embedding)
        sem_rank = [i for i in sorted(range(len(pool)), key=lambda i: sims[i],
                                      reverse=True) if sims[i] > 0.25][:20]

        if not bm_rank and not sem_rank:
            from memory.entity_schema import normalize_alias
            needle = normalize_alias(query)
            if not needle:
                return []
            hits: list[MemoryRecord] = []
            for record in pool:
                hay = [record.title or ""]
                hay.extend(record.details.get("aliases") or [])
                hay.append(str(record.details.get("description") or ""))
                hay.append(str(record.details.get("brief") or ""))
                if any(needle in normalize_alias(h) for h in hay):
                    hits.append(record)
            return _touch(hits[:top_k])

        fused = rrf_merge([sem_rank, bm_rank])
        scored = []
        now = time.time()
        for i, rrf in fused.items():
            record = pool[i]
            weight = rrf * (0.5 + 0.5 * record.effective_importance)
            age_days = max(0.0, (now - (record.created_at or now)) / 86400)
            weight *= 1.0 + 0.25 * math.exp(-age_days / 7.0)
            scored.append((weight, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return _touch([r for _s, r in scored[:top_k]])

    def search_by_embedding(self, embedding: list[float], top_k: int = 3) -> list[MemoryRecord]:
        if not embedding:
            return []

        scored = []
        for record in self.records:
            if record.is_forgotten or not record.embedding or record.type == "лор":
                continue
            sim = cosine_similarity(embedding, record.embedding)
            weight = sim * (0.5 + 0.5 * record.effective_importance)
            scored.append((weight, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for s, r in scored[:top_k] if s > 0.3]

    RECENT_EVENT_TYPES = ("событие", "событие_план", "предпочтение", "рефлексия")

    def get_recent_events(self, n: int = 5, *,
                          types: tuple[str, ...] | None = None) -> list[MemoryRecord]:
        if n <= 0:
            return []
        allowed = types or self.RECENT_EVENT_TYPES
        candidates = [
            r for r in self.records
            if r.type in allowed and not r.is_forgotten
        ]
        candidates.sort(key=lambda r: r.created_at or 0.0, reverse=True)
        return candidates[:n]

    def get_by_title(self, title: str) -> MemoryRecord | None:
        title_clean = title.lower().strip()

        for r in self.records:
            if r.record_id and r.record_id.lower() == title_clean:
                r.last_accessed = time.time()
                r.access_count += 1
                return r

        for r in self.records:
            if r.title.lower() == title_clean:
                r.last_accessed = time.time()
                r.access_count += 1
                return r

        for r in self.records:
            if title_clean in r.title.lower() or r.title.lower() in title_clean:
                r.last_accessed = time.time()
                r.access_count += 1
                return r

        return None

    def get_always_on_lore(self) -> list[str]:
        return [
            r.details.get("fact", r.title)
            for r in self.records
            if r.type == "лор" and r.details.get("always_in_prompt", False)
        ]

    def get_passive_hints(self, query_embedding: list[float], top_k: int = 2) -> list[str]:
        if not query_embedding:
            return []

        scored = []
        for r in self.records:
            if r.is_forgotten or not r.embedding or r.type == "лор":
                continue
            sim = cosine_similarity(query_embedding, r.embedding)
            if sim > 0.35:
                scored.append((sim, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r.search_label for _, r in scored[:top_k]]

    def _find_similar_record(self, title: str, rec_type: str) -> MemoryRecord | None:
        from memory.entity_schema import is_entity_card
        title_lower = title.lower().strip()
        want_card = (rec_type == "сущность")

        for r in self.records:
            if is_entity_card(r) != want_card:
                continue
            r_lower = r.title.lower()

            if r_lower == title_lower:
                return r

            if r.type == rec_type or r.type == "сущность":
                if len(r_lower) < len(title_lower) and title_lower.startswith(r_lower):
                    return r
                if len(title_lower) < len(r_lower) and r_lower.startswith(title_lower):
                    return r

            if len(title_lower) >= 4 and len(r_lower) >= 4:
                min_len = min(len(title_lower), len(r_lower))
                prefix = min(min_len, max(4, min_len - 2))
                if title_lower[:prefix] == r_lower[:prefix] and r.type == rec_type:
                    return r

        return None

    def _get_self_name(self) -> str:
        for r in self.records:
            if r.type == "сущность" and r.details.get("entity_type") == "self":
                return r.title
        return "себя"

    def _ensure_registry(self):
        if getattr(self, "_registry", None) is not None:
            return self._registry
        from tools.registry import ToolRegistry
        from tools.builtin import register_builtin_tools
        reg = ToolRegistry()
        register_builtin_tools(reg)
        self._registry = reg
        return reg

    def _build_tool_context(self):
        from tools.registry import ToolContext
        state = getattr(self, "_session_state_ref", None)
        ctx = ToolContext(
            memory=self,
            weather_config=self.weather_config,
            debug=self.debug,
            pending_actions=self.pending_actions,
        )
        if state is not None:
            try:
                config = state.get("config")
                ctx.drawing_catalog = state.get("drawing_catalog")
                ctx.wardrobe = state.get("wardrobe")
                ctx.default_outfit_id = state.get("character_default_outfit_id") or ""
                ctx.current_outfit_id = (state.get("runtime_portrait_outfit_id")
                                         or ctx.default_outfit_id)
                ctx.identity = state.get("identity")
                ctx.document = state.get("document")
                if config is not None:
                    ctx.drawing_max_rating = config.drawing.max_rating
                    ctx.drawing_renderer_id = config.drawing.renderer_id
                    ctx.drawing_outfit_change_min_tier = config.drawing.outfit_change_min_tier
            except Exception as e:
                print(f"[ToolContext] drawing fields fill failed: {e}")
        return ctx

    def get_tools(self, query: str = "", query_embedding=None) -> list[dict]:
        reg = self._ensure_registry()
        active = reg.select_active(query=query or "", query_embedding=query_embedding)
        return reg.schemas_for(active)

    def get_tool_preferences(self, tool_name: str) -> list[str]:
        try:
            tool = self._ensure_registry().get(tool_name)
            theme = getattr(tool, "pref_theme", "") if tool else ""
            if not theme:
                return []
            card = self.find_entity(theme)
            if card is None:
                return []
            up = (card.details or {}).get("user_preference")
            if isinstance(up, str):
                return [up.strip()] if up.strip() else []
            return [str(x).strip() for x in (up or []) if str(x).strip()]
        except Exception:
            return []

    def reembed_all(self) -> int:
        if self._client is None:
            return 0
        texts, targets = [], []
        for r in self.records:
            joined = " ".join(str(v) for v in (r.details or {}).values() if isinstance(v, str))
            text = f"{r.title} {joined}".strip() or (r.title or r.type)
            texts.append(text)
            targets.append(r)
        if not texts:
            return 0
        vecs = self._client.embed_batch(texts)
        n = 0
        for r, v in zip(targets, vecs):
            if v:
                r.embedding = v
                n += 1
        return n

    def handle_tool_call(self, tool_name: str, arguments: dict) -> str | None:
        reg = self._ensure_registry()
        return reg.handle(tool_name, arguments or {}, self._build_tool_context())

    def add_record(self, type: str, title: str, details: dict,
                   importance: float = 0.5, embed_text: str | None = None,
                   links: list[str] | None = None):
        if embed_text:
            text = embed_text
        else:
            text = _record_search_text(MemoryRecord(type=type, title=title, details=details,
                                                    record_id="tmp"))
        embedding = self._client.embed(text) if self._client else []

        record = MemoryRecord(
            type=type, title=title, details=details,
            embedding=embedding, importance=min(1.0, max(0.0, float(importance))),
            created_at=time.time(),
            links=list(links or []),
        )
        self.records.append(record)
        if record.links and type in self.RECENT_EVENT_TYPES:
            self._link_episode_to_entities(record, record.links)
        return record

    def add_reflection(self, description: str, importance: float,
                       reflection_type: str = "diary",
                       extra: dict | None = None):
        title = description[:50] + ("..." if len(description) > 50 else "")
        details = {"description": description, "reflection_type": reflection_type}
        if extra:
            details.update(extra)
        self.add_record(
            type="рефлексия",
            title=title,
            details=details,
            importance=importance,
            embed_text=description,
        )

    QUICK_EXTRACT_PROMPT = (
        "Извлеки ВСЕ новые факты ТОЛЬКО из сообщения пользователя.\n"
        "Ответ ассистента показан для контекста, но НЕ извлекай из него факты.\n\n"
        "ВАЖНО: не пропускай имена людей и названия мест.\n\n"
        "Что искать в сообщении пользователя:\n"
        "- Люди: имена, кто они пользователю, чем занимаются\n"
        "- Места: дом, работа, город, любимые заведения\n"
        "- Факты: работа, хобби, планы пользователя\n"
        "- События: встречи, решения, новости\n\n"
        "Примеры:\n"
        "Пользователь: 'Моя сестра Аня приехала из Москвы'\n"
        "→ {{\"items\": [\n"
        "  {{\"type\": \"сущность\", \"title\": \"Аня\", \"details\": {{\"связь\": \"сестра пользователя\", \"откуда\": \"Москва\"}}}},\n"
        "  {{\"type\": \"сущность\", \"title\": \"Москва\", \"details\": {{\"что\": \"город\", \"связь\": \"откуда приехала Аня\"}}}}\n"
        "]}}\n\n"
        "Пользователь: 'Вчера ходил в новое кафе рядом с офисом'\n"
        "→ {{\"items\": [\n"
        "  {{\"type\": \"сущность\", \"title\": \"Кафе рядом с офисом\", \"details\": {{\"что\": \"заведение\", \"связь\": \"новое место пользователя\"}}}},\n"
        "  {{\"type\": \"событие\", \"title\": \"Поход в новое кафе\", \"details\": {{\"когда\": \"вчера\"}}}}\n"
        "]}}\n\n"
        "Пользователь: 'Привет, как дела?'\n"
        "→ {{\"items\": []}}\n\n"
        "Ответь ТОЛЬКО JSON, без пояснений."
    )

    def quick_extract(self, last_user: str, last_assistant: str):
        if not self._client:
            return

        pair = f"Пользователь: {last_user}\nАссистент: {last_assistant}"
        prompt = self.QUICK_EXTRACT_PROMPT

        try:
            response = self._client.chat(
                messages=[{"role": "user", "content": pair}],
                system=prompt, thinking=True,
                label="Быстрая экстракция (в чате)",
            )
            data = _parse_llm_json(response, debug=self.debug)
            if data is None:
                return

            count = 0
            for item in data.get("items", []):
                title = item.get("title", "").strip()
                rec_type = item.get("type", "")
                details = item.get("details", {})
                if isinstance(details, str):
                    details = {"description": details}
                if not title or not rec_type:
                    continue

                existing = self._find_similar_record(title, rec_type)
                if existing:
                    for k, v in details.items():
                        if v and k not in ("_fresh",):
                            existing.details[k] = v
                    existing.details["_fresh"] = True
                    if self.debug:
                        print(f"[MEM] Quick (updated): [{rec_type}] {priv(title)}")
                    count += 1
                    continue

                importance = 0.6 if rec_type == "сущность" else 0.4
                details["_fresh"] = True
                self.add_record(rec_type, title, details, importance)
                count += 1
                if self.debug:
                    print(f"[MEM] Quick: [{rec_type}] {priv(title)}")

            if count:
                self.save()
                return

        except Exception:
            pass

        import re
        known_names = {r.title.lower() for r in self.records}
        skip_words = {
            "господин", "господи", "привет", "здравствуй", "здравствуйте",
            "пожалуйста", "спасибо", "извини", "извините", "ладно", "хорошо",
            "кстати", "конечно", "наверное", "возможно", "может", "кажется",
            "сегодня", "вчера", "завтра", "потом", "сейчас",
        }
        potential_names = re.findall(r'(?<=[а-яё,] )([А-ЯЁ][а-яё]{2,})', last_user)
        for name in potential_names:
            if name.lower() in skip_words:
                continue
            existing = self._find_similar_record(name, "сущность")
            if existing:
                existing.details["_fresh"] = True
                if self.debug:
                    print(f"[MEM] Quick (fallback, matched existing): {priv(existing.title)}")
            else:
                self.add_record(
                    "сущность", name,
                    {"связь": "упомянут в разговоре", "_fresh": True},
                    importance=0.5,
                )
                if self.debug:
                    print(f"[MEM] Quick (fallback): [сущность] {priv(name)}")
            self.save()

    DEDUP_PROMPT = (
        "Ты — система дедупликации памяти. Рассуждай пошагово.\n\n"
        "Шаг 1: Прочитай все записи.\n"
        "Шаг 2: Для каждой новой записи (помечены *НОВАЯ*) проверь — нет ли среди старых записей ТОГО ЖЕ человека или события.\n"
        "Шаг 3: Если нашёл дубликат — объедини информацию из обеих записей.\n\n"
        "Признаки дубликата (объединяй ТОЛЬКО если это ОДНА И ТА ЖЕ сущность):\n"
        "- Одно и то же имя в разных падежах ('Виктора' = 'Виктор')\n"
        "- Одно имя содержится в другом ('Виктор' и 'Виктор — друг')\n"
        "- Одно и то же событие описано по-разному\n"
        "- ОСОБЫЙ СЛУЧАЙ: пара 'событие_план' + 'событие' про одну и ту же встречу/дело —\n"
        "  это дубликат (план и ретроспективная запись того же факта). ОСТАВЛЯЙ план,\n"
        "  потому что у него есть due_date и status='ожидает'; merge = запись типа 'событие'.\n\n"
        "ЗАПРЕЩЕНО объединять:\n"
        "- Разных людей (даже если они связаны между собой)\n"
        "- Записи типа 'сущность' с записью 'событие' (они про разные уровни — карточка vs эпизод)\n"
        "- Записи где совпадает только тема, но не субъект\n\n"
        "Для каждого дубликата укажи:\n"
        "- keep: индекс записи которую оставить\n"
        "- merge: индекс записи которую удалить\n"
        "- merged_title: лучшее название для объединённой записи\n"
        "- merged_details: объединённые детали из обеих записей\n\n"
        "Ответь ТОЛЬКО JSON:\n"
        "{{\"merges\": [{{\"keep\": 0, \"merge\": 1, \"merged_title\": \"...\", \"merged_details\": {{...}}}}]}}\n"
        "Если дубликатов нет: {{\"merges\": []}}"
    )

    def deduplicate_records(self, session_start_count: int = 0):
        if not self._client or len(self.records) < 2:
            return

        DEDUPABLE_TYPES = ("сущность", "событие", "событие_план")

        new_records = [(i, r) for i, r in enumerate(self.records)
                       if i >= session_start_count and r.type in DEDUPABLE_TYPES]

        if not new_records:
            return

        all_records = [(i, r) for i, r in enumerate(self.records)
                       if r.type in DEDUPABLE_TYPES and not r.is_forgotten]

        if len(all_records) < 2:
            return

        new_indices = {i for i, _ in new_records}

        _DEDUP_RECENT_OLD = 100
        old_records = [(i, r) for i, r in all_records if i not in new_indices]
        if len(old_records) > _DEDUP_RECENT_OLD:
            def _sig_words(text: str) -> set[str]:
                return set(re.findall(r"\w{3,}", (text or "").lower()))
            new_words: set[str] = set()
            for _, r in new_records:
                new_words |= _sig_words(r.title)
            recent = old_records[-_DEDUP_RECENT_OLD:]
            recent_ids = {i for i, _ in recent}
            lexical = [(i, r) for i, r in old_records
                       if i not in recent_ids and (_sig_words(r.title) & new_words)]
            old_records = sorted(lexical + recent, key=lambda p: p[0])
        candidates = sorted(
            old_records + [(i, r) for i, r in all_records if i in new_indices],
            key=lambda p: p[0])

        lines = []
        for i, r in candidates:
            details_str = ", ".join(f"{k}: {v}" for k, v in r.details.items()
                                    if isinstance(v, str) and v and not k.startswith("_"))
            marker = " *НОВАЯ*" if i in new_indices else ""
            lines.append(f"[{i}] ({r.type}) {r.title} — {details_str}{marker}")

        records_text = "\n".join(lines)

        try:
            response = self._client.chat(
                messages=[{"role": "user", "content": records_text}],
                system=self.DEDUP_PROMPT, thinking=False,
                label="Дедупликация записей",
            )
            data = _parse_llm_json(response, debug=self.debug)
            if data is None:
                print("[MEM] Dedup: не удалось разобрать JSON")
                return

            merged_indices = set()
            for merge in data.get("merges", []):
                keep_idx = merge.get("keep")
                merge_idx = merge.get("merge")
                new_title = merge.get("merged_title", "")
                new_details = merge.get("merged_details", {})

                if keep_idx is None or merge_idx is None:
                    continue
                if keep_idx >= len(self.records) or merge_idx >= len(self.records):
                    continue

                keep_rec = self.records[keep_idx]
                merge_rec = self.records[merge_idx]

                if isinstance(new_details, dict):
                    for k, v in new_details.items():
                        if v:
                            keep_rec.details[k] = v
                if new_title:
                    keep_rec.title = new_title

                merged_indices.add(merge_idx)
                if self.debug:
                    print(f"[MEM] Dedup: merged [{merge_idx}] '{priv(merge_rec.title)}' "
                          f"into [{keep_idx}] '{priv(keep_rec.title)}'")

            if merged_indices:
                self.records = [r for i, r in enumerate(self.records) if i not in merged_indices]
                self.save()
                print(f"[MEM] Dedup: removed {len(merged_indices)} duplicates")

        except Exception as e:
            if self.debug:
                print(f"[MEM] Dedup error: {e}")

    def _build_known_list(self) -> str:
        def _line(r):
            etype = r.details.get("entity_type")
            return f"«{r.title}» (сущность:{etype})" if etype else f"«{r.title}» ({r.type})"
        return "; ".join(_line(r) for r in self.records[-30:]
                         if not r.is_forgotten) or "ничего"

    def _apply_extracted_records(self, records) -> int:
        from memory.entity_schema import ALL_ENTITY_TYPES, ENTITY_TYPE_USER_PROFILE
        count = 0
        for item in (records or []):
            if not isinstance(item, dict):
                continue
            rec_type = item.get("type", "")
            title = (item.get("title") or "").strip()
            details = item.get("details", {})
            if isinstance(details, str):
                details = {"description": details}
            if not title or not rec_type:
                continue

            raw_links = item.get("links") or details.get("links") or []
            details.pop("links", None)
            resolved_links: list[str] = []
            for raw in raw_links:
                if not isinstance(raw, str) or not raw.strip():
                    continue
                raw = raw.strip()
                if self._refers_to_user(raw):
                    continue
                if raw.startswith("r") and raw[1:].isdigit():
                    resolved_links.append(raw)
                    continue
                found = self.find_entity(raw)
                if found:
                    resolved_links.append(found.record_id)
                elif self.debug:
                    print(f"[MEM] Unresolved link «{priv(raw)}» dropped")

            entity_type = details.get("entity_type")
            if (rec_type == "сущность"
                    and entity_type in ALL_ENTITY_TYPES
                    and entity_type != ENTITY_TYPE_USER_PROFILE):
                if self._refers_to_user(title):
                    self._route_user_facts_to_profile(details)
                    if self.debug:
                        print(f"[MEM] Факты Господина → профиль (из «{priv(title)}»)")
                    count += 1
                    continue
                fields = {k: v for k, v in details.items()
                          if k not in ("entity_type",) and not k.startswith("_")}
                try:
                    rec = self.upsert_entity(entity_type, title, **fields)
                    if self.debug:
                        print(f"[MEM] Upserted card: [{entity_type}] {priv(rec.title)}")
                    count += 1
                    continue
                except ValueError as e:
                    print(f"[MEM] upsert_entity failed for «{priv(title)}»: {e}")

            existing = self._find_similar_record(title, rec_type)
            if existing:
                for k, v in details.items():
                    if v:
                        existing.details[k] = v
                if resolved_links:
                    merged = list(dict.fromkeys((existing.links or []) + resolved_links))
                    existing.links = merged
                    if rec_type in self.RECENT_EVENT_TYPES:
                        self._link_episode_to_entities(existing, resolved_links)
                if len(title) > len(existing.title):
                    existing.title = title
                if self.debug:
                    print(f"[MEM] Updated: [{rec_type}] {priv(existing.title)}")
                count += 1
                continue

            importance = 0.5
            if rec_type == "событие":
                importance = _event_importance(details.pop("importance", None))
            elif rec_type == "сущность":
                importance = 0.7
            self.add_record(rec_type, title, details, importance, links=resolved_links)
            count += 1
            print(f"[MEM] New: [{rec_type}] {priv(title)}"
                  + (f" links={resolved_links}" if resolved_links else ""))
        return count

    def extract_from_session(self, messages: list[dict], char_name: str = "", honorific: str = "",
                             gender: str = "female"):
        for r in self.records:
            if r.details.get("_fresh"):
                del r.details["_fresh"]
        if not self._client or len(messages) < 4:
            self.save()
            return

        from memory.conversation import tail_by_tokens
        recent = tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET)
        conversation = format_dialogue(recent, honorific, char_name)
        if (gender or "female").lower() == "male":
            gender_hint = ("О себе пиши в МУЖСКОМ роде "
                           "(сказал, подумал, был, рад, сделал, увидел).")
        else:
            gender_hint = ("О себе пиши в ЖЕНСКОМ роде "
                           "(сказала, подумала, была, рада, сделала, увидела).")
        from memory.text_classifier import classify_messages
        hints = classify_messages(recent)
        hints_text = (("\n\nПодсказки (автоанализ типов):\n" + "\n".join(
            f"- «{h['message']}» → вероятно {h['type']}" for h in hints)) if hints else "")

        rounds = (
            ("сущности", ENTITIES_EXTRACT_PROMPT, ""),
            ("события", EVENTS_EXTRACT_PROMPT, hints_text),
        )
        total = 0
        for label, tmpl, extra in rounds:
            known = self._build_known_list()
            system = tmpl.format(known=known, char_name=char_name or "персонаж",
                                 honorific=honorific or "пользователь",
                                 gender_hint=gender_hint) + extra
            try:
                response = self._client.chat(
                    messages=[{"role": "user", "content": conversation}],
                    system=system, thinking=False, label=f"Извлечение: {label}")
                data = _parse_llm_json(response, debug=self.debug)
                if data:
                    total += self._apply_extracted_records(data.get("records", []))
            except Exception as e:
                print(f"[MEM] Extraction round {label} error: {e}")
        if total:
            self.save()

    def extract_user_rules(self, messages: list[dict], char_name: str = "",
                           honorific: str = "") -> int:
        from prompts.reflection import RULES_EXTRACT_PROMPT
        if not self._client or len(messages) < 4:
            return 0
        from memory.conversation import tail_by_tokens
        convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                                honorific or "Господин", char_name or "")
        system = RULES_EXTRACT_PROMPT.format(
            char_name=char_name or "персонаж", honorific=honorific or "Господин")
        try:
            resp = self._client.chat(
                messages=[{"role": "user", "content": convo}],
                system=system, thinking=False, label="Извлечение: правила")
        except Exception as e:
            print(f"[MEM] rules extract error: {type(e).__name__}: {e}")
            return 0
        data = _parse_llm_json(resp, debug=self.debug)
        if not isinstance(data, dict):
            return 0
        new = [str(r).strip() for r in (data.get("rules") or []) if str(r).strip()]
        if not new:
            return 0
        existing = list((self.get_user_profile() or {}).get("rules") or [])
        seen = {r.lower() for r in existing}
        added = [r for r in new if r.lower() not in seen]
        if added:
            self.update_user_profile("rules", (existing + added)[-self.MAX_RULES:])
        return len(added)

    def extract_preferences(self, messages: list[dict], char_name: str = "",
                            honorific: str = "") -> dict:
        from prompts.reflection import PREFERENCES_ROUTED_PROMPT
        res = {"general": 0, "entity": 0, "topic": 0}
        if not self._client or len(messages) < 4:
            return res
        from memory.conversation import tail_by_tokens
        convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                                honorific or "Господин", char_name or "")
        routes = self._ensure_registry().pref_theme_routes()
        tool_themes = ""
        if routes:
            rlines = [f'- если это про {hint} — scope="тема", target="{theme}".'
                      for theme, hint in routes]
            tool_themes = ("Привязка к инструментам (используй ИМЕННО эти target):\n"
                           + "\n".join(rlines))
        system = PREFERENCES_ROUTED_PROMPT.format(
            char_name=char_name or "персонаж", honorific=honorific or "Господин",
            tool_themes=tool_themes)
        try:
            resp = self._client.chat(
                messages=[{"role": "user", "content": convo}],
                system=system, thinking=False, label="Извлечение: предпочтения")
        except Exception as e:
            print(f"[MEM] preferences extract error: {type(e).__name__}: {e}")
            return res
        data = _parse_llm_json(resp, debug=self.debug)
        if not isinstance(data, dict):
            return res
        return self._apply_preference_items(data.get("preferences") or [])

    def _apply_preference_items(self, items) -> dict:
        res = {"general": 0, "entity": 0, "topic": 0}
        general = list((self.get_user_profile() or {}).get("preferences") or [])
        gseen = {p.lower() for p in general}
        gchanged = False

        def _add_general(text: str) -> None:
            nonlocal gchanged
            if text.lower() not in gseen:
                general.append(text)
                gseen.add(text.lower())
                gchanged = True
                res["general"] += 1

        for item in (items or []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()[:240]
            if not text:
                continue
            scope = str(item.get("scope") or "общее").strip().lower()
            target = str(item.get("target") or "").strip()
            if scope == "тема" and target:
                try:
                    card = self.upsert_entity("тема", target)
                    self._add_card_preference(card, text)
                    res["topic"] += 1
                except Exception as e:
                    print(f"[MEM] pref topic upsert fail «{priv(target)}»: {e}")
                    _add_general(text)
            elif scope in ("сущность", "персона", "место", "организация") and target:
                card = self.find_entity(target)
                if card is not None:
                    self._add_card_preference(card, text)
                    res["entity"] += 1
                else:
                    _add_general(text)
            else:
                _add_general(text)
        if gchanged:
            self.update_user_profile("preferences", general[-self.MAX_GENERAL_PREFERENCES:])
        return res

    def _add_card_preference(self, card, text: str) -> None:
        cur = (card.details or {}).get("user_preference")
        if isinstance(cur, str):
            lst = [cur.strip()] if cur.strip() else []
        elif isinstance(cur, list):
            lst = [str(x).strip() for x in cur if str(x).strip()]
        else:
            lst = []
        if text.lower() in {x.lower() for x in lst}:
            return
        lst.append(text)
        card.details["user_preference"] = lst[-self.MAX_ENTITY_PREFERENCES:]

    def infer_preferences_from_material(self, material_text: str, honorific: str = "") -> dict:
        from prompts.reflection import INFER_PREFERENCES_PROMPT
        if not self._client or not (material_text or "").strip():
            return {"general": 0, "entity": 0, "topic": 0}
        system = INFER_PREFERENCES_PROMPT.format(honorific=honorific or "Господин")
        try:
            resp = self._client.chat(
                messages=[{"role": "user", "content": material_text[:3000]}],
                system=system, thinking=True, label="Вывод предпочтений (паттерны)")
        except Exception as e:
            print(f"[MEM] infer prefs error: {type(e).__name__}: {e}")
            return {"general": 0, "entity": 0, "topic": 0}
        data = _parse_llm_json(resp, debug=self.debug)
        if not isinstance(data, dict):
            return {"general": 0, "entity": 0, "topic": 0}
        return self._apply_preference_items(data.get("preferences") or [])

    def consolidate_preferences_rules(self, honorific: str = "", min_total: int = 4) -> dict:
        from prompts.reflection import CONSOLIDATE_PREFS_PROMPT
        prof = self.get_user_profile() or {}
        prefs = [str(p).strip() for p in (prof.get("preferences") or []) if str(p).strip()]
        rules = [str(r).strip() for r in (prof.get("rules") or []) if str(r).strip()]
        info = {"prefs_before": len(prefs), "prefs_after": len(prefs),
                "rules_before": len(rules), "rules_after": len(rules), "changed": False}
        if not self._client or (len(prefs) + len(rules)) < min_total:
            return info
        payload = ("<предпочтения>\n"
                   + "\n".join(f"{i+1}. {p}" for i, p in enumerate(prefs))
                   + "\n</предпочтения>\n<правила>\n"
                   + "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))
                   + "\n</правила>")
        try:
            resp = self._client.chat(
                messages=[{"role": "user", "content": payload}],
                system=CONSOLIDATE_PREFS_PROMPT.format(honorific=honorific or "Господин"),
                thinking=True, label="Чистка предпочтений/правил")
        except Exception as e:
            print(f"[MEM] consolidate prefs error: {type(e).__name__}: {e}")
            return info
        data = _parse_llm_json(resp, debug=self.debug)
        if not isinstance(data, dict):
            return info
        new_prefs = [str(x).strip() for x in (data.get("preferences") or []) if str(x).strip()]
        new_rules = [str(x).strip() for x in (data.get("rules") or []) if str(x).strip()]
        if prefs and not new_prefs:
            new_prefs = prefs
        if rules and not new_rules:
            new_rules = rules
        if len(new_prefs) > len(prefs) or len(new_rules) > len(rules):
            info["note"] = "skip: cleanup увеличил списки (подозрительно)"
            return info
        if new_prefs != prefs:
            self.update_user_profile("preferences", new_prefs)
        if new_rules != rules:
            self.update_user_profile("rules", new_rules)
        info.update(prefs_after=len(new_prefs), rules_after=len(new_rules),
                    changed=(new_prefs != prefs or new_rules != rules))
        return info

    def bootstrap_from_character(self, character):
        print("[MEM] Bootstrapping from character YAML...")
        pending = []
        now = time.time()

        pending.append(("сущность", character.name, {
            "entity_type": "self",
            "description": f"Это я — {character.name}",
            "attitude": "это я",
        }, 0.9, f"{character.name} {character.core_identity or ''}"))

        for rel in character.relationships:
            if self._refers_to_user(rel.name):
                continue
            pending.append(("сущность", rel.name, {
                "entity_type": "person", "attitude": rel.attitude,
                "notes": [rel.notes] if rel.notes else [],
            }, 0.8, f"{rel.name} {rel.attitude} {rel.notes}"))

        abilities_path = Path("extensions/abilities/data/default.yaml")
        if abilities_path.exists():
            with open(abilities_path, "r", encoding="utf-8") as f:
                ab_data = yaml.safe_load(f)
            for ab in ab_data.get("abilities", []):
                pending.append(("навык", ab["name"], {
                    "brief": ab.get("brief", ""),
                    "detail": ab.get("detail", ""),
                    "keywords": ab.get("keywords", []),
                }, 0.5, f"{ab['name']} {ab.get('brief', '')}"))

        lore_path = Path("extensions/lore/data/default.yaml")
        if lore_path.exists():
            with open(lore_path, "r", encoding="utf-8") as f:
                lore_data = yaml.safe_load(f)
            for fact in lore_data.get("core", []):
                pending.append(("лор", fact[:50], {
                    "fact": fact, "always_in_prompt": True,
                }, 1.0, fact))
            for item in lore_data.get("extended", []):
                pending.append(("лор", item["topic"], {
                    "fact": item["text"], "always_in_prompt": False,
                    "keywords": item.get("keywords", []),
                }, 0.5, f"{item['topic']} {' '.join(item.get('keywords', []))}"))

        if pending and self._client and hasattr(self._client, "embed_batch"):
            texts = [p[4] for p in pending]
            embeddings = self._client.embed_batch(texts)
        else:
            embeddings = [self._client.embed(p[4]) if self._client else [] for p in pending]

        for i, (rec_type, title, details, importance, _) in enumerate(pending):
            self.records.append(MemoryRecord(
                type=rec_type, title=title, details=details,
                embedding=embeddings[i] if i < len(embeddings) else [],
                importance=importance, created_at=now,
            ))

        self.save()
        print(f"[MEM] Bootstrapped {len(pending)} records")
