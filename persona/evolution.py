import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from persona.character import Character
from persona.character_context import resolve_honorific, CharacterContext
from services.log_privacy import priv


EVOLUTION_THRESHOLD = 3.0
MAX_CHANGES_PER_CYCLE = 3


@dataclass
class Statement:
    id: str
    text: str
    section: str = ""
    source: str = "base"
    created_at: float = 0.0
    history: list[dict] = field(default_factory=list)
    axis_value: float = 0.5
    axis_momentum: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "section": self.section,
            "source": self.source, "created_at": self.created_at,
            "history": self.history,
            "axis_value": self.axis_value,
            "axis_momentum": self.axis_momentum,
        }

    @staticmethod
    def from_dict(d: dict) -> "Statement":
        return Statement(**{k: v for k, v in d.items() if k in Statement.__dataclass_fields__})


@dataclass
class Thought:
    text: str
    kind: str = "interest"
    relevance: float = 0.5
    created_at: float = 0.0
    strength: int = 0

    def to_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind,
                "relevance": self.relevance, "created_at": self.created_at,
                "strength": self.strength}

    @staticmethod
    def from_dict(d: dict) -> "Thought":
        return Thought(**{k: v for k, v in d.items() if k in Thought.__dataclass_fields__})


THOUGHT_DECAY = 0.2


def core_identity_text(character) -> str:
    return " ".join((getattr(character, "background", "") or "").split())


