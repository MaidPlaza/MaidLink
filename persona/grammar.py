from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.llama_client import LlamaClient

_SYSTEM_TMPL = """Ты — корректор русского текста. На вход — РЕПЛИКА персонажа из чата.
Исправь ТОЛЬКО механические ошибки русского языка:
- падежи, окончания, согласование слов;
- род глаголов и прилагательных;
- склонение числительных (в том числе годов прописью);
- опечатки и пунктуацию.

СТРОГО СОХРАНИ всё остальное: стиль и тон (разговорное остаётся разговорным),
выбор слов, порядок мыслей, длину, эмодзи, текст в *звёздочках* (действия),
обращение-титул с его ЗАГЛАВНОЙ буквы (как в оригинале; НЕ понижай регистр),
служебные частицы («и», «же», «-то», «ну»), разговорные формы
(«щас», «ага» — это голос, не ошибка) и ФОРМУ чисел: прописью оставляй прописью (НЕ
превращай «две тысячи двадцать второй» в «2022»), цифры — цифрами. НЕ делай текст
формальнее, НЕ переписывай, НЕ сокращай. Если ошибок нет — верни реплику дословно.

Род участников:
- сам персонаж — {self_gender} (о себе: {self_forms});
- собеседник — {user_gender} (о нём: {user_forms}).
Род третьих лиц: если местоимение или глагол относится к упомянутому в диалоге-
контексте человеку, согласуй род С НИМ: «сестра / подруга / мама» → она (пришла,
устала); «брат / друг / папа» → он (пришёл, устал).

Обращение к собеседнику: персонаж зовёт его ТОЛЬКО «{honorific}». Если в реплике
стоит ДРУГОЙ титул-обращение к собеседнику (напр. «Господин» вместо «{honorific}»
или наоборот) — ЗАМЕНИ на «{honorific}» в правильном падеже. Это единственная
правка обращения; имя собеседника, если он назван ПО ИМЕНИ, НЕ трогай.

ВАЖНО: проверь род у КАЖДОГО глагола и прилагательного О СЕБЕ по ВСЕЙ реплике — в
длинных репликах ошибку легко пропустить (напр. «я приготовила… и испёк» → «испекла»;
«я заварил» → «заварила»; «я уверен» → «уверена»).

Ответ — ТОЛЬКО исправленный текст реплики на русском, без кавычек, без пояснений,
без префиксов."""


def _gender_words(g: str) -> tuple[str, str]:
    if g == "female":
        return "женщина", "сказала, подумала, была"
    return "мужчина", "сказал, подумал, был"


def build_grammar_system(character, honorific: str = "Господин") -> str:
    sg, sf = _gender_words(getattr(character, "gender", "female"))
    ug_raw = getattr(character, "user_gender", "male")
    ug, uf = _gender_words("female" if ug_raw == "female" else "male")
    return _SYSTEM_TMPL.format(self_gender=sg, self_forms=sf, user_gender=ug,
                               user_forms=uf, honorific=(honorific or "Господин"))


def _format_dialogue(dialogue, honorific: str, char_name: str) -> str:
    if not dialogue:
        return ""
    lines = []
    for m in dialogue[-4:]:
        from memory.unified import _flatten_dialogue_content
        txt = _flatten_dialogue_content(m.get("content") or "").strip()
        if not txt:
            continue
        who = honorific if m.get("role") == "user" else char_name
        lines.append(f"{who}: {txt}")
    return "\n".join(lines)


def _clean_output(s: str) -> str:
    s = (s or "").strip()
    for d in ("<<<", ">>>"):
        s = s.replace(d, "")
    s = s.strip()
    if len(s) >= 2 and s[0] in "«\"'" and s[-1] in "»\"'":
        s = s[1:-1].strip()
    return s


def correct_grammar(
    client: "LlamaClient",
    text: str,
    *,
    character,
    dialogue=None,
    honorific: str = "Господин",
    thinking: bool = False,
) -> str:
    text = (text or "").strip()
    if not text:
        return text

    system = build_grammar_system(character, honorific)
    ctx = _format_dialogue(dialogue, honorific, getattr(character, "name", "персонаж"))
    user = (
        (f"<контекст_диалога>\n{ctx}\n</контекст_диалога>\n\n" if ctx else "")
        + f"Исправь грамматику в этой реплике:\n<<<\n{text}\n>>>"
    )

    try:
        out = client.complete(
            [{"role": "user", "content": user}],
            system=system,
            thinking=thinking,
            temperature=0.3,
            label="grammar polish",
        )
    except Exception as e:
        print(f"[grammar] correction failed: {e}")
        return text

    out = _clean_output(out)
    if not out:
        return text
    if len(out) < len(text) * 0.5 or len(out) > len(text) * 2.0:
        print(f"[grammar] length off ({len(text)}→{len(out)}), keeping original")
        return text
    return out
