from __future__ import annotations

import random
import time
from datetime import date, datetime

from services import self_styling as ss

TICKET_RATE = 3
DAILY_TICKETS = 1 * TICKET_RATE
TICKET_CAP = 7 * TICKET_RATE

SPHERE_EVERY = 25

RARITY_WEIGHTS = {"common": 70, "rare": 25, "legendary": 5}
RARITY_RU = {"common": "обычная", "rare": "редкая", "legendary": "легендарная"}
RARITY_ORDER = ("common", "rare", "legendary")

RARE_PITY = 10
LEGENDARY_PITY = 50

HAIR_SLOTS = frozenset({"hair_style", "hair_texture", "hair_bangs", "hair_extra"})

SPHERE_TAG = "change sphere"
SPHERE_LABEL = "сфера изменения"
SPHERE_SHARE = 0.15

CATEGORY_RU = {
    "hair_style": "укладка", "hair_texture": "текстура волос",
    "hair_bangs": "чёлка", "hair_extra": "элемент причёски",
    "makeup": "макияж", "accessory": "украшение",
    "underwear": "бельё", "intimate": "интимное украшение",
}
NSFW_SLOTS = frozenset({"underwear", "intimate"})

LEGENDARY = frozenset({
    "crown", "mini crown", "tiara", "halo", "head wreath", "veil",
    "face jewel", "heart hair bun", "heart ahoge",
    "pearl thong", "nipple chain",
    "latex set", "fur set", "o-ring set",
    "wedding ring", "laurel crown", "diadem", "masquerade mask", "fox mask",
    "head chain", "jewel butt plug", "chastity belt",
})
RARE = frozenset({
    "crown braid", "braided bun", "donut hair bun", "cone hair bun",
    "folded ponytail", "rope braid", "french braid", "braided ponytail",
    "half up braid", "hair rings", "split ponytail", "uneven twintails",
    "drill hair", "twin drills", "ringlets", "drill sidelocks",
    "antenna hair", "hair flaps", "low-tied sidelocks", "crossed bangs",
    "bangs pinned back",
    "facepaint", "glitter makeup",
    "pearl necklace", "cross necklace", "bead necklace", "neck bell",
    "hair bell", "hair flower", "hair ornament", "hair tubes",
    "crescent earrings", "hoop earrings", "single earring", "ear piercing",
    "monocle", "eyepatch", "mask", "sunglasses", "semi-rimless eyewear",
    "wristwatch", "brooch", "bangle", "anklet", "armband", "ribbon choker",
    "scarf",
    "nipple piercing", "navel piercing", "collar",
    "babydoll", "negligee", "garter belt", "garter straps", "camisole",
    "front-tie bra", "frontless bra", "multi-strapped bra", "shelf bra",
    "backless panties", "side-tie panties",
    "lace set", "satin set", "see-through set", "lace-trimmed set",
    "ribbon-trimmed set", "embroidered set", "micro set", "string set",
    "open set",
    "circlet", "kanzashi", "forehead jewel", "bindi", "fascinator", "hair stick",
    "fake animal ears", "fake tail", "tail bell", "tail ornament", "goggles",
    "pince-nez", "oni mask", "domino mask", "half mask", "aviator sunglasses",
    "armlet", "thighlet", "belly chain", "harness", "chest harness", "locket",
    "dog tags", "neck ring", "earclip", "industrial piercing",
    "spiked ear piercing", "ear chain", "animal ear piercing", "ear ornament",
    "horn ornament", "tongue piercing", "eyebrow piercing", "nose piercing",
    "lip piercing", "nose ring", "labret piercing", "bridge piercing",
    "chin piercing", "cheek piercing", "labia piercing", "spiked collar",
    "metal collar", "belt collar",
    "studded collar", "heart collar", "wrist flower", "hand jewel", "corsage",
    "magatama necklace", "magatama earrings", "crystal earrings",
    "planet earrings", "pentacle", "nail art",
    "bodystocking", "bustier", "chemise", "fundoshi", "maebari", "g-string",
    "heart pasties", "cross pasties", "nipple rings", "nipple bar",
    "nipple jewelry", "pussy piercing", "clitoris ring", "animal collar",
    "padlocked collar", "leash", "shibari", "crotch rope", "shackles",
    "remote control vibrator", "egg vibrator", "vibrator under clothes",
    "vibrator under panties", "butt plug", "anal tail", "nipple clamps",
    "cock ring",
})