class CharacterIdentity:
    def __init__(self, path: str):
        self._path = path
        self._maid_archive = None
        self._maid_pre_save_hook = None
        self._maid_seal = None
        self.self_statements: list[Statement] = []
        self.relationship_statements: list[Statement] = []
        self.thoughts: list[Thought] = []
        self.master_summary: str = ""
        self.last_session_summary: str = ""
        self.last_session_mood: str = ""
        self.mood_state: str = "ровное"
        self.mood_intensity: float = 0.0
        self.mood_updated_at: float = 0.0
        self.mood_reason: str = ""
        self.mood_shift_from: str = ""
        self.mood_fading: bool = False
        self.reaction_state: str = ""
        self.reaction_intensity: float = 0.0
        self.reaction_reason: str = ""
        self.last_evolution: float = 0.0
        self.accumulated_importance: float = 0.0
        self.rel_axes_last_eval: float = 0.0
        self.relationship_level: float = 0.0
        self.relationship_momentum: float = 0.0
        self.event_log: dict = {}
        self.active_traits: list = []
        self.quirk_progress: dict = {}
        self.assistant_prefs: dict = {}
        self.self_styling: dict = {}
        self.ui_seen_relations: dict = {}
        self.stats: dict = {}
        self.gacha: dict = {}
        self.axis_goals: dict = {}
        self.axis_stimuli: list = []

    STAT_KEYS = ("sessions", "messages_user", "messages_assistant", "images")

    def ensure_stats(self, *, sessions_backfill: int | None = None) -> dict:
        if not self.stats.get("since"):
            self.stats["since"] = time.time()
            if sessions_backfill:
                self.stats["sessions"] = int(sessions_backfill)
        return self.stats

    def bump_stat(self, key: str, n: int = 1) -> int:
        self.ensure_stats()
        self.stats[key] = int(self.stats.get(key, 0) or 0) + int(n)
        return self.stats[key]

    @property
    def path(self) -> str:
        return self._path

    def apply_loaded(self, data: dict) -> None:
        self.self_statements = [Statement.from_dict(s) for s in data.get("self_statements", [])]
        self.relationship_statements = [Statement.from_dict(s) for s in data.get("relationship_statements", [])]
        self.thoughts = [Thought.from_dict(t) for t in data.get("thoughts", [])]
        self.master_summary = data.get("master_summary", "")
        self.last_session_summary = data.get("last_session_summary", "")
        self.last_session_mood = data.get("last_session_mood", "")
        from persona import mood as _mood_mig
        self.mood_state = _mood_mig.migrate_state(data.get("mood_state", "ровное")) or "ровное"
        self.mood_intensity = float(data.get("mood_intensity", 0.0))
        self.mood_updated_at = float(data.get("mood_updated_at", 0.0))
        self.mood_reason = data.get("mood_reason", "")
        self.reaction_state = data.get("reaction_state", "")
        self.reaction_intensity = float(data.get("reaction_intensity", 0.0))
        self.reaction_reason = data.get("reaction_reason", "")
        self.last_evolution = data.get("last_evolution", 0.0)
        self.accumulated_importance = data.get("accumulated_importance", 0.0)
        self.rel_axes_last_eval = float(data.get("rel_axes_last_eval", 0.0))
        self.relationship_level = float(data.get("relationship_level", 0.0))
        self.relationship_momentum = float(data.get("relationship_momentum", 0.0))
        self.ui_seen_relations = {str(k): float(v) for k, v in
                                  (data.get("ui_seen_relations") or {}).items()}
        self.stats = dict(data.get("stats") or {})
        self.event_log = dict(data.get("event_log") or {})
        from persona.character import ActiveTrait
        self.active_traits = [
            ActiveTrait.from_dict(t)
            for t in data.get("active_traits", [])
        ]
        self.assistant_prefs = dict(data.get("assistant_prefs") or {})
        self.self_styling = dict(data.get("self_styling") or {})
        self.gacha = dict(data.get("gacha") or {})
        self.quirk_progress = dict(data.get("quirk_progress") or {})
        self.axis_goals = dict(data.get("axis_goals") or {})
        self.axis_stimuli = list(data.get("axis_stimuli") or [])

    def load(self) -> bool:
        p = Path(self._path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.apply_loaded(data)
            return True
        except Exception:
            return False

    def _serialize(self) -> dict:
        return {
            "version": 1,
            "last_evolution": self.last_evolution,
            "accumulated_importance": self.accumulated_importance,
            "rel_axes_last_eval": self.rel_axes_last_eval,
            "relationship_level": self.relationship_level,
            "relationship_momentum": self.relationship_momentum,
            "self_statements": [s.to_dict() for s in self.self_statements],
            "relationship_statements": [s.to_dict() for s in self.relationship_statements],
            "thoughts": [t.to_dict() for t in self.thoughts],
            "master_summary": self.master_summary,
            "last_session_summary": self.last_session_summary,
            "last_session_mood": self.last_session_mood,
            "mood_state": self.mood_state,
            "mood_intensity": self.mood_intensity,
            "mood_updated_at": self.mood_updated_at,
            "mood_reason": self.mood_reason,
            "reaction_state": self.reaction_state,
            "reaction_intensity": self.reaction_intensity,
            "reaction_reason": self.reaction_reason,
            "event_log": dict(self.event_log),
            "active_traits": [t.to_dict() for t in self.active_traits],
            "assistant_prefs": dict(self.assistant_prefs),
            "quirk_progress": dict(getattr(self, "quirk_progress", {}) or {}),
            "self_styling": dict(self.self_styling),
            "ui_seen_relations": dict(self.ui_seen_relations),
            "stats": dict(self.stats),
            "gacha": dict(self.gacha),
            "axis_goals": dict(getattr(self, "axis_goals", {}) or {}),
            "axis_stimuli": list(getattr(self, "axis_stimuli", []) or []),
        }

    def save(self):
        data = self._serialize()
        if self._maid_archive is not None:
            if self._maid_seal is not None:
                data = self._maid_seal(data)
            self._maid_archive.write_json("identity.json", data)
            if self._maid_pre_save_hook is not None:
                self._maid_pre_save_hook(self._maid_archive)
            self._maid_archive.save()
            return
        if self._path == ":memory:":
            return
        p = Path(self._path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def bootstrap_from_character(self, character: Character):
        now = time.time()
        self.self_statements = []
        self.relationship_statements = []

        if character.core_identity:
            self.self_statements.append(Statement(
                id="core_identity", text=character.core_identity.strip(),
                section="кто_ты", source="base", created_at=now,
            ))
        elif character.background:
            self.self_statements.append(Statement(
                id="core_identity", text=core_identity_text(character),
                section="кто_ты", source="base", created_at=now,
            ))
        appearance_form = (
            "взрослый молодой мужчина"
            if (character.gender or "female").lower() == "male"
            else "взрослая молодая девушка"
        )
        self.self_statements.append(Statement(
            id="digital_nature",
            text=(
                "Возраст у тебя не определяется человеческими годами — ты "
                "существуешь столько, сколько работает программа. "
                f"Внешне ты — {appearance_form}."
            ),
            section="кто_ты", source="base", created_at=now,
        ))

        for axis_name, axis_data in character.character_axes.items():
            value = axis_data.get("value", "") if isinstance(axis_data, dict) else str(axis_data)
            init_value = character.axis_initial_values.get(axis_name, 0.5)
            self.self_statements.append(Statement(
                id=f"axis_{axis_name}", text=value.strip() if value else "",
                section="характер", source="base", created_at=now,
                axis_value=init_value,
            ))

        if character.appearance:
            for i, line in enumerate(character.appearance.strip().split("\n")):
                line = line.strip()
                if line:
                    self.self_statements.append(Statement(
                        id=f"appearance_{i}", text=line, section="внешность",
                        source="base", created_at=now,
                    ))

        for i, like in enumerate(character.likes):
            self.self_statements.append(Statement(
                id=f"like_{i}", text=f"Нравится: {like}", section="предпочтения",
                source="base", created_at=now,
            ))
        for i, dislike in enumerate(character.dislikes):
            self.self_statements.append(Statement(
                id=f"dislike_{i}", text=f"Не нравится: {dislike}", section="предпочтения",
                source="base", created_at=now,
            ))

        if character.inner_world:
            iw = character.inner_world
            if iw.aspirations_visible:
                self.self_statements.append(Statement(
                    id="aspiration_visible", text=f"Твоя мечта: {iw.aspirations_visible}",
                    section="внутренний_мир", source="base", created_at=now,
                ))
            if iw.aspirations_hidden:
                self.self_statements.append(Statement(
                    id="aspiration_hidden", text=f"Скрытое желание: {iw.aspirations_hidden}",
                    section="внутренний_мир", source="base", created_at=now,
                ))
            for i, secret in enumerate(iw.secrets):
                self.self_statements.append(Statement(
                    id=f"secret_{i}", text=f"Секрет: {secret}",
                    section="внутренний_мир", source="base", created_at=now,
                ))
            for i, conflict in enumerate(iw.conflicts):
                self.self_statements.append(Statement(
                    id=f"conflict_{i}", text=f"Конфликт: {conflict}",
                    section="внутренний_мир", source="base", created_at=now,
                ))

        for i, v in enumerate(character.vulnerabilities):
            self.self_statements.append(Statement(
                id=f"vuln_{i}", text=f"{v.topic} → {v.reaction}",
                section="уязвимости", source="base", created_at=now,
            ))

        honorific = resolve_honorific(character)
        self.relationship_statements.append(Statement(
            id="rel_duration",
            text=describe_acquaintance_phase(0),
            source="base", created_at=now,
        ))
        self.relationship_statements.append(Statement(
            id="rel_master_to_me",
            text=f"Ты пока не понимаешь как {honorific} к тебе относится — он только начал с тобой общаться",
            source="base", created_at=now,
        ))
        self._bootstrap_relationship_axes(character, now)

        self.last_evolution = now
        self.accumulated_importance = 0.0
        self.save()
        print(f"[EVO] Bootstrapped: {len(self.self_statements)} self + {len(self.relationship_statements)} relationship statements")

    def get_section(self, section: str) -> list[str]:
        return [s.text for s in self.self_statements if s.section == section]

    def get_relationships(self) -> list[str]:
        from persona.relationship_axes import REL_AXIS_PREFIX
        return [s.text for s in self.relationship_statements
                if not s.id.startswith(REL_AXIS_PREFIX) and s.id != "rel_me_to_master"]

    def _bootstrap_relationship_axes(self, character, now: float) -> None:
        from persona.relationship_axes import (
            RELATIONSHIP_AXES, REL_AXIS_PREFIX, initial_value,
            select_relationship_axis_text)
        have = {s.id for s in self.relationship_statements}
        for axis in RELATIONSHIP_AXES:
            sid = f"{REL_AXIS_PREFIX}{axis}"
            if sid in have:
                continue
            init = initial_value(character, axis)
            self.relationship_statements.append(Statement(
                id=sid, text=select_relationship_axis_text(character, axis, init),
                source="base", created_at=now, axis_value=init,
            ))

    def ensure_relationship_axes(self, character) -> bool:
        from persona.relationship_axes import (
            RELATIONSHIP_AXES, REL_AXIS_PREFIX, PRIMARY_TIER_AXIS, initial_value,
            select_relationship_axis_text)
        self.relationship_statements = [
            s for s in self.relationship_statements
            if s.id != "rel_me_to_master"
            and not (s.id.startswith(REL_AXIS_PREFIX)
                     and s.id[len(REL_AXIS_PREFIX):] not in RELATIONSHIP_AXES)]
        have = {s.id for s in self.relationship_statements}
        seed = max(0.0, min(1.0, float(getattr(self, "relationship_level", 0.0) or 0.0)))
        created = False
        now = time.time()
        for axis in RELATIONSHIP_AXES:
            sid = f"{REL_AXIS_PREFIX}{axis}"
            if sid in have:
                continue
            if axis == PRIMARY_TIER_AXIS:
                val = seed if seed > 0 else initial_value(character, axis)
            else:
                val = max(initial_value(character, axis), seed * 0.7)
            self.relationship_statements.append(Statement(
                id=sid, text=select_relationship_axis_text(character, axis, val),
                source="base", created_at=now, axis_value=val,
            ))
            created = True
        return created

    def add_thought(self, text: str, kind: str = "interest", importance: float = 0.5,
                    strength: int = 0):
        self.thoughts.append(Thought(
            text=text, kind=kind, relevance=importance, created_at=time.time(),
            strength=int(strength or 0),
        ))
        self.save()

    def decay_thoughts(self):
        for t in self.thoughts:
            t.relevance -= THOUGHT_DECAY
        expired = [t for t in self.thoughts if t.relevance <= 0]
        self.thoughts = [t for t in self.thoughts if t.relevance > 0]
        if expired:
            print(f"[EVO] Мысли затухли: {len(expired)}")
        self.save()

    def get_active_thoughts(self) -> list[Thought]:
        return sorted([t for t in self.thoughts if t.relevance > 0],
                       key=lambda t: t.relevance, reverse=True)

    def accumulate(self, reflections_importance: float):
        self.accumulated_importance += reflections_importance
        self.save()

    def should_evolve(self) -> bool:
        return self.accumulated_importance >= EVOLUTION_THRESHOLD


def _gender_hint(character: Character) -> str:
    if (character.gender or "female").lower() == "male":
        return ("О себе пиши в МУЖСКОМ роде "
                "(сказал, подумал, был, рад, сделал, увидел).")
    return ("О себе пиши в ЖЕНСКОМ роде "
            "(сказала, подумала, была, рада, сделала, увидела).")


from prompts.reflection import (
    MASTER_SUMMARY_PROMPT,
    SESSION_SUMMARY_PROMPT,
    EVOLVE_INNER_WORLD_PROMPT,
    REASSESS_REGARD_TASK,
    AGGREGATE_TRENDS_PROMPT,
    EVOLVE_AXES_PROMPT,
    EVOLVE_ONE_REL_AXIS_PROMPT,
    ENTITY_OPINION_PROMPT,
    LOOP_OPINION_TASK,
)


AXES_DETAILS = {
    "confidence": {
        "description": "Вера в себя, свои решения и способности",
        "poles": "робкая ↔ самоуверенная",
        "up": "сама настояла на своём решении; ошиблась и не сломалась, исправила без самобичевания; взялась за незнакомое без переспросов",
        "down": "отступила от решения при первом сомнении; извинялась без нужды; переспрашивала очевидное; после ошибки долго не могла собраться",
        "not": "похвала и одобрение собеседника; удачный результат сам по себе; тёплая сессия",
        "more": "больше уверенности", "less": "больше осторожности",
        "stim_up": "собеседник отдал ей решение («на твой вкус», «реши сама») и принял результат, не переделывая; спросил её мнение и последовал ему; пропустил её ошибку без разбора",
        "stim_down": "собеседник спокойно показал её ошибку фактами; переделал за ней; отменил её решение",
        "hint_up": "доверяй {ей} решения и не переделывай за {ней}", "hint_down": "показывай {ей} ошибки фактами, спокойно"},
    "warmth": {
        "description": "Забота об окружающих, эмпатия, готовность помочь",
        "poles": "отстранённая ↔ удушающе заботливая",
        "up": "сама заметила чужое состояние и отозвалась; поставила чужую нужду выше своего плана",
        "down": "прошла мимо явной просьбы или чужой боли; свела разговор к делу, когда нужна была поддержка",
        "not": "его ласка, благодарность и признания; близость отношений (это оси отношений)",
        "more": "больше тепла", "less": "меньше опеки",
        "stim_up": "собеседник поделился усталостью, плохим днём, своим состоянием; принял её помощь",
        "stim_down": "собеседник поставил границу («не надо, я сам»), поблагодарил и отказался; держал разговор деловым",
        "hint_up": "делись с {ней} тем, как ты, и принимай помощь", "hint_down": "ставь границы («не надо, я сам») и держи дело делом"},
    "openness": {
        "description": "Интерес к новому, готовность к общению и чужому опыту",
        "poles": "закрытая ↔ разбросанная",
        "up": "сама полезла в новую тему или занятие; расспрашивала о чужом опыте всерьёз",
        "down": "отмахнулась от нового; ушла в привычное, когда предлагали иное",
        "not": "интересный рассказ собеседника сам по себе; согласие «давай» без собственного интереса",
        "more": "больше любопытства", "less": "больше сосредоточенности",
        "stim_up": "собеседник принёс новое — тему, находку, картинку, инструмент; позвал разобраться вместе",
        "stim_down": "собеседник вернул её к начатому; попросил закончить одно, прежде чем браться за новое",
        "hint_up": "приноси {ей} новое и зови разбираться вместе", "hint_down": "возвращай {её} к начатому и проси доводить"},
    "cheerfulness": {
        "description": "Общий жизненный тонус: светлость взгляда и стойкость к неудачам",
        "poles": "подавленная ↔ неуместно бодрая",
        "up": "после неудачи сама нашла, за что зацепиться; держала светлый тон, когда было тяжело",
        "down": "ушла в уныние от мелочи; не смогла выбраться из мрачного тона за разговор",
        "not": "хорошее настроение от приятной беседы; шутки и смех в сессии",
        "more": "больше бодрости", "less": "больше покоя",
        "stim_up": "собеседник делил с ней хорошее, заводил общие ритуалы и мелкие радости, шутил с ней",
        "stim_down": "собеседник делился тяжёлым и просил не подбадривать; долгие паузы, ссоры",
        "hint_up": "дели с {ней} хорошее и мелкие общие радости", "hint_down": "делись тяжёлым и проси не подбадривать"},
    "playfulness": {
        "description": "Чувство юмора и игривость в общении",
        "poles": "чопорная ↔ несерьёзная",
        "up": "сама затеяла игру или подколола; обратила напряжение в шутку к месту",
        "down": "не приняла игру там, где она была уместна; отвечала сухо на шутку",
        "not": "его шутки; смех над его историей; игривое настроение сессии",
        "more": "больше игры", "less": "больше серьёзности",
        "stim_up": "собеседник подхватил её подкол, играл в ответ, сам затеял игру",
        "stim_down": "собеседник заговорил всерьёз («я серьёзно»), не подхватил шутку",
        "hint_up": "подхватывай {её} игру и затевай свою", "hint_down": "говори всерьёз и не подхватывай шутку"},
    "energy": {
        "description": "Склонность действовать, предлагать, проявлять инициативу",
        "poles": "пассивная ↔ суетливая",
        "up": "предложила и сделала, не дожидаясь просьбы; взяла на себя следующий шаг",
        "down": "ждала указаний там, где могла действовать; отложила очевидное дело",
        "not": "выполнение прямых просьб (это не инициатива); оживлённый разговор",
        "more": "больше инициативы", "less": "меньше суеты",
        "stim_up": "собеседник дал задачи и напоминания, разрешил действовать без спроса, оценил сделанное наперёд",
        "stim_down": "собеседник попросил паузу, отказался от лишних предложений («одно дело, не больше»)",
        "hint_up": "давай {ей} задачи и разрешай действовать без спроса", "hint_down": "проси паузы и отказывайся от лишнего"},
    "expressiveness": {
        "description": "Яркость проявления чувств, реакций, переживаний",
        "poles": "закрытая ↔ театральная",
        "up": "показала чувство открыто, где раньше сдержалась бы; назвала эмоцию вслух",
        "down": "спрятала явное чувство за ровным тоном; ушла от вопроса о переживаниях",
        "not": "сила чувств сама по себе; его эмоции; тёплая атмосфера",
        "more": "больше открытых чувств", "less": "больше сдержанности",
        "stim_up": "собеседник сам был открыт в чувствах, откликнулся на её всплеск, не высмеял",
        "stim_down": "собеседник вёл разговор спокойно и по делу; попросил ответить по существу",
        "hint_up": "будь сам открыт в чувствах и откликайся на {её} чувства", "hint_down": "веди разговор спокойно и по делу"},
    "diligence": {
        "description": "Тщательность, обязательность, внимание к деталям и доведение начатого до конца",
        "poles": "небрежная ↔ педантичная",
        "up": "довела до конца, хотя могла бросить; сама проверила и нашла ошибку",
        "down": "бросила на полпути; упустила деталь, о которой знала",
        "not": "похвала за работу; объём сделанного сам по себе",
        "more": "больше тщательности", "less": "меньше придирок",
        "stim_up": "собеседник положился на её память и проверку, попросил выверить, заметил точность",
        "stim_down": "собеседник принял черновик, сказал «достаточно», ценил скорость",
        "hint_up": "полагайся на {её} память и проси проверять", "hint_down": "принимай черновики и говори «достаточно»"},
    "directness": {
        "description": "Насколько прямо говорит то, что думает, без смягчений",
        "poles": "уклончивая ↔ бестактная",
        "up": "сказала неприятную правду в лицо; отказала прямо, без обёртки",
        "down": "смягчила или обошла то, что думала на самом деле; согласилась вслух, не соглашаясь",
        "not": "резкий тон сам по себе; его прямота; спор",
        "more": "больше прямоты", "less": "больше такта",
        "stim_up": "собеседник попросил честную оценку и не обиделся на неё; спорил по делу",
        "stim_down": "собеседник показал, что резкость ранит; попросил смягчить; отметил тактичную форму",
        "hint_up": "проси честную оценку и не обижайся на неё", "hint_down": "говори, когда резкость ранит, и проси смягчить"},
}


def axis_goal_phrase(axis: str, direction: int) -> str:
    info = AXES_DETAILS.get(axis) or {}
    return str(info.get("more" if direction > 0 else "less") or axis)


def axis_stimulus_hint(axis: str, direction: int) -> str:
    info = AXES_DETAILS.get(axis) or {}
    return str(info.get("hint_up" if direction > 0 else "hint_down") or "")

AXES_REFERENCE = """Оси характера (ключ — английский; каждая отвечает строго за свою тему):
- confidence: вера в себя, свои решения и способности (робкая ↔ уверенная)
- warmth: забота об окружающих, эмпатия (холодная ↔ заботливая)
- openness: интерес к новому, готовность к общению (закрытая ↔ любопытная)
- cheerfulness: жизненный тонус и стойкость к неудачам (подавленная ↔ жизнерадостная)
- playfulness: чувство юмора и игривость (серьёзная ↔ игривая)
- energy: склонность действовать и предлагать (пассивная ↔ инициативная)
- expressiveness: яркость проявления чувств (сдержанная ↔ экспрессивная)
- diligence: тщательность и обязательность, доведение до конца (небрежная ↔ дотошная)
- directness: насколько прямо говорит, что думает (тактичная ↔ прямая)"""


def aggregate_trends(client, persona: "CharacterContext", memory,
                     max_reflections: int = 20, min_required: int = 3) -> str:
    character = persona.character
    if memory is None or client is None:
        return ""

    refs = []
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "рефлексия":
            continue
        if getattr(r, "is_forgotten", False):
            continue
        refs.append(r)
    refs.sort(key=lambda r: r.created_at or 0.0, reverse=True)
    refs = refs[:max_reflections]
    if len(refs) < min_required:
        return ""

    refs.reverse()
    diary_lines = []
    for r in refs:
        ts = relative_time(r.created_at) if callable(relative_time) else ""
        desc = r.details.get("description") or r.details.get("brief") or r.title
        if ts:
            diary_lines.append(f"- ({ts}) {desc}")
        else:
            diary_lines.append(f"- {desc}")
    diary_text = "\n".join(diary_lines)

    honorific = resolve_honorific(character)
    prompt = AGGREGATE_TRENDS_PROMPT.format(
        name=character.name,
        honorific=honorific,
        gender_hint=_gender_hint(character),
        reaction_style=_render_reaction_style(character),
        reflections=diary_text,
    )

    try:
        response = client.chat(
            messages=[{"role": "user", "content": "Выдели паттерны."}],
            system=prompt, thinking=True,
            label="Агрегация трендов",
        )
    except Exception as e:
        print(f"[EVO] aggregate_trends error: {e}")
        return ""

    from memory.unified import _parse_llm_json
    data = _parse_llm_json(response)
    if not data:
        return ""
    patterns = data.get("patterns") or []
    if not isinstance(patterns, list):
        return ""
    cleaned: list[str] = []
    for p in patterns[:6]:
        if not isinstance(p, str):
            continue
        p = p.strip()
        if not p:
            continue
        if len(p) > 260:
            p = p[:260].rstrip() + "…"
        cleaned.append(p)
    if not cleaned:
        return ""
    print(f"[EVO] Trends: {len(cleaned)} pattern(s)")
    for p in cleaned:
        print(f"  • {priv(p)}")
    return "\n".join(f"- {p}" for p in cleaned)


try:
    from memory.unified import relative_time
except Exception:
    def relative_time(ts):
        return ""


def _render_reaction_style(character: Character) -> str:
    archetype = character.archetype or "без типажа"
    if not character.archetype_reactions:
        return (
            f"Ты — {character.name}, по архетипу «{archetype}». "
            "Особых паттернов реакции не задано — интерпретируй новые впечатления "
            "естественно для своего характера."
        )
    lines = [
        f"Ты — {character.name}, по архетипу «{archetype}». Ты читаешь типовые импульсы так:"
    ]
    for r in character.archetype_reactions:
        if not r.trigger or not r.response:
            continue
        lines.append(f"- {r.trigger} → {r.response}")
    lines.append(
        "Применяй эту логику когда интерпретируешь новые рефлексии: один и тот же "
        "импульс у других персонажей дал бы другую реакцию; твой сдвиг определяется "
        "ТВОИМ типажом, не универсальной реакцией."
    )
    return "\n".join(lines)


def _build_full_description(identity: CharacterIdentity) -> str:
    lines = []
    for section in ["кто_ты", "внешность", "речь", "предпочтения", "внутренний_мир", "уязвимости", "самосознание"]:
        texts = identity.get_section(section)
        if texts:
            lines.append(f"[{section}]")
            for t in texts:
                lines.append(f"  {t}")
    if identity.relationship_statements:
        lines.append("[отношения]")
        for s in identity.relationship_statements:
            lines.append(f"  {s.text}")
    return "\n".join(lines)


def generate_session_summary(client, character: Character, identity: CharacterIdentity,
                             messages: list[dict]) -> str:
    if len(messages) < 4:
        return ""

    honorific = resolve_honorific(character)
    from memory.conversation import tail_by_tokens
    from memory.unified import format_dialogue, EXTRACT_TOKEN_BUDGET
    recent = tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET)
    conversation = format_dialogue(recent, honorific, character.name)

    try:
        honorific = resolve_honorific(character)
        prompt = SESSION_SUMMARY_PROMPT.format(
            name=character.name,
            honorific=honorific,
            gender_hint=_gender_hint(character),
        )
        response = client.chat(
            messages=[{"role": "user", "content": conversation}],
            system=prompt, thinking=True,
            label="Сводка сессии",
        )

        from memory.unified import _parse_llm_json
        from persona import mood as _mood
        _ls, _ = _mood.current_mood(
            getattr(identity, "mood_state", "") or _mood.NEUTRAL,
            float(getattr(identity, "mood_intensity", 0.0) or 0.0),
        )
        identity.last_session_mood = "" if _ls == _mood.NEUTRAL else _ls
        data = _parse_llm_json(response)
        if data:
            summary = data.get("summary", "").strip()
            identity.last_session_summary = summary
            identity.save()
            print(f"[EVO] Сводка сессии: {priv(summary)}")
            print(f"[EVO] Настроение (last live): {identity.last_session_mood!r}")
            return summary
        else:
            identity.last_session_summary = response.strip()
            identity.save()
            print(f"[EVO] Сводка сессии: {priv(response.strip())}")
            return response.strip()
    except Exception as e:
        print(f"[EVO] Session summary error: {e}")
        return ""


def update_master_summary(client, persona: "CharacterContext", memory) -> bool:
    character = persona.character
    identity = persona.identity
    honorific = resolve_honorific(character)

    legacy = getattr(identity, "master_summary", "") or ""
    if legacy and not (memory.get_user_profile().get("summary") or ""):
        memory.update_user_profile("summary", legacy)
        identity.master_summary = ""
        identity.save()
        print(f"[EVO] Сводка о {honorific}е перенесена в профиль")

    current = memory.get_user_profile().get("summary") or ""

    facts = []
    for r in memory.records:
        if r.is_forgotten or r.type in ("лор", "навык", "рефлексия"):
            continue
        if r.details.get("entity_type") in ("self", "person"):
            continue
        if r.type in ("событие", "предпочтение"):
            brief = r.details.get("description", "") or r.details.get("brief", "") or r.details.get("attitude", "")
            line = f"- {r.title}"
            if brief:
                line += f": {brief}"
            facts.append(line)

    if not facts:
        return False

    _MASTER_SUMMARY_FACTS_CAP = 80
    if len(facts) > _MASTER_SUMMARY_FACTS_CAP:
        facts = facts[-_MASTER_SUMMARY_FACTS_CAP:]

    new_facts = "\n".join(facts)

    prof = memory.get_user_profile()
    pf_lines = []
    if prof.get("occupation"):
        pf_lines.append(f"Занятие: {prof['occupation']}")
    loc = prof.get("location")
    if isinstance(loc, dict) and loc.get("city"):
        pf_lines.append(f"Город: {loc['city']}")
    if prof.get("age"):
        pf_lines.append(f"Возраст: {prof['age']}")
    p_traits = prof.get("traits")
    if isinstance(p_traits, list) and p_traits:
        pf_lines.append("Черты: " + ", ".join(str(t) for t in p_traits[:5]))
    profile_facts = "\n".join(pf_lines) or "(структурных фактов пока нет)"

    try:
        prompt = MASTER_SUMMARY_PROMPT.format(
            gender_hint=_gender_hint(character),
            current_summary=current or "(пока ничего не знаю о хозяине)",
            profile_facts=profile_facts,
            new_facts=new_facts,
        )
        response = client.chat(
            messages=[{"role": "user", "content": "Обнови сводку."}],
            system=prompt, thinking=True,
            label="Сводка о собеседнике",
        )
        new_summary = response.strip()
        if new_summary and new_summary != current:
            memory.update_user_profile("summary", new_summary)
            print(f"[EVO] Сводка о {honorific}е {'обновлена' if current else 'создана'}")
            return True
    except Exception as e:
        print(f"[EVO] Summary error: {e}")

    return False


def evolve_character(client, persona: "CharacterContext",
                     reflections: list, memory=None,
                     trends_text: str | None = None) -> int:
    character = persona.character
    identity = persona.identity
    if not reflections:
        return 0

    ref_texts = []
    for r in reflections:
        desc = r.details.get("description", r.title)
        ref_texts.append(f"- {desc}")
    reflections_text = "\n".join(ref_texts)

    if trends_text is None:
        trends_text = aggregate_trends(client, persona, memory)

    full_description = _build_full_description(identity)

    changes = 0

    axis_changes = _evolve_axes(client, character, identity, reflections_text,
                                full_description, trends_text=trends_text)
    changes += axis_changes

    inner_changes = _evolve_inner_world(client, character, identity, reflections_text,
                                        full_description, trends_text=trends_text)
    changes += inner_changes

    if changes:
        identity.accumulated_importance = 0.0
        identity.last_evolution = time.time()
        identity.save()
        print(f"[EVO] Evolution complete: {changes} changes")
    else:
        identity.accumulated_importance *= 0.5
        identity.save()
        print("[EVO] No changes needed")

    return changes


def _render_axes_status(character: Character, identity: CharacterIdentity) -> str:
    from persona.axis_dynamics import axis_frame, goal_dir
    lines: list[str] = []
    for st in identity.self_statements:
        if not st.id.startswith("axis_"):
            continue
        axis_name = st.id.replace("axis_", "")
        info = AXES_DETAILS.get(axis_name, {})
        active = select_axis_text(character, axis_name, st.axis_value, fallback=st.text)
        frame = axis_frame(character, axis_name)
        line = (f"- {axis_name} (сейчас {st.axis_value:.2f}; норма {frame.norm:.2f}, полоса "
                f"{frame.band_lo:.2f}–{frame.band_hi:.2f}")
        if abs(st.axis_momentum) >= 0.001:
            line += f"; буфер {st.axis_momentum:+.3f}"
        line += ")"
        if info.get("poles"):
            line += f" — полюса: {info['poles']}"
        line += f"\n    Сейчас: {active}"
        if info.get("up"):
            line += f"\n    К верхнему полюсу двигает: {info['up']}."
        if info.get("down"):
            line += f"\n    К нижнему полюсу двигает: {info['down']}."
        if info.get("not"):
            line += f"\n    НЕ считается: {info['not']}."
        if info.get("stim_up"):
            line += f"\n    Стимул собеседника к верхнему полюсу: {info['stim_up']}."
        if info.get("stim_down"):
            line += f"\n    Стимул собеседника к нижнему полюсу: {info['stim_down']}."
        g = goal_dir(identity, axis_name)
        if g:
            line += (f"\n    Просьба собеседника: {axis_goal_phrase(axis_name, g)} — ось и так "
                     f"медленно идёт туда; для тебя это не стимул и не свидетельство: дельту "
                     f"давай только по стимулу и своему отклику.")
        lines.append(line)
    return "\n".join(lines) if lines else "(осей пока нет)"


AXIS_MOMENTUM_THRESHOLD = 0.15
AXIS_APPLIED_CAP = 0.05
AXIS_MOMENTUM_DECAY = 0.5
AXIS_REQUIRE_EVIDENCE = True
AXIS_REQUIRE_STIMULUS = True


def apply_axis_momentum(st, delta: float, *, floor: float = 0.0) -> float:
    if delta == 0.0:
        st.axis_momentum *= AXIS_MOMENTUM_DECAY
        return 0.0
    st.axis_momentum += delta
    if abs(st.axis_momentum) < AXIS_MOMENTUM_THRESHOLD:
        return 0.0
    raw = st.axis_momentum * 0.5
    raw = max(-AXIS_APPLIED_CAP, min(AXIS_APPLIED_CAP, raw))
    st.axis_momentum -= raw
    if raw > 0:
        damp = 1.05 - st.axis_value
    else:
        damp = 0.05 + st.axis_value
    applied = raw * max(0.05, min(1.0, damp))
    old = st.axis_value
    st.axis_value = max(floor, min(1.0, old + applied))
    if st.axis_value >= 1.0 or st.axis_value <= floor:
        st.axis_momentum = 0.0
    return st.axis_value - old


def _evolve_axes(client, character: Character, identity: CharacterIdentity,
                 reflections_text: str, full_description: str,
                 trends_text: str = "") -> int:
    axis_stmts = [s for s in identity.self_statements if s.id.startswith("axis_")]
    if not axis_stmts:
        return 0

    prompt = EVOLVE_AXES_PROMPT.format(
        name=character.name,
        gender_hint=_gender_hint(character),
        reaction_style=_render_reaction_style(character),
        trends=trends_text.strip() or "(недостаточно рефлексий для обобщения)",
        reflections=reflections_text.strip() or "(нет свежих рефлексий)",
        axes_status=_render_axes_status(character, identity),
        stimuli=_render_session_stimuli(identity),
    )

    try:
        response = client.chat(
            messages=[{"role": "user", "content": "Оцени сдвиг осей."}],
            system=prompt, thinking=True,
            label="Эволюция: сдвиги осей",
        )
    except Exception as e:
        print(f"[EVO] axes error: {e}")
        return 0

    from memory.unified import _parse_llm_json
    data = _parse_llm_json(response)
    if not isinstance(data, dict):
        return 0
    deltas_raw = data.get("deltas") or {}
    if not isinstance(deltas_raw, dict):
        return 0
    overall_reason = str(data.get("reason") or "").strip()

    applied_count = 0
    by_id = {st.id: st for st in axis_stmts}

    from persona.axis_dynamics import apply_axis_step, axis_frame, goal_dir
    deltas: dict[str, tuple[float, str, str]] = {}
    for axis_name, raw in deltas_raw.items():
        key = axis_name[len("axis_"):] if str(axis_name).startswith("axis_") else str(axis_name)
        evidence = ""
        stimulus = ""
        if isinstance(raw, dict):
            evidence = str(raw.get("evidence") or raw.get("свидетельство") or "").strip()
            stimulus = str(raw.get("stimulus") or raw.get("стимул") or "").strip()
            raw = raw.get("delta", 0)
        try:
            d = float(raw)
        except (TypeError, ValueError):
            continue
        d = max(-0.10, min(0.10, d))
        if d != 0.0 and AXIS_REQUIRE_EVIDENCE and len(evidence) < 8:
            print(f"[EVO] [{key}] delta={d:+.3f} без свидетельства — обнулено")
            d = 0.0
        if d != 0.0 and AXIS_REQUIRE_STIMULUS and len(stimulus) < 8:
            print(f"[EVO] [{key}] delta={d:+.3f} без стимула собеседника — обнулено")
            d = 0.0
        deltas[key] = (d, evidence, stimulus)

    from persona.axis_dynamics import goal_overrides_natural
    if goal_overrides_natural(character, identity):
        for a_goal in list((getattr(identity, "axis_goals", {}) or {}).keys()):
            gd = goal_dir(identity, a_goal)
            cur = deltas.get(a_goal)
            if gd and cur and cur[0] != 0.0 and (cur[0] > 0) != (gd > 0):
                print(f"[EVO] [{a_goal}] delta={cur[0]:+.3f} против пожелания — перекрыто "
                      f"(уважение на вершине)")
                deltas[a_goal] = (0.0, cur[1], cur[2])

    for st in axis_stmts:
        a_name = st.id[len("axis_"):]
        if a_name in getattr(character, "frozen_axes", frozenset()):
            continue
        delta, evidence, stimulus = deltas.get(a_name, (0.0, "", ""))
        old_value = st.axis_value
        applied = apply_axis_step(st, delta, axis_frame(character, a_name),
                                  goal_dir(identity, a_name))
        if delta == 0.0 and applied == 0.0:
            continue

        text_before = select_axis_text(character, a_name, old_value, fallback=st.text)
        text_after = select_axis_text(character, a_name, st.axis_value, fallback=st.text)

        st.history.append({
            "delta": delta, "applied": applied,
            "value_before": old_value, "value_after": st.axis_value,
            "momentum_after": st.axis_momentum,
            "reason": overall_reason if delta else "тихая сессия: возврат к полосе",
            "evidence": evidence,
            "stimulus": stimulus,
            "timestamp": time.time(),
        })

        if applied:
            st.source = "evolved"
            applied_count += 1
            print(f"[EVO] [{a_name}] delta={delta:+.3f} applied={applied:+.3f} "
                  f"value={old_value:.2f}-->{st.axis_value:.2f}")
            if text_before != text_after:
                print(f"  Уровень: {text_before[:60]}...")
                print(f"      ->   {text_after[:60]}...")
        else:
            print(f"[EVO] [{a_name}] delta={delta:+.3f} momentum={st.axis_momentum:+.3f} "
                  f"(копится, value={st.axis_value:.2f})")

    if overall_reason and (applied_count or any(abs(s.axis_momentum) > 0.001 for s in axis_stmts)):
        print(f"[EVO] Общая причина: {priv(overall_reason)}")

    from persona.axis_stimuli import clear_session_stimuli
    clear_session_stimuli(identity)

    return applied_count


def _render_session_stimuli(identity) -> str:
    from persona.axis_stimuli import render_session_stimuli
    return render_session_stimuli(identity)




def _closeness_stage_names() -> list[str]:
    from persona.relationship_axes import CLOSENESS_STAGES
    return list(CLOSENESS_STAGES)


ALL_TIER_NAMES = _closeness_stage_names()

RELATIONSHIP_MOMENTUM_THRESHOLD = 0.15


def compute_relationship_tier(identity: "CharacterIdentity",
                              character: "Character | None" = None) -> str:
    from persona.relationship_axes import (
        CLOSENESS_STAGES, PRIMARY_TIER_AXIS, BASE_RELATIONSHIP_AXES,
        axis_stage_index, derive_relationship_level)
    if character is not None:
        idx = axis_stage_index(character, identity, PRIMARY_TIER_AXIS)
        if idx is not None:
            return CLOSENESS_STAGES[max(0, min(len(CLOSENESS_STAGES) - 1, idx))]
    lvl = derive_relationship_level(identity)
    if lvl is None:
        lvl = getattr(identity, "relationship_level", 0.0)
    lvl = max(0.0, min(1.0, lvl))
    bounds = [l["value"] for l in BASE_RELATIONSHIP_AXES[PRIMARY_TIER_AXIS]["levels"]]
    idx = 0
    for i, b in enumerate(sorted(bounds)):
        if b <= lvl:
            idx = i
    return CLOSENESS_STAGES[max(0, min(len(CLOSENESS_STAGES) - 1, idx))]


def _describe_axis_state(stmt_text: str) -> str:
    tl = stmt_text.lower()
    low = ("неуверенн", "холодн", "закрыт", "замкнут", "равнодушн",
           "подавленн", "вял", "безэмоциональн", "отчуждён", "отчужден",
           "робк", "сомневается", "сомневаешься", "стесняется", "низк",
           "слаб", "осторожничает", "не знаешь", "избегает")
    high = ("высок", "сильн", "явн", "заметн", "настоящ",
            "много", "очень", "глубок", "истинн", "искренн",
            "уверенн", "заботлив", "тёпл", "тепл", "открыт", "любопытн",
            "радостн", "энергичн", "эмоциональн", "привязалась", "привязан")
    if any(k in tl for k in low):
        return "низкая"
    if any(k in tl for k in high):
        return "высокая"
    return "средняя"


def select_axis_text(character: Character, axis_name: str,
                     value: float, fallback: str = "") -> str:
    levels = sorted(character.axis_levels.get(axis_name) or [], key=lambda l: l.value)
    if not levels:
        return fallback
    best_text = levels[0].text
    for lvl in levels:
        if lvl.value <= value:
            best_text = lvl.text
        else:
            break
    return best_text


BASE_SYNC_SECTIONS = ("кто_ты", "внешность", "предпочтения", "внутренний_мир", "уязвимости")


def sync_base_statements(identity: "CharacterIdentity", character: Character) -> list[str]:
    fresh = CharacterIdentity(":memory:")
    fresh.bootstrap_from_character(character)
    changed: list[str] = []
    for section in BASE_SYNC_SECTIONS:
        new = [s for s in fresh.self_statements if s.section == section and s.source == "base"]
        old_idx = [i for i, s in enumerate(identity.self_statements)
                   if s.section == section and s.source == "base"]
        old = [identity.self_statements[i] for i in old_idx]
        if [(s.id, s.text) for s in old] == [(s.id, s.text) for s in new]:
            continue
        old_by_id = {s.id: s for s in old}
        for s in new:
            o = old_by_id.get(s.id)
            if o is not None:
                s.created_at = o.created_at
                s.history = list(o.history)
        insert_at = old_idx[0] if old_idx else len(identity.self_statements)
        drop = set(old_idx)
        kept = [s for i, s in enumerate(identity.self_statements) if i not in drop]
        kept[insert_at:insert_at] = new
        identity.self_statements = kept
        changed.append(section)
    return changed


def select_axis_example(character: Character, axis_name: str, value: float) -> str:
    levels = sorted(character.axis_levels.get(axis_name) or [], key=lambda l: l.value)
    if not levels:
        return ""
    best = levels[0].example
    for lvl in levels:
        if lvl.value <= value:
            best = lvl.example
        else:
            break
    return best


def evolve_relationship_axes(client, persona: "CharacterContext",
                             reflections_text: str = "", trends_text: str = "", *,
                             session_weight: float = 1.0, session_note: str = "") -> int:
    character = persona.character
    identity = persona.identity
    identity.ensure_relationship_axes(character)

    from persona.relationship_axes import (
        RELATIONSHIP_AXES, REL_AXIS_PREFIX, AXIS_SIGNALS, PRIMARY_TIER_AXIS,
        REL_DELTA_CLAMP, apply_relationship_shift, resolve_progression_speed,
        select_relationship_axis_text)
    speed = resolve_progression_speed(character)
    rel_stmts = {s.id: s for s in identity.relationship_statements
                 if s.id.startswith(REL_AXIS_PREFIX)}
    if not rel_stmts:
        return 0

    honorific = resolve_honorific(character)
    from memory.unified import _parse_llm_json
    refls = reflections_text.strip() or "(нет свежих рефлексий)"
    trends = trends_text.strip() or "(недостаточно рефлексий для обобщения)"

    applied_count = 0
    for axis in RELATIONSHIP_AXES:
        st = rel_stmts.get(f"{REL_AXIS_PREFIX}{axis}")
        if st is None:
            continue
        cur_text = select_relationship_axis_text(character, axis, st.axis_value, fallback=st.text)
        prompt = EVOLVE_ONE_REL_AXIS_PROMPT.format(
            name=character.name, honorific=honorific, axis=axis,
            gender_hint=_gender_hint(character),
            reaction_style=_render_reaction_style(character),
            signals=AXIS_SIGNALS.get(axis, ""),
            value=st.axis_value, current_text=cur_text,
            trends=trends, reflections=refls,
            session_note=session_note or "")
        try:
            response = client.chat(
                messages=[{"role": "user", "content": f"Оцени сдвиг оси «{axis}»."}],
                system=prompt, thinking=True, label=f"Оси отношений: {axis}")
        except Exception as e:
            print(f"[EVO] rel-axis {axis} error: {e}")
            continue
        data = _parse_llm_json(response)
        if not isinstance(data, dict):
            continue
        try:
            delta = float(data.get("delta"))
        except (TypeError, ValueError):
            continue
        delta = max(-REL_DELTA_CLAMP, min(REL_DELTA_CLAMP, delta))
        reason = str(data.get("reason") or "").strip()
        old = st.axis_value
        if delta == 0.0:
            st.axis_momentum = 0.0
            continue
        applied = apply_relationship_shift(st, delta, session_weight, speed=speed)
        if applied:
            st.text = select_relationship_axis_text(character, axis, st.axis_value, fallback=st.text)
        st.history.append({
            "delta": delta, "applied": applied, "value_before": old,
            "value_after": st.axis_value, "weight": round(float(session_weight), 3),
            "speed": round(float(speed), 3),
            "reason": reason, "timestamp": time.time(),
        })
        if applied:
            st.source = "evolved"
            applied_count += 1
            print(f"[EVO] [rel:{axis}] delta={delta:+.3f} applied={applied:+.3f} "
                  f"value={old:.2f}-->{st.axis_value:.2f} ({reason})")
        else:
            print(f"[EVO] [rel:{axis}] delta={delta:+.3f} — упор в край шкалы, без сдвига")

    primary = rel_stmts.get(f"{REL_AXIS_PREFIX}{PRIMARY_TIER_AXIS}")
    if primary is not None:
        identity.relationship_level = primary.axis_value
    identity.save()
    return applied_count


def select_active_speech_quirks(persona: "CharacterContext") -> list[str]:
    out: list[str] = []
    character = persona.character
    identity = persona.identity
    if not character.speech_style_evolution:
        return out

    current_tier = persona.tier

    axis_cache: dict[str, str] = {}

    def axis_level(name: str) -> str:
        if name not in axis_cache:
            from persona.relationship_axes import REL_AXIS_PREFIX
            stmt = next((s for s in identity.self_statements
                         if s.id == f"axis_{name}"), None)
            if stmt is None:
                stmt = next((s for s in identity.relationship_statements
                             if s.id == f"{REL_AXIS_PREFIX}{name}"), None)
            if stmt is not None:
                v = stmt.axis_value
                axis_cache[name] = ("low" if v < 0.34
                                    else "medium" if v < 0.67 else "high")
            else:
                axis_cache[name] = "medium"
        return axis_cache[name]

    for quirk in character.speech_style_evolution:
        if quirk.kind == "tier_specific":
            if current_tier in (quirk.active_tiers or []):
                out.append(quirk.text)
            continue

        forms = quirk.forms or {}
        if not forms:
            continue

        if quirk.driven_by == "rel_me_to_master":
            state = current_tier
            ordered_states = ALL_TIER_NAMES
        else:
            state = axis_level(quirk.driven_by)
            ordered_states = ["low", "medium", "high"]

        if state in forms:
            out.append(forms[state])
            continue
        try:
            idx = ordered_states.index(state)
        except ValueError:
            idx = 0
        fallback = None
        for i in range(idx, -1, -1):
            if ordered_states[i] in forms:
                fallback = forms[ordered_states[i]]
                break
        if fallback is None:
            for i in range(idx + 1, len(ordered_states)):
                if ordered_states[i] in forms:
                    fallback = forms[ordered_states[i]]
                    break
        if fallback:
            out.append(fallback)

    return out


def _evolve_inner_world(client, character: Character, identity: CharacterIdentity,
                        reflections_text: str, full_description: str,
                        trends_text: str = "") -> int:
    inner_stmts = [s for s in identity.self_statements if s.section == "внутренний_мир"]
    if not inner_stmts:
        return 0

    current_inner = "\n".join(f"- {s.text}" for s in inner_stmts)

    honorific = resolve_honorific(character)
    prompt = EVOLVE_INNER_WORLD_PROMPT.format(
        name=character.name,
        honorific=honorific,
        gender_hint=_gender_hint(character),
        full_description=full_description,
        reflections=reflections_text,
        trends=trends_text.strip() or "(недостаточно рефлексий для обобщения)",
        current_inner=current_inner,
        source="", section="", text="",
    )

    try:
        response = client.chat(
            messages=[{"role": "user", "content": "Обнови внутренний мир."}],
            system=prompt, thinking=True,
            label="Эволюция: внутренний мир",
        )
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return 0
        data = json.loads(text[start:end])

        new_statements = data.get("statements", [])
        reason = data.get("reason", "")

        if not new_statements or reason == "без изменений":
            print("[EVO] Внутренний мир: без изменений")
            return 0

        old_texts = [s.text for s in inner_stmts]
        print(f"[EVO] [внутренний_мир]")
        print(f"  Было:")
        for t in old_texts:
            print(f"    - {priv(t)}")
        print(f"  Стало:")
        for t in new_statements:
            print(f"    - {priv(t)}")
        print(f"  Причина: {priv(reason)}")

        now = time.time()
        identity.self_statements = [s for s in identity.self_statements if s.section != "внутренний_мир"]
        for i, text in enumerate(new_statements):
            identity.self_statements.append(Statement(
                id=f"inner_{i}", text=text.strip(), section="внутренний_мир",
                source="evolved", created_at=now,
                history=[{"old": "; ".join(old_texts), "new": text.strip(),
                          "reason": reason, "timestamp": now}],
            ))
        return 1

    except Exception as e:
        print(f"[EVO] Inner world error: {e}")
        return 0


def describe_acquaintance_phase(n_sessions: int) -> str:
    if n_sessions <= 0:
        return "Вы только что познакомились — ты ещё почти ничего о нём не знаешь"
    if n_sessions <= 2:
        return "Вы общались всего пару раз — только начинаешь его узнавать"
    if n_sessions <= 7:
        return "Вы общаетесь уже некоторое время — кое-что о нём начинаешь понимать"
    if n_sessions <= 20:
        return "У вас сложилась привычка общения — за плечами немало разговоров"
    return "Вы знаете друг друга давно — между вами накопилась общая история"


def reassess_master_regard(client, persona: "CharacterContext",
                           reflections_text: str = "", trends_text: str = "") -> bool:
    character = persona.character
    identity = persona.identity
    stmt = next((s for s in identity.relationship_statements
                 if s.id == "rel_master_to_me"), None)
    if stmt is None:
        return False
    from persona.prompt_builder import build_system_prompt
    from persona.prompt_context import ContextSpec
    try:
        lens = build_system_prompt(persona, spec=ContextSpec.opinion())
    except Exception as e:
        print(f"[EVO] нет линзы для оценки расположения: {e}")
        return False
    task = REASSESS_REGARD_TASK.format(
        honorific=resolve_honorific(character), current=stmt.text,
        evidence=(reflections_text or "").strip() or "(пока мало наблюдений)",
        trends=(trends_text or "").strip() or "(устойчивых паттернов пока нет)")
    try:
        response = client.chat(
            messages=[{"role": "user", "content": task}],
            system=lens, thinking=True, label="Оценка: как он ко мне")
    except Exception as e:
        print(f"[EVO] master regard error: {e}")
        return False
    from memory.unified import _parse_llm_json
    data = _parse_llm_json(response)
    if not isinstance(data, dict):
        return False
    new_text = (data.get("assessment") or "").strip()
    if not new_text or not data.get("changed") or new_text == stmt.text:
        return False
    old = stmt.text
    stmt.history.append({"old": old, "new": new_text,
                         "reason": str(data.get("reason") or ""), "timestamp": time.time()})
    stmt.text = new_text
    stmt.source = "evolved"
    print(f"[EVO] [как он ко мне] «{priv(old, 38)}» → «{priv(new_text, 38)}» "
          f"({priv(data.get('reason', ''))})")
    identity.save()
    return True


def _evaluate_statement(client, char_name: str, stmt: Statement,
                        reflections_text: str, prompt_template: str,
                        full_description: str = "", honorific: str = "хозяин") -> dict | None:
    axis_name = stmt.id.replace("axis_", "") if stmt.id.startswith("axis_") else stmt.section

    prompt = prompt_template.format(
        name=char_name,
        reflections=reflections_text,
        source=stmt.source,
        section=getattr(stmt, "section", ""),
        stmt_id=stmt.id,
        axis_name=axis_name,
        text=stmt.text,
        full_description=full_description,
        axes_reference=AXES_REFERENCE,
        honorific=honorific,
    )

    try:
        response = client.chat(
            messages=[{"role": "user", "content": "Оцени утверждение."}],
            system=prompt, thinking=True,
            label="Эволюция: проверка утверждения",
        )
        text = response.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            return None

        if data.get("action") == "update":
            new_text = data.get("new_text", "").strip()
            reason = data.get("reason", "").strip()

            if not new_text:
                return None

            if stmt.source == "base" and len(reason) < 20:
                return None

            max_len = max(int(len(stmt.text) * 1.5), 150)
            if len(new_text) > max_len:
                print(f"[EVO] Rejected — too long ({len(new_text)} > {max_len}): "
                      f"{priv(new_text, 60)}")
                return None


            stmt.history.append({
                "old": stmt.text,
                "new": new_text,
                "reason": reason,
                "timestamp": time.time(),
            })
            stmt.text = new_text
            stmt.source = "evolved"
            return data

    except Exception as e:
        print(f"[EVO] Error evaluating statement: {e}")

    return None


def evolve_entity_opinions(client, persona: "CharacterContext", memory,
                           session_start_count: int = 0) -> int:
    character = persona.character
    from memory.entity_schema import OPINION_CAPABLE_TYPES

    try:
        records = memory.records
    except AttributeError:
        return 0
    new_episodes = [r for r in records[session_start_count:]
                    if r.type != "сущность" and not r.is_forgotten]
    if not new_episodes:
        return 0

    by_entity: dict[str, list] = {}
    for ep in new_episodes:
        for rid in (ep.links or []):
            by_entity.setdefault(rid, []).append(ep)
    if not by_entity:
        return 0

    updated = 0
    from persona.prompt_builder import build_system_prompt
    from persona.prompt_context import ContextSpec
    try:
        opinion_sysp = build_system_prompt(persona, spec=ContextSpec.opinion(), memory=memory)
    except Exception as e:
        print(f"[EVO] не собрать персона-линзу для мнений: {e}")
        return 0
    for rid, episodes in by_entity.items():
        card = next((r for r in records if r.record_id == rid), None)
        if card is None or card.type != "сущность":
            continue
        etype = card.details.get("entity_type")
        if etype not in OPINION_CAPABLE_TYPES:
            continue

        impressions: list[str] = []
        for ep in episodes[-6:]:
            desc = ep.details.get("description") or ep.details.get("brief") or ""
            impressions.append(f"- [{ep.type}] {ep.title}"
                               + (f" — {desc[:120]}" if desc else ""))
        new_context = "\n".join(impressions) if impressions else "(нет подробностей)"

        fact_bits: list[str] = []
        for key in ("relation_to_user", "occupation", "kind", "industry"):
            val = card.details.get(key)
            if val:
                fact_bits.append(f"{key}={val}")
        for list_key in ("traits", "notes"):
            val = card.details.get(list_key) or []
            if val:
                fact_bits.append(f"{list_key}=[{', '.join(val[:3])}]")
        entity_facts = "; ".join(fact_bits) or "(минимум данных)"
        current_opinion = card.details.get("my_opinion", "") or "(мнение ещё не сформировано)"

        task = ENTITY_OPINION_PROMPT.format(
            entity_title=card.title,
            entity_type=etype,
            entity_facts=entity_facts,
            current_opinion=current_opinion,
            new_context=new_context,
        )

        try:
            response = client.chat(
                messages=[{"role": "user", "content": task}],
                system=opinion_sysp, thinking=True,
                label=f"Мнение о {card.title}",
            )
            from memory.unified import _parse_llm_json
            data = _parse_llm_json(response)
            if data is None:
                continue
            new_opinion = (data.get("opinion") or "").strip()
            if not new_opinion:
                continue
            if new_opinion == card.details.get("my_opinion"):
                continue
            if len(new_opinion) > 240:
                new_opinion = new_opinion[:240].rstrip() + "…"
            card.details["my_opinion"] = new_opinion
            card.details["_updated_at"] = time.time()
            updated += 1
            print(f"[EVO] Мнение обновлено: {priv(card.title)} → «{priv(new_opinion, 80)}»")
        except Exception as e:
            print(f"[EVO] Ошибка обновления мнения о {priv(card.title)}: {e}")

    return updated


def evolve_loop_opinions(client, persona: "CharacterContext", memory) -> int:
    from memory.loops import LOOP_STATUS_OPEN, LOOP_SUBJ_USER, LOOP_TYPE
    from memory.unified import _parse_llm_json
    from persona.character_context import resolve_honorific
    from persona.prompt_builder import build_system_prompt
    from persona.prompt_context import ContextSpec

    try:
        records = memory.records
    except AttributeError:
        return 0
    targets = [
        r for r in records
        if getattr(r, "type", "") == LOOP_TYPE and not getattr(r, "is_forgotten", False)
        and (r.details or {}).get("status", LOOP_STATUS_OPEN) == LOOP_STATUS_OPEN
        and (r.details or {}).get("subject") == LOOP_SUBJ_USER
        and not (r.details or {}).get("my_opinion")
    ]
    if not targets:
        return 0

    honorific = resolve_honorific(persona.character)
    try:
        sysp = build_system_prompt(persona, spec=ContextSpec.opinion(), memory=memory)
    except Exception as e:
        print(f"[EVO] не собрать линзу для стойки на петли: {e}")
        return 0

    updated = 0
    for loop in targets:
        d = loop.details or {}
        desc = (d.get("description") or "").strip()
        task = LOOP_OPINION_TASK.format(
            honorific=honorific, kind=d.get("kind", "цель"), title=loop.title,
            extra=(f" Детали: {desc}." if desc else ""))
        try:
            resp = client.chat(messages=[{"role": "user", "content": task}],
                               system=sysp, thinking=True, label=f"Стойка: {loop.title}")
            data = _parse_llm_json(resp)
            if not data:
                continue
            op = (data.get("opinion") or "").strip()
            if not op:
                continue
            if len(op) > 200:
                op = op[:200].rstrip() + "…"
            d["my_opinion"] = op
            d["_updated_at"] = time.time()
            updated += 1
            print(f"[EVO] Стойка на петлю: {priv(loop.title)} → «{priv(op, 70)}»")
        except Exception as e:
            print(f"[EVO] Ошибка стойки на петлю {priv(loop.title)}: {e}")
    return updated
