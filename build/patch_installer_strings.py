from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YML = (ROOT / "node_modules" / "app-builder-lib" / "templates"
       / "nsis" / "assistedMessages.yml")

REPLACEMENTS = {
    "Выбери, хочешь ли ты сделать": "Выберите, хотите ли вы сделать",
    "программ ты хочешь удалить": "программ вы хотите удалить",
    "продолжить, тебе нужно войти": "продолжить, вам нужно войти",
}


def main() -> None:
    if not YML.exists():
        print(f"[patch-strings] not found (skip): {YML}")
        return
    text = YML.read_text(encoding="utf-8")
    applied = 0
    for old, new in REPLACEMENTS.items():
        if old in text:
            text = text.replace(old, new)
            applied += 1
    YML.write_text(text, encoding="utf-8")
    print(f"[patch-strings] applied {applied}/{len(REPLACEMENTS)} replacements")


if __name__ == "__main__":
    main()