LABELS_RU: dict[str, str] = {
    "ponytail": "хвост", "high ponytail": "высокий хвост",
    "low ponytail": "низкий хвост", "side ponytail": "хвост набок",
    "short ponytail": "короткий хвостик",
    "folded ponytail": "подогнутый хвост",
    "front ponytail": "хвост, переброшенный вперёд",
    "split ponytail": "раздвоенный хвост", "twintails": "два хвостика",
    "low twintails": "низкие хвостики", "short twintails": "короткие хвостики",
    "uneven twintails": "неровные хвостики",
    "one side up": "прядь, собранная с одной стороны",
    "two side up": "две собранные пряди по бокам",
    "half updo": "полусобранные волосы", "topknot": "пучок на макушке",
    "braid": "коса", "single braid": "одна коса", "twin braids": "две косы",
    "low twin braids": "две низкие косы", "side braid": "коса набок",
    "front braid": "коса спереди", "crown braid": "коса-корона",
    "braided ponytail": "хвост-коса", "half up braid": "полусобранная коса",
    "braided bun": "пучок из косы", "french braid": "французская коса",
    "rope braid": "коса-жгут", "hair bun": "пучок",
    "single hair bun": "одиночный пучок", "double bun": "два пучка",
    "cone hair bun": "пучок-конус", "donut hair bun": "пучок-бублик",
    "heart hair bun": "пучок-сердечко", "hair rings": "кольца в волосах",
    "hair down": "распущенные волосы", "hair up": "собранные волосы",
    "hair pulled back": "волосы, зачёсанные назад",
    "hair slicked back": "гладко зачёсанные назад",
    "straight hair": "прямые волосы", "wavy hair": "волнистые волосы",
    "curly hair": "кудри", "fluffy hair": "пушистые волосы",
    "messy hair": "растрёпанные волосы", "ringlets": "локоны-колечки",
    "flipped hair": "подкрученные кончики", "drill hair": "волосы-спиральки",
    "twin drills": "две спирали", "spiked hair": "торчащие пряди",
    "pointy hair": "острые пряди",
    "blunt bangs": "ровная чёлка", "parted bangs": "чёлка на пробор",
    "swept bangs": "чёлка набок", "crossed bangs": "скрещённая чёлка",
    "arched bangs": "чёлка аркой", "asymmetrical bangs": "асимметричная чёлка",
    "bangs pinned back": "заколотая чёлка", "wispy bangs": "лёгкая чёлка",
    "choppy bangs": "рваная чёлка", "short bangs": "короткая чёлка",
    "long bangs": "длинная чёлка", "hair between eyes": "прядь между глаз",
    "hair over one eye": "прядь на один глаз",
    "curtained hair": "чёлка-шторка", "middle part": "прямой пробор",
    "sidelocks": "боковые пряди", "long sidelocks": "длинные боковые пряди",
    "low-tied sidelocks": "подвязанные боковые пряди",
    "drill sidelocks": "боковые спиральки", "hair intakes": "заломы у висков",
    "single hair intake": "залом у виска", "ahoge": "ахоге",
    "heart ahoge": "ахоге-сердечко", "antenna hair": "прядь-антенна",
    "hair flaps": "пряди-крылышки", "hair over shoulder": "волосы через плечо",
    "blunt ends": "ровные кончики",
    "lipstick": "помада", "lipgloss": "блеск для губ", "eyeshadow": "тени",
    "eyeliner": "подводка", "mascara": "тушь", "nail polish": "лак для ногтей",
    "facepaint": "роспись на лице", "face jewel": "стразы на лице",
    "glitter makeup": "блёстки",
    "earrings": "серьги", "hoop earrings": "серьги-кольца",
    "stud earrings": "серьги-гвоздики", "single earring": "одна серьга",
    "crescent earrings": "серьги-полумесяцы", "ear piercing": "пирсинг уха",
    "necklace": "ожерелье", "pendant": "кулон", "choker": "чокер",
    "ribbon choker": "чокер-лента", "neck ribbon": "лента на шее",
    "pearl necklace": "жемчужное ожерелье", "bead necklace": "бусы",
    "cross necklace": "крестик на цепочке", "neck bell": "бубенчик на шее",
    "scarf": "шарф",
    "hair ribbon": "лента в волосах", "hair bow": "бант в волосах",
    "hairclip": "заколка", "hairpin": "шпилька",
    "hair ornament": "украшение для волос", "hair flower": "цветок в волосах",
    "hairband": "повязка для волос", "headband": "ободок",
    "hair scrunchie": "резинка-скранчи", "hair bell": "колокольчик в волосах",
    "hair tubes": "трубочки на прядях",
    "tiara": "тиара", "mini crown": "мини-корона", "crown": "корона",
    "head wreath": "венок", "veil": "вуаль", "halo": "нимб",
    "glasses": "очки", "semi-rimless eyewear": "очки в полуоправе",
    "sunglasses": "солнечные очки", "monocle": "монокль",
    "eyepatch": "повязка на глаз", "mask": "маска",
    "bracelet": "браслет", "bangle": "браслет-обруч",
    "wristband": "напульсник", "wristwatch": "наручные часы", "ring": "кольцо",
    "anklet": "браслет на щиколотке", "brooch": "брошь",
    "armband": "повязка на руке",
    "nipple piercing": "пирсинг сосков", "navel piercing": "пирсинг пупка",
    "collar": "ошейник", "nipple chain": "цепочка на сосках",
    "bra": "лиф", "panties": "трусики", "thong": "стринги",
    "lingerie": "комплект белья", "babydoll": "бэбидолл",
    "camisole": "камисоль", "negligee": "неглиже",
    "garter belt": "пояс для чулок", "garter straps": "подвязки",
    "lace set": "кружевной комплект", "satin set": "атласный комплект",
    "latex set": "латексный комплект", "fur set": "меховой комплект",
    "see-through set": "прозрачный комплект", "bow set": "комплект с бантиками",
    "frilled set": "комплект с рюшами",
    "lace-trimmed set": "комплект с кружевной каймой",
    "ribbon-trimmed set": "комплект с лентами", "o-ring set": "комплект с кольцами",
    "embroidered set": "комплект с вышивкой", "micro set": "микро-комплект",
    "string set": "комплект на тесёмках", "sports set": "спортивный комплект",
    "open set": "открытый комплект", "basic set": "простой комплект",
    "strapless bra": "лиф без бретелек",
    "front-tie bra": "лиф на завязках спереди",
    "frontless bra": "лиф с открытым фронтом",
    "multi-strapped bra": "лиф с ремешками", "shelf bra": "лиф-полочка",
    "front-hook bra": "лиф с застёжкой спереди",
    "thong panties": "трусики-стринги",
    "highleg panties": "трусики с высоким вырезом",
    "lowleg panties": "трусики с низким вырезом",
    "high-waist panties": "трусики с высокой талией",
    "side-tie panties": "трусики на завязках",
    "backless panties": "трусики с открытой спинкой",
    "pearl thong": "жемчужные стринги",
    "toenail polish": "лак на ногтях ног", "nail art": "роспись ногтей",
    "earclip": "клипсы", "tassel earrings": "серьги с кисточками",
    "teardrop earrings": "серьги-капли", "star earrings": "серьги-звёздочки",
    "heart earrings": "серьги-сердечки", "cross earrings": "серьги-крестики",
    "sphere earrings": "серьги-шарики", "flower earrings": "серьги-цветы",
    "triangle earrings": "серьги-треугольники", "pearl earrings": "жемчужные серьги",
    "feather earrings": "серьги-пёрышки", "bow earrings": "серьги-бантики",
    "skull earrings": "серьги-черепа", "crystal earrings": "серьги-кристаллы",
    "magatama earrings": "серьги-магатамы", "pom pom earrings": "серьги-помпоны",
    "butterfly earrings": "серьги-бабочки", "leaf earrings": "серьги-листики",
    "bell earrings": "серьги-колокольчики", "cherry earrings": "серьги-вишенки",
    "planet earrings": "серьги-планеты", "snowflake earrings": "серьги-снежинки",
    "dangle earrings": "висячие серьги", "diamond-shaped earrings": "серьги-ромбы",
    "industrial piercing": "индастриал", "spiked ear piercing": "шипы в ушах",
    "ear chain": "цепочка в ухе", "ear ornament": "украшение на ушко",
    "animal ear piercing": "пирсинг звериного ушка",
    "frilled choker": "чокер с рюшами", "o-ring choker": "чокер с кольцом",
    "pendant choker": "чокер с подвеской", "chain necklace": "цепочка",
    "heart necklace": "кулон-сердечко", "star necklace": "кулон-звезда",
    "magatama necklace": "ожерелье с магатамой", "key necklace": "кулон-ключик",
    "tooth necklace": "ожерелье из клыков", "flower necklace": "цветочное ожерелье",
    "shell necklace": "ожерелье из ракушек", "crescent necklace": "кулон-полумесяц",
    "pentacle": "пентакль", "skull necklace": "кулон-череп",
    "ring necklace": "кольцо на цепочке", "feather necklace": "кулон-пёрышко",
    "locket": "медальон", "dog tags": "жетоны", "neck ring": "обруч на шее",
    "neck tassel": "кисточка на шее", "lei": "гавайские бусы",
    "bandana around neck": "бандана на шее", "belt collar": "ошейник-ремешок",
    "spiked collar": "ошейник с шипами", "metal collar": "металлический ошейник",
    "heart collar": "ошейник с сердечком", "studded collar": "ошейник с заклёпками",
    "tress ribbon": "лента, обвивающая прядь", "x hair ornament": "заколка-крестик",
    "star hair ornament": "заколка-звёздочка", "heart hair ornament": "заколка-сердечко",
    "butterfly hair ornament": "заколка-бабочка", "feather hair ornament": "перо в волосах",
    "rabbit hair ornament": "заколка-зайчик", "leaf hair ornament": "заколка-листик",
    "cross hair ornament": "заколка-крест", "crescent hair ornament": "заколка-полумесяц",
    "skull hair ornament": "заколка-череп", "pom pom hair ornament": "помпон в волосах",
    "cat hair ornament": "заколка-котик", "musical note hair ornament": "заколка-нотка",
    "bone hair ornament": "заколка-косточка", "clover hair ornament": "заколка-клевер",
    "bat hair ornament": "заколка-летучая мышь", "fish hair ornament": "заколка-рыбка",
    "snowflake hair ornament": "заколка-снежинка", "bow hairband": "ободок с бантом",
    "frilled hairband": "ободок с рюшами", "lolita hairband": "лолита-ободок",
    "flower hairband": "ободок с цветами", "hair tie": "резинка для волос",
    "hair bobbles": "резинки-шарики", "hair beads": "бусины в волосах",
    "hair stick": "шпилька-палочка", "kanzashi": "канзаши",
    "circlet": "венец", "diadem": "диадема", "laurel crown": "лавровый венок",
    "head chain": "цепочка на голове", "forehead jewel": "украшение на лбу",
    "bindi": "бинди", "fascinator": "шляпка-вуалетка",
    "fake animal ears": "ободок с ушками", "horn ornament": "украшение на рожки",
    "hachimaki": "повязка хатимаки", "sweatband": "спортивная повязка",
    "round eyewear": "круглые очки", "under-rim eyewear": "очки с нижней оправой",
    "rimless eyewear": "очки без оправы", "rectangular eyewear": "прямоугольные очки",
    "over-rim eyewear": "очки с верхней оправой", "heart-shaped eyewear": "очки-сердечки",
    "star-shaped eyewear": "очки-звёздочки", "triangular eyewear": "треугольные очки",
    "aviator sunglasses": "очки-авиаторы", "pince-nez": "пенсне", "goggles": "гогглы",
    "medical eyepatch": "медицинская повязка на глаз", "mouth mask": "маска на рот",
    "surgical mask": "медицинская маска", "fox mask": "маска лисы",
    "oni mask": "маска они", "domino mask": "маска-домино", "half mask": "полумаска",
    "masquerade mask": "маскарадная маска", "sticker on face": "наклейка на лице",
    "bandaid on face": "пластырь на лице", "bandaid on nose": "пластырь на носу",
    "bandaid on cheek": "пластырь на щеке",
    "tongue piercing": "пирсинг языка", "eyebrow piercing": "пирсинг брови",
    "nose piercing": "пирсинг носа", "lip piercing": "пирсинг губы",
    "nose ring": "кольцо в носу", "labret piercing": "лабрет",
    "bridge piercing": "пирсинг переносицы", "chin piercing": "пирсинг подбородка",
    "cheek piercing": "пирсинг щеки", "labia piercing": "пирсинг половых губ",
    "bead bracelet": "браслет из бусин", "spiked bracelet": "браслет с шипами",
    "studded bracelet": "браслет с заклёпками", "pearl bracelet": "жемчужный браслет",
    "flower bracelet": "цветочный браслет", "chain bracelet": "браслет-цепочка",
    "wrist cuffs": "манжеты", "wrist scrunchie": "резинка на запястье",
    "wrist ribbon": "лента на запястье", "wrist flower": "цветок на запястье",
    "armlet": "браслет на плечо", "arm ribbon": "лента на руке",
    "arm garter": "подвязка на руке", "thumb ring": "кольцо на большом пальце",
    "wedding ring": "обручальное кольцо", "hand jewel": "украшение на кисть",
    "thigh strap": "ремешок на бедре", "thighlet": "украшение на бедре",
    "leg ribbon": "лента на ноге", "thigh ribbon": "лента на бедре",
    "legwear garter": "подвязка на чулке", "leg belt": "ремень на ноге",
    "ankle garter": "подвязка на щиколотке",
    "corsage": "цветок-корсаж", "belly chain": "цепочка на талии",
    "harness": "портупея", "chest harness": "портупея на груди",
    "tail ornament": "украшение на хвост", "tail bow": "бант на хвосте",
    "tail ribbon": "лента на хвосте", "tail bell": "колокольчик на хвосте",
    "fake tail": "накладной хвост",
    "bodystocking": "боди-чулок", "bustier": "бюстье", "chemise": "сорочка",
    "boyshort panties": "трусики-шортики", "g-string": "стринги-ниточка",
    "strapless bottom": "трусики без завязок", "fundoshi": "фундоси",
    "pasties": "наклейки на соски", "heart pasties": "наклейки-сердечки",
    "cross pasties": "наклейки-крестики", "tape on nipples": "пластырь на сосках",
    "maebari": "маэбари",
    "nipple rings": "кольца в сосках", "nipple bar": "штанга в сосках",
    "nipple jewelry": "украшения на сосках", "pussy piercing": "интимный пирсинг",
    "clitoris ring": "кольцо в клиторе", "animal collar": "ошейник питомца",
    "padlocked collar": "ошейник с замком", "leash": "поводок", "cuffs": "наручи",
    "handcuffs": "наручники", "shackles": "кандалы", "shibari": "шибари",
    "crotch rope": "верёвка между ног", "chastity belt": "пояс верности",
    "nipple clamps": "зажимы на сосках", "remote control vibrator": "вибратор с пультом",
    "egg vibrator": "вибро-яйцо", "vibrator under clothes": "вибратор под одеждой",
    "vibrator under panties": "вибратор под бельём", "butt plug": "анальная пробка",
    "jewel butt plug": "пробка с камнем", "anal tail": "хвост-пробка",
    "cock ring": "эрекционное кольцо",
}


class GachaError(Exception):
    pass


class NoTickets(GachaError):
    pass


class PoolEmpty(GachaError):
    pass


def rarity_of(tag: str) -> str:
    t = (tag or "").strip().lower()
    if t in LEGENDARY:
        return "legendary"
    if t in RARE or t == SPHERE_TAG:
        return "rare"
    if t in ss.ALWAYS_OPEN:
        return "common"
    if ss.route_tag(t) in HAIR_SLOTS:
        return "rare"
    return "common"


def label_of(tag: str) -> str:
    t = (tag or "").strip().lower()
    if t == SPHERE_TAG:
        return SPHERE_LABEL
    return LABELS_RU.get(t, tag)


def universe(*, allow_nsfw: bool = False, cur_len: str = "",
             body: dict | None = None) -> list[dict]:
    c = ss._canon()
    items: list[dict] = []

    def put(tag: str, slot: str) -> None:
        if not ss.fits_body(tag, body):
            return
        group = slot
        if slot == "accessory":
            group = f"accessory:{ss.wearable_section(tag)}"
        items.append({"tag": tag, "slot": slot, "group": group,
                      "rarity": rarity_of(tag)})

    for tag, need in c["styles"].items():
        if ss._length_ok(cur_len, need):
            put(tag, "hair_style")
    for tag in c["textures"]:
        put(tag, "hair_texture")
    for tag in c["bangs"]:
        put(tag, "hair_bangs")
    for tag in c["extras"]:
        put(tag, "hair_extra")
    for tag in c["makeup"]:
        put(tag, "makeup")
    for tags in c["wearables"].values():
        for tag in tags:
            put(tag, "accessory")
    if allow_nsfw:
        for tags in c["underwear"].values():
            for tag in tags:
                if tag in ss.UNDERWEAR_IMPLICIT:
                    continue
                put(tag, "underwear")
        for tags in c["wearables_nsfw"].values():
            for tag in tags:
                put(tag, "intimate")
    return items


def _day(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).date().isoformat()


def _days_between(a: str, b: str) -> int:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days
    except Exception:
        return 0


def has_gacha(identity) -> bool:
    return identity is not None and hasattr(identity, "gacha")


def _state_tags(state: dict) -> list[str]:
    tags = list(ss.hair_tags(state))
    for key in ("accessories", "makeup", "underwear", "intimate"):
        tags += list(state.get(key) or [])
    return tags


def _cores_of_state(state: dict) -> set[str]:
    out = {ss.allowance_key(t) for t in _state_tags(state)}
    return {t for t in out if t}


def _add_color(colors: dict, item: str, color: str) -> bool:
    if not item or not color or color not in ss.palette(item):
        return False
    lst = colors.setdefault(item, [])
    if color in lst:
        return False
    lst.append(color)
    return True


def _worn_colors(tags) -> dict[str, list[str]]:
    colors: dict[str, list[str]] = {}
    for t in tags:
        k = ss.allowance_key(t)
        if not ss.is_colorable(k) or k in ss.UNDERWEAR_IMPLICIT:
            continue
        c = ss.tag_color(t)
        _add_color(colors, k, c if c in ss.palette(k) else ss.fallback_color(k))
    return colors


def _colorize_worn(identity) -> bool:
    allowed = allowed_cores(identity)
    if allowed is None:
        return False

    def fix(t: str) -> str:
        k = ss.allowance_key(t)
        if ss.tag_color(t) is not None or not ss.is_colorable(k) \
                or k in ss.UNDERWEAR_IMPLICIT:
            return t
        c = ss.pick_color(allowed, k)
        return f"{c} {t}" if c else t

    return ss.rewrite_slot_tags(identity, fix)


def ensure_state(identity, now: float | None = None) -> bool:
    if not has_gacha(identity):
        return False
    st = identity.gacha
    if isinstance(st, dict) and st.get("last_daily"):
        return False
    state = ss.styling_state(identity)
    worn = _cores_of_state(state)
    defaults = defaults_cores(identity)
    identity.gacha = {
        "tickets": DAILY_TICKETS,
        "last_daily": _day(now),
        "unlocked": sorted(worn - defaults - ss.UNDERWEAR_IMPLICIT),
        "colors": _worn_colors(_state_tags(state)),
        "colors_v1": True,
        "pulls": [],
        "granted": {},
    }
    _colorize_worn(identity)
    return True


def accrue(identity, now: float | None = None) -> int:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return 0
    st = identity.gacha
    today = _day(now)
    days = _days_between(str(st.get("last_daily")), today)
    if days <= 0:
        return 0
    before = int(st.get("tickets", 0) or 0)
    st["tickets"] = max(before, min(TICKET_CAP, before + days * DAILY_TICKETS))
    st["last_daily"] = today
    return st["tickets"] - before


def touch(identity, now: float | None = None) -> bool:
    created = ensure_state(identity, now)
    added = accrue(identity, now)
    migrated = _refund_implicit(identity)
    migrated = _refund_base(identity) or migrated
    migrated = _refund_always_open(identity) or migrated
    migrated = _refund_unfit(identity) or migrated
    migrated = _migrate_colors(identity) or migrated
    migrated = _migrate_uw_sets(identity) or migrated
    return created or added > 0 or migrated


def _migrate_uw_sets(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    st = identity.gacha
    if st.get("uw_sets_v1"):
        return False
    st["uw_sets_v1"] = True
    alias = ss.LEGACY_UW_ALIAS
    cuts = set(ss.UW_BRA_CUTS) | set(ss.UW_PANTIES_CUTS)

    def new_key(tag: str) -> str:
        tag = alias.get(tag, tag)
        return ss.LEGACY_UW_TO_SET.get(tag, tag)

    colors = {k: list(v) for k, v in (st.get("colors") or {}).items()}
    patterns = {k: list(v) for k, v in (st.get("patterns") or {}).items()}
    unlocked: list[str] = []
    touched: set[str] = set()
    for k in st.get("unlocked") or []:
        k2 = alias.get(k, k)
        if k2 in ss.UW_REMOVED:
            colors.pop(k, None)
            patterns.pop(k, None)
            continue
        nk = new_key(k)
        if k2 in ss.LEGACY_UW_TO_SET:
            for c in colors.pop(k, []):
                _add_color(colors, nk, c)
            for p in patterns.pop(k, []):
                _add_pattern(patterns, nk, p)
            touched.add(nk)
        elif nk in cuts:
            colors.pop(k, None)
            patterns.pop(k, None)
            touched.add(nk)
        if nk not in unlocked:
            unlocked.append(nk)
    for k in touched:
        if k not in cuts and not colors.get(k):
            _add_color(colors, k, ss.fallback_color(k))
    budget = {k: (1 if k in cuts else
                  max(1, len(colors.get(k, [])) + len(patterns.get(k, []))))
              for k in touched}
    seen: dict[str, int] = {}
    pulls, refund = [], 0
    for p in st.get("pulls") or []:
        tag = alias.get(str(p.get("tag") or ""), str(p.get("tag") or ""))
        if tag in ss.UW_REMOVED:
            refund += 1
            continue
        nk = new_key(tag)
        if nk in budget:
            seen[nk] = seen.get(nk, 0) + 1
            if seen[nk] > budget[nk]:
                refund += 1
                continue
            p = {**p, "tag": nk}
            if p.get("pattern") and p["pattern"] not in ss.patterns_of(nk):
                p.pop("pattern")
        pulls.append(p)
    gone = ss.UW_REMOVED | cuts
    spheres_back = sum(1 for u in (st.get("sphere_uses") or [])
                       if alias.get(str(u.get("tag") or ""), str(u.get("tag") or "")) in gone)
    st["unlocked"], st["colors"], st["patterns"], st["pulls"] = unlocked, colors, patterns, pulls
    if refund:
        st["tickets"] = int(st.get("tickets", 0) or 0) + refund
    if spheres_back:
        st["spheres"] = spheres(identity) + spheres_back
    styling = getattr(identity, "self_styling", None)
    if isinstance(styling, dict):
        for holder in (styling, styling.get("defaults")):
            if isinstance(holder, dict) and holder.get("underwear"):
                uw, moved = ss.migrate_underwear_tags(holder.get("underwear"))
                holder["underwear"] = uw
                holder["intimate"] = list(holder.get("intimate") or []) + [
                    t for t in moved if t not in (holder.get("intimate") or [])]
    print(f"[gacha] бельё — комплектами: открыто {len(unlocked)}, "
          f"+{refund} билет(ов), +{spheres_back} сфер(ы)")
    return True


def _migrate_colors(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    st = identity.gacha
    if st.get("colors_v1"):
        return False
    st["colors_v1"] = True
    colors = {k: list(v) for k, v in (st.get("colors") or {}).items()}
    for k in st.get("unlocked") or []:
        if (ss.is_colorable(k) and k not in ss.UNDERWEAR_IMPLICIT
                and not colors.get(k)):
            _add_color(colors, k, ss.fallback_color(k))
    worn = _state_tags(ss.styling_state(identity))
    for k, cols in _worn_colors([t for t in worn if ss.tag_color(t)]).items():
        for c in cols:
            _add_color(colors, k, c)
    st["colors"] = colors
    _colorize_worn(identity)
    return True


def _refund_implicit(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    st = identity.gacha
    if st.get("implicit_refunded"):
        return False
    st["implicit_refunded"] = True
    pulls = list(st.get("pulls") or [])
    bad = [p for p in pulls if str(p.get("tag") or "") in ss.UNDERWEAR_IMPLICIT]
    if bad:
        st["pulls"] = [p for p in pulls if p not in bad]
        st["unlocked"] = [t for t in (st.get("unlocked") or [])
                          if t not in ss.UNDERWEAR_IMPLICIT]
        st["tickets"] = int(st.get("tickets", 0) or 0) + len(bad)
        print(f"[gacha] неявное бельё вычеркнуто из открытого: "
              f"{[p['tag'] for p in bad]} → +{len(bad)} билет(ов)")
    return True


def _refund_base(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    styling = getattr(identity, "self_styling", None) or {}
    if "base" not in styling:
        return False
    st = identity.gacha
    if st.get("base_refunded"):
        return False
    st["base_refunded"] = True
    base = {ss.allowance_key(t) for t in ss.base_appearance_tags(identity)}
    pulls = list(st.get("pulls") or [])
    bad = [p for p in pulls if not p.get("color")
           and ss.allowance_key(str(p.get("tag") or "")) in base]
    if bad:
        st["pulls"] = [p for p in pulls if p not in bad]
        st["unlocked"] = [t for t in (st.get("unlocked") or [])
                          if ss.allowance_key(t) not in base]
        st["tickets"] = int(st.get("tickets", 0) or 0) + len(bad)
        print(f"[gacha] базовая внешность вычеркнута из выпавшего: "
              f"{[p['tag'] for p in bad]} → +{len(bad)} билет(ов)")
    return True


def _refund_always_open(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    st = identity.gacha
    if st.get("always_open_refunded"):
        return False
    st["always_open_refunded"] = True
    pulls = list(st.get("pulls") or [])
    bad = [p for p in pulls if str(p.get("tag") or "") in ss.ALWAYS_OPEN]
    st["unlocked"] = [t for t in (st.get("unlocked") or []) if t not in ss.ALWAYS_OPEN]
    if bad:
        st["pulls"] = [p for p in pulls if p not in bad]
        st["tickets"] = int(st.get("tickets", 0) or 0) + len(bad)
        print(f"[gacha] открытое всем вычеркнуто из выпавшего: "
              f"{[p['tag'] for p in bad]} → +{len(bad)} билет(ов)")
    return True


def _refund_unfit(identity) -> bool:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return False
    body = ss.body_of(identity)
    if not body:
        return False
    st = identity.gacha
    unfit = {t for t in (st.get("unlocked") or []) if not ss.fits_body(t, body)}
    if not unfit:
        return False
    pulls = list(st.get("pulls") or [])
    bad = [p for p in pulls if str(p.get("tag") or "") in unfit]
    st["unlocked"] = [t for t in (st.get("unlocked") or []) if t not in unfit]
    for key in ("colors", "patterns"):
        for t in unfit:
            (st.get(key) or {}).pop(t, None)
    if bad:
        st["pulls"] = [p for p in pulls if p not in bad]
        st["tickets"] = int(st.get("tickets", 0) or 0) + len(bad)
    print(f"[gacha] не по телу вычеркнуто из выпавшего: {sorted(unfit)} → "
          f"+{len(bad)} билет(ов)")
    return True


def grant(identity, n: int, reason: str = "") -> int:
    if not has_gacha(identity):
        return 0
    ensure_state(identity)
    st = identity.gacha
    st["tickets"] = int(st.get("tickets", 0) or 0) + max(0, int(n))
    if reason:
        g = st.setdefault("granted", {})
        g[reason] = int(g.get(reason, 0) or 0) + max(0, int(n))
    return st["tickets"]


def tickets(identity) -> int:
    if not has_gacha(identity):
        return 0
    return int((identity.gacha or {}).get("tickets", 0) or 0)


def earned_count(identity) -> int:
    if not has_gacha(identity) or not isinstance(identity.gacha, dict):
        return 0
    return len([t for t in (identity.gacha.get("unlocked") or [])
                if t and t not in ss.UNDERWEAR_IMPLICIT])


def design_cores(identity) -> set[str]:
    try:
        cores = _cores_of_state(ss.default_state(identity))
        cores |= {ss.allowance_key(t) for t in ss.base_appearance_tags(identity)}
        cores |= set(ss.ALWAYS_OPEN)
        return {c for c in cores if c}
    except Exception:
        return set(ss.ALWAYS_OPEN)


def innate_cores(identity) -> set[str]:
    try:
        return {c for c in (ss.allowance_key(t) for t in ss.innate_tags(identity)) if c}
    except Exception:
        return set()


def defaults_cores(identity) -> set[str]:
    return design_cores(identity) | innate_cores(identity)


def design_colors(identity) -> dict[str, list[str]]:
    colors: dict[str, list[str]] = {}
    try:
        tags = _state_tags(ss.default_state(identity)) + ss.base_appearance_tags(identity)
    except Exception:
        return colors
    for t in tags:
        c = ss.tag_color(t)
        if c:
            _add_color(colors, ss.allowance_key(t), c)
    return colors


def color_map(identity) -> dict[str, list[str]]:
    colors = design_colors(identity)
    for k in innate_cores(identity):
        for c in ss.palette(k):
            _add_color(colors, k, c)
    st = identity.gacha if has_gacha(identity) and isinstance(identity.gacha, dict) else {}
    for k, cols in (st.get("colors") or {}).items():
        for c in cols or []:
            _add_color(colors, k, c)
    return colors


def open_colors(identity, item: str) -> list[str]:
    return list(color_map(identity).get(item, []))


def _add_pattern(patterns: dict, item: str, pattern: str) -> bool:
    if not item or not pattern or pattern not in ss.patterns_of(item):
        return False
    lst = patterns.setdefault(item, [])
    if pattern in lst:
        return False
    lst.append(pattern)
    return True


def pattern_map(identity) -> dict[str, list[str]]:
    patterns: dict[str, list[str]] = {}
    try:
        for t in _state_tags(ss.default_state(identity)):
            p = ss.tag_pattern(t)
            if p:
                _add_pattern(patterns, ss.allowance_key(t), p)
    except Exception:
        pass
    st = identity.gacha if has_gacha(identity) and isinstance(identity.gacha, dict) else {}
    for k, pats in (st.get("patterns") or {}).items():
        for p in pats or []:
            _add_pattern(patterns, k, p)
    return patterns


def open_patterns(identity, item: str) -> list[str]:
    return list(pattern_map(identity).get(item, []))


def allowed_cores(identity) -> "ss.Allowance | None":
    if not has_gacha(identity):
        return None
    ensure_state(identity)
    unlocked = set(identity.gacha.get("unlocked") or [])
    return ss.Allowance(defaults_cores(identity) | unlocked | ss.UNDERWEAR_IMPLICIT,
                        color_map(identity), pattern_map(identity),
                        ss.body_of(identity))


def unlock(identity, tag: str, color: str | None = None,
           pattern: str | None = None) -> bool:
    if not has_gacha(identity):
        return False
    ensure_state(identity)
    t = (tag or "").strip().lower()
    if not t:
        return False
    st = identity.gacha
    new = False
    lst = list(st.get("unlocked") or [])
    if t not in lst and t not in defaults_cores(identity):
        lst.append(t)
        st["unlocked"] = lst
        new = True
    if color:
        colors = st.setdefault("colors", {})
        new = _add_color(colors, t, color) or new
    if pattern:
        patterns = st.setdefault("patterns", {})
        new = _add_pattern(patterns, t, pattern) or new
    return new


def pool(identity, *, allow_nsfw: bool = False, cur_len: str = "") -> list[dict]:
    allowed = allowed_cores(identity)
    if allowed is None:
        allowed = ss.Allowance()
    out: list[dict] = []
    for it in universe(allow_nsfw=allow_nsfw, cur_len=cur_len,
                       body=ss.body_of(identity)):
        k = it["tag"]
        is_open = k in allowed
        pal = ss.palette(k)
        if pal:
            opened = set(allowed.open_colors(k)) if is_open else set()
            left = [c for c in pal if c not in opened]
            opened_p = set(allowed.open_patterns(k)) if is_open else set()
            pleft = [p for p in ss.patterns_of(k) if p not in opened_p]
            if left or pleft:
                out.append({**it, "colors": left, "patterns": pleft,
                            "new_item": not is_open})
        elif not is_open:
            out.append({**it, "colors": [], "patterns": [], "new_item": True})
    return out


def _pool_size(entries: list[dict]) -> int:
    return sum((len(e["colors"]) + len(e.get("patterns") or ())) or 1 for e in entries)


def pulls_since(pulls: list[dict], rarities) -> int:
    n = 0
    for p in reversed(pulls or []):
        if str(p.get("rarity") or "") in rarities:
            break
        n += 1
    return n


def sphere_in(identity) -> int:
    st = identity.gacha if has_gacha(identity) and isinstance(identity.gacha, dict) else {}
    n = int(st.get("pull_count") or len(st.get("pulls") or []))
    return SPHERE_EVERY - n % SPHERE_EVERY


def pity_state(identity) -> dict:
    pulls = list((identity.gacha or {}).get("pulls") or []) if has_gacha(identity) else []
    return {
        "rare_in": max(1, RARE_PITY - pulls_since(pulls, ("rare", "legendary"))),
        "legendary_in": max(1, LEGENDARY_PITY - pulls_since(pulls, ("legendary",))),
    }


def sphere_targets(identity, *, allow_nsfw: bool = False, cur_len: str = "") -> list[dict]:
    return [it for it in pool(identity, allow_nsfw=allow_nsfw, cur_len=cur_len)
            if not it["new_item"] and (it["colors"] or it.get("patterns"))]


def spheres(identity) -> int:
    if not has_gacha(identity):
        return 0
    return int((identity.gacha or {}).get("spheres", 0) or 0)


def pull(identity, *, allow_nsfw: bool = False, cur_len: str = "",
         rng: random.Random | None = None, now: float | None = None) -> dict:
    if not has_gacha(identity):
        raise GachaError("механика недоступна")
    touch(identity, now)
    st = identity.gacha
    if int(st.get("tickets", 0) or 0) <= 0:
        raise NoTickets()
    avail = pool(identity, allow_nsfw=allow_nsfw, cur_len=cur_len)
    if not avail:
        raise PoolEmpty()
    rng = rng or random.SystemRandom()
    tiers = {r: [it for it in avail if it["rarity"] == r] for r in RARITY_ORDER}
    sphere_ok = any(not it["new_item"] and (it["colors"] or it.get("patterns"))
                    for it in avail)
    choices = [r for r in RARITY_ORDER
               if tiers[r] or (r == "rare" and sphere_ok)]
    pulls = list(st.get("pulls") or [])
    pity = ""
    if (pulls_since(pulls, ("legendary",)) >= LEGENDARY_PITY - 1
            and "legendary" in choices):
        choices, pity = ["legendary"], "legendary"
    elif pulls_since(pulls, ("rare", "legendary")) >= RARE_PITY - 1:
        better = [r for r in choices if r != "common"]
        if better:
            choices, pity = better, "rare"
    weights = [RARITY_WEIGHTS[r] for r in choices]
    tier = rng.choices(choices, weights=weights, k=1)[0]
    ts = now if now is not None else time.time()
    if tier == "rare" and sphere_ok and (not tiers["rare"] or rng.random() < SPHERE_SHARE):
        st["tickets"] = int(st.get("tickets", 0) or 0) - 1
        st["spheres"] = spheres(identity) + 1
        item = {"tag": SPHERE_TAG, "slot": "special", "rarity": "rare",
                "special": "sphere", "new_item": True, "color": "",
                "colors_before": [], "spheres": st["spheres"],
                "targets": [label_of(it["tag"]) for it in avail
                            if not it["new_item"] and (it["colors"] or it.get("patterns"))][:6]}
        item["series"] = series_note(pulls, ts)
        rec = {"tag": SPHERE_TAG, "rarity": "rare", "at": ts, "special": "sphere"}
    else:
        item = dict(rng.choice(tiers[tier]))
        color = pattern = None
        pats = list(item.get("patterns") or [])
        if item["new_item"] and item["colors"]:
            color = rng.choice(item["colors"])
        else:
            variants = [("c", c) for c in item["colors"]] + [("p", q) for q in pats]
            if variants:
                kind, val = rng.choice(variants)
                color, pattern = (val, None) if kind == "c" else (None, val)
        if color:
            before = open_colors(identity, item["tag"])
        elif pattern:
            before = open_patterns(identity, item["tag"])
        else:
            before = []
        st["tickets"] = int(st.get("tickets", 0) or 0) - 1
        unlock(identity, item["tag"], color, pattern)
        item.pop("colors", None)
        item.pop("patterns", None)
        item["color"] = color or ""
        item["pattern"] = pattern or ""
        item["colors_before"] = before if color else []
        item["patterns_before"] = before if pattern else []
        item["series"] = series_note(pulls, ts)
        item["angle"] = pick_angle(identity, rng)
        rec = {"tag": item["tag"], "rarity": item["rarity"], "at": ts}
        if color:
            rec["color"] = color
        if pattern:
            rec["pattern"] = pattern
    if pity:
        rec["pity"] = pity
        item["pity"] = pity
    n = int(st.get("pull_count") or len(pulls)) + 1
    st["pull_count"] = n
    if n % SPHERE_EVERY == 0:
        st["spheres"] = spheres(identity) + 1
        item["bonus_sphere"] = st["spheres"]
        rec["bonus_sphere"] = True
    pulls.append(rec)
    st["pulls"] = pulls[-1500:]
    return item


class NoSpheres(GachaError):
    pass


def use_sphere(identity, tag: str, color: str = "", *, pattern: str = "",
               allow_nsfw: bool = False) -> dict:
    if not has_gacha(identity):
        raise GachaError("механика недоступна")
    ensure_state(identity)
    t = (tag or "").strip().lower()
    c = ss.color_word(color or "") or ""
    pat = (pattern or "").strip().lower()
    if spheres(identity) <= 0:
        raise NoSpheres("сфер изменения нет — они выпадают из билетов удачи")
    allowed = allowed_cores(identity)
    if not t or t not in allowed or t in ss.UNDERWEAR_IMPLICIT:
        raise GachaError("эта вещь ещё не открыта — сфера открывает цвет только того, что уже есть")
    if ss.route_tag(t) in NSFW_SLOTS and not allow_nsfw:
        raise GachaError("эта вещь сейчас недоступна")
    if pat:
        if pat not in ss.patterns_of(t):
            raise GachaError("такого узора у этой вещи не бывает")
        if pat in allowed.open_patterns(t):
            raise GachaError("этот узор уже открыт")
        c = ""
    else:
        if c not in ss.palette(t):
            raise GachaError("такого цвета у этой вещи не бывает")
        if c in allowed.open_colors(t):
            raise GachaError("этот цвет уже открыт")
    unlock(identity, t, c or None, pat or None)
    st = identity.gacha
    st["spheres"] = spheres(identity) - 1
    uses = list(st.get("sphere_uses") or [])
    use = {"tag": t, "at": time.time()}
    use.update({"pattern": pat} if pat else {"color": c})
    uses.append(use)
    st["sphere_uses"] = uses[-200:]
    return {"tag": t, "color": c, "pattern": pat, "spheres": st["spheres"]}


def describe_item(item: dict) -> dict:
    out = _describe_item(item)
    if item.get("bonus_sphere"):
        card = _describe_item({"tag": SPHERE_TAG, "special": "sphere",
                               "spheres": item["bonus_sphere"]})
        card["category_label"] = f"бонус за каждые {SPHERE_EVERY} билетов"
        out["bonus_sphere"] = card
    return out


def _describe_item(item: dict) -> dict:
    tag = item["tag"]
    if item.get("special") == "sphere":
        return {
            "tag": tag, "label": SPHERE_LABEL, "category": "special",
            "category_label": "особый предмет", "rarity": "rare",
            "rarity_label": RARITY_RU["rare"], "nsfw": False, "color": "",
            "color_label": "", "colored_tag": "", "new_item": True,
            "colors_before": [], "special": "sphere",
            "spheres": int(item.get("spheres") or 0),
            "targets": list(item.get("targets") or []),
            "hint": ("откроет один цвет (у белья — или узор) любой уже открытой "
                     "вещи — выбор в окне гардероба, раздел «Стайлинг»: клик по "
                     "вещи, затем по цвету"),
        }
    slot = item.get("slot") or ss.route_tag(tag) or ""
    rarity = item.get("rarity") or rarity_of(tag)
    color = item.get("color") or ""
    pattern = item.get("pattern") or ""
    sec = ss.wearable_section(tag) if slot == "accessory" else ""
    return {
        "tag": tag,
        "label": label_of(tag),
        "category": slot,
        "category_label": (ss.WEARABLE_SECTION_ITEM.get(sec) if sec else None)
                          or CATEGORY_RU.get(slot, "образ"),
        "rarity": rarity,
        "rarity_label": RARITY_RU.get(rarity, rarity),
        "nsfw": slot in NSFW_SLOTS,
        "color": color,
        "color_label": ss.color_label(color) if color else "",
        "pattern": pattern,
        "pattern_label": ss.pattern_label(pattern) if pattern else "",
        "colored_tag": ss.join_style_tag(color, pattern, tag),
        "new_item": bool(item.get("new_item", True)),
        "colors_before": [ss.color_label(c) for c in item.get("colors_before") or []],
        "patterns_before": [ss.pattern_label(q) for q in item.get("patterns_before") or []],
    }


def summary(identity, *, allow_nsfw: bool = False, cur_len: str = "") -> dict:
    uni = universe(allow_nsfw=allow_nsfw, cur_len=cur_len, body=ss.body_of(identity))
    total = sum((len(ss.palette(it["tag"])) + len(ss.patterns_of(it["tag"]))) or 1
                for it in uni)
    if allowed_cores(identity) is None:
        left = total
    else:
        left = _pool_size(pool(identity, allow_nsfw=allow_nsfw, cur_len=cur_len))
    st = identity.gacha if has_gacha(identity) else {}
    return {
        "tickets": tickets(identity),
        "cap": TICKET_CAP,
        "per_day": DAILY_TICKETS,
        "sphere_in": sphere_in(identity),
        "sphere_every": SPHERE_EVERY,
        "unlocked": total - left,
        "total": total,
        "pool": left,
        "last_daily": str((st or {}).get("last_daily") or ""),
        "spheres": spheres(identity),
        **pity_state(identity),
    }


def unworn_unlocked(identity, *, allow_nsfw: bool = False, limit: int = 12) -> list[str]:
    if not has_gacha(identity) or not identity.gacha.get("last_daily"):
        return []
    worn = _cores_of_state(ss.styling_state(identity))
    out: list[str] = []
    for t in identity.gacha.get("unlocked") or []:
        if t in worn or t in ss.UNDERWEAR_IMPLICIT:
            continue
        slot = ss.route_tag(t)
        if slot in NSFW_SLOTS and not allow_nsfw:
            continue
        out.append(t)
    return out[:limit]


def item_hint(identity, tag: str) -> str:
    mark = ss.color_mark(tag, open_colors(identity, tag) if ss.palette(tag) else [],
                         open_patterns(identity, tag) if ss.patterns_of(tag) else [])
    return f"{label_of(tag)} ({tag}; {mark})" if mark else f"{label_of(tag)} ({tag})"


_ANGLES = (
    "сама вещь: как это будет смотреться на тебе и идёт ли тебе вообще",
    "везение: насколько это удача или так себе — с учётом редкости и того, "
    "что выпадало раньше",
    "рука собеседника: как ему сегодня везёт с билетами — поддразни или "
    "отметь",
    "план: когда и с чем это надеть — или почему пока не станешь",
    "сравнение с тем, что у тебя уже есть, и чего в образе не хватает",
    "твоё настроение прямо сейчас: реакция сквозь него",
)

_RARITY_NOTE = {
    "common": "обычная, таких в пуле большинство",
    "rare": "редкая, выпадает нечасто",
    "legendary": "легендарная, такие выпадают реже всего",
}


def pick_angle(identity, rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    st = identity.gacha if (has_gacha(identity) and isinstance(identity.gacha, dict)) else None
    last = st.get("last_angle") if st is not None else None
    options = [i for i in range(len(_ANGLES)) if i != last] or list(range(len(_ANGLES)))
    i = rng.choice(options)
    if st is not None:
        st["last_angle"] = i
    return _ANGLES[i]


def series_note(pulls: list[dict], now: float) -> str:
    if not pulls:
        return "Это самый первый билет удачи в вашей истории."
    today = _day(now)
    todays = [p for p in pulls if _day(float(p.get("at") or 0)) == today]
    if not todays:
        return "Это первый билет сегодня."
    before = ", ".join(RARITY_RU.get(str(p.get("rarity") or ""), "обычная")
                       for p in todays[-3:])
    return (f"Это {len(todays) + 1}-й билет подряд за сегодня; перед ним "
            f"выпали: {before}.")


def reaction_trigger(item: dict, *, honorific: str, female: bool = True,
                     angle: str | None = None, series: str = "") -> str:
    if item.get("special") == "sphere":
        return _bonus_note(sphere_trigger(item, honorific=honorific, series=series),
                           item, honorific, also=True)
    return _bonus_note(_item_trigger(item, honorific=honorific, female=female,
                                     angle=angle, series=series), item, honorific)


def _bonus_note(text: str, item: dict, honorific: str, also: bool = False) -> str:
    bonus = item.get("bonus_sphere")
    if not bonus:
        return text
    n = int((bonus or {}).get("spheres") or 1) if isinstance(bonus, dict) else int(bonus)
    what = "И ещё одна сфера — бонусом" if also else "Вдобавок выпала сфера изменения — бонус"
    return (text[:-1] + f" {what} за каждые {SPHERE_EVERY} открытых билетов (сфер "
            f"теперь {n}; тратит {honorific}). Её можно упомянуть мимоходом или "
            f"не упоминать.)")


def _item_trigger(item: dict, *, honorific: str, female: bool = True,
                  angle: str | None = None, series: str = "") -> str:
    rarity = item.get("rarity") or "common"
    note = _RARITY_NOTE.get(rarity, _RARITY_NOTE["common"])
    nsfw_note = (" Это деталь под одеждой (18+) — реагируй уместно, без пошлости."
                 if item.get("nsfw") else "")
    who = "сама" if female else "сам"
    angle = angle or random.SystemRandom().choice(_ANGLES)
    series = (series + " ") if series else ""
    what = f"«{item['label']}»"
    if item.get("color"):
        what += f", цвет — {item.get('color_label') or item['color']}"
    if item.get("pattern"):
        what += f", узор — {item.get('pattern_label') or item['pattern']}"
    tag = item.get("colored_tag") or item["tag"]
    novelty = ""
    if item.get("color") and not item.get("new_item", True):
        had = ", ".join(item.get("colors_before") or [])
        novelty = (" Сама вещь у тебя уже есть" + (f" ({had})" if had else "")
                   + " — открылся новый её цвет.")
    elif item.get("pattern"):
        had = ", ".join(item.get("patterns_before") or [])
        novelty = (" Сама вещь у тебя уже есть — открылся новый узор для неё"
                   + (f" (уже были: {had})" if had else "") + "; носится вместе "
                   "с любым её открытым цветом.")
    return (f"(Служебное событие: вы с {honorific} вместе открываете билет удачи — "
            f"маленькая лотерея на двоих: что выпадет для твоего образа, заранее "
            f"не знает никто. {series}Выпало: {what} ({tag}; "
            f"{item['category_label']}; редкость: {note}).{novelty} Теперь это твоё — "
            f"носить или нет, решишь {who} позже: надевается инструментом "
            f"style_self в обычном разговоре, прямо сейчас ничего надевать не "
            f"нужно.{nsfw_note} Отреагируй строго в своём характере и по СВОЕМУ "
            f"вкусу: вещь может нравиться, а может и нет — скажи честно; "
            f"редкость сама по себе ни к восторгу, ни к разочарованию не "
            f"обязывает. Ракурс этой реакции — {angle}. Форма на твой выбор: "
            f"встречный вопрос, одна короткая реплика или мысль вслух — не "
            f"больше двух фраз. Не повторяй форму и слова своих прошлых реакций "
            f"на билеты, начни иначе. Без благодарностей за «подарок» и без "
            f"пересказа механики билетов.)")


def sphere_trigger(item: dict, *, honorific: str, series: str = "") -> str:
    series = (series + " ") if series else ""
    targets = list(item.get("targets") or [])
    have = (" Вещи, которым есть что открыть: " + ", ".join(targets) + "."
            if targets else "")
    n = int(item.get("spheres") or 1)
    stock = f" Сфер сейчас накоплено: {n}." if n > 1 else ""
    return (f"(Служебное событие: вы с {honorific} вместе открываете билет удачи — "
            f"маленькая лотерея на двоих. {series}Выпала не вещь, а сфера "
            f"изменения (редкая находка): она открывает ОДИН новый цвет для любой "
            f"вещи, которая у тебя уже есть — ленты, украшения, макияжа, белья (у "
            f"белья — или узор); причёскам цвет не нужен.{have}{stock} Какой вещи "
            f"и какой цвет "
            f"открыть, решает {honorific}: в окне гардероба, в разделе «Стайлинг». "
            f"Можешь сказать, чего хотелось бы тебе, — или промолчать об этом. "
            f"Отреагируй строго в своём характере и по СВОЕМУ вкусу: встречный "
            f"вопрос, одна короткая реплика или мысль вслух — не больше двух фраз. "
            f"Не повторяй форму и слова своих прошлых реакций на билеты, начни "
            f"иначе. Без благодарностей за «подарок» и без пересказа механики "
            f"билетов.)")


def history_marker(item: dict) -> str:
    text = _history_marker(item)
    if item.get("bonus_sphere"):
        text = (text[:-2] + f"; плюс бонусная сфера изменения — за каждые "
                f"{SPHERE_EVERY} открытых билетов.)")
    return text


def _history_marker(item: dict) -> str:
    if item.get("special") == "sphere":
        return ("(Билет удачи открыт вместе — выпала сфера изменения: она откроет "
                "один новый цвет уже открытой вещи; выбор — в гардеробе, раздел "
                "«Стайлинг».)")
    color = f", {item['color_label']}" if item.get("color") else ""
    if item.get("pattern"):
        color += f", узор {item.get('pattern_label') or item['pattern']}"
    novelty = ("; новый цвет уже открытой вещи"
               if item.get("color") and not item.get("new_item", True) else
               "; новый узор уже открытой вещи" if item.get("pattern") else "")
    return (f"(Билет удачи открыт вместе — выпало для образа: «{item['label']}»"
            f"{color} ({item.get('colored_tag') or item['tag']}, "
            f"{item['category_label']}; редкость: {item['rarity_label']}{novelty}).)")


CATEGORY_ORDER = ("hair_style", "hair_texture", "hair_bangs", "hair_extra",
                  "makeup",
                  *(f"accessory:{sec}" for sec in ss.WEARABLES),
                  "underwear", "intimate")
CATEGORY_TITLE = {
    "hair_style": "Укладка", "hair_texture": "Текстура волос",
    "hair_bangs": "Чёлка", "hair_extra": "Элементы причёски",
    "makeup": "Макияж",
    **{f"accessory:{sec}": title for sec, title in ss.WEARABLE_SECTION_TITLE.items()},
    "underwear": "Бельё", "intimate": "Интимное",
}


def _group_of(tag: str, slot: str) -> str:
    if slot == "accessory":
        return f"accessory:{ss.wearable_section(tag)}"
    return slot


def worn_map(identity, *, outfit_hair: bool = False) -> dict[str, str]:
    state = ss.styling_state(identity)
    out: dict[str, str] = {}
    hair = list(ss.hair_tags(state))
    tags = [] if outfit_hair else list(hair)
    for key in ("accessories", "makeup", "underwear", "intimate"):
        tags += list(state.get(key) or [])
    for t in tags:
        k = ss.allowance_key(t)
        if k:
            out.setdefault(k, t)
    swap = {ss.allowance_key(t) for t in ss.base_swap_tags(identity)}
    hide_swap = outfit_hair or bool(hair)
    for t in ss.base_appearance_tags(identity):
        k = ss.allowance_key(t)
        if not k or k in out or (hide_swap and k in swap):
            continue
        out[k] = t
    return out


def collection(identity, *, allow_nsfw: bool = False, cur_len: str = "",
               outfit_hair: bool = False) -> dict:
    allowed = allowed_cores(identity)
    if allowed is None:
        return {}
    uni = universe(allow_nsfw=allow_nsfw, cur_len=cur_len, body=ss.body_of(identity))
    worn = worn_map(identity, outfit_hair=outfit_hair)
    defaults = design_cores(identity)
    innate = innate_cores(identity)
    pulled = {str(p.get("tag") or "") for p in (identity.gacha.get("pulls") or [])}

    def item(key: str, slot: str, rarity: str) -> dict:
        w = worn.get(key)
        pal = ss.palette(key)
        opened = set(allowed.open_colors(key)) if pal else set()
        worn_color = ss.tag_color(w) if w else None
        pats = ss.patterns_of(key)
        opened_p = set(allowed.open_patterns(key)) if pats else set()
        worn_pattern = ss.tag_pattern(w) if w else None
        return {
            "tag": key, "label": label_of(key),
            "category": slot, "rarity": rarity,
            "rarity_label": RARITY_RU.get(rarity, rarity),
            "worn": w is not None,
            "worn_as": (w if (w and w != key) else ""),
            "source": ("default" if key in defaults else
                       "innate" if key in innate else
                       "gacha" if key in pulled else "legacy"),
            "colors": [{"key": c, "label": ss.color_label(c),
                        "open": c in opened, "worn": c == worn_color}
                       for c in pal],
            "colors_open": len(opened & set(pal)),
            "colors_total": len(pal),
            "patterns": ([{"key": ss.PLAIN_PATTERN, "label": ss.PLAIN_LABEL,
                           "open": True, "worn": w is not None and worn_pattern is None}]
                         if pats else [])
                        + [{"key": q, "label": ss.pattern_label(q),
                            "open": q in opened_p, "worn": q == worn_pattern}
                           for q in pats],
            "patterns_open": (len(opened_p & set(pats)) + 1) if pats else 0,
            "patterns_total": (len(pats) + 1) if pats else 0,
        }

    cats = {k: {"key": k, "label": CATEGORY_TITLE[k], "items": [], "locked": 0}
            for k in CATEGORY_ORDER if allow_nsfw or k not in NSFW_SLOTS}
    seen: set[str] = set()
    for it in uni:
        key, slot = it["tag"], it["slot"]
        seen.add(key)
        cat = cats.get(it.get("group") or slot)
        if cat is None:
            continue
        if not ss.tag_allowed(key, allowed):
            cat["locked"] += 1
            continue
        cat["items"].append(item(key, slot, it["rarity"]))
    for key in sorted(allowed):
        if key in seen or key not in worn or key in ss.UNDERWEAR_IMPLICIT:
            continue
        slot = ss.route_tag(key) or ""
        cat = cats.get(_group_of(key, slot))
        if cat is not None:
            cat["items"].append(item(key, slot, rarity_of(key)))
    for cat in cats.values():
        cat["items"].sort(key=lambda x: (not x["worn"],
                                         -RARITY_ORDER.index(x["rarity"]),
                                         x["label"]))
    out = summary(identity, allow_nsfw=allow_nsfw, cur_len=cur_len)
    out["worn_count"] = sum(1 for c in cats.values() for x in c["items"] if x["worn"])
    out["categories"] = [cats[k] for k in CATEGORY_ORDER if k in cats]
    return out
