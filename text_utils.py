"""Zajednički pomoćnici za tekst (koriste ih app.py i event_parser.py)."""

_CYR2LAT = {
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v", "Г": "G", "г": "g",
    "Д": "D", "д": "d", "Ђ": "Đ", "ђ": "đ", "Е": "E", "е": "e", "Ж": "Ž", "ж": "ž",
    "З": "Z", "з": "z", "И": "I", "и": "i", "Ј": "J", "ј": "j", "К": "K", "к": "k",
    "Л": "L", "л": "l", "М": "M", "м": "m", "Н": "N", "н": "n", "О": "O", "о": "o",
    "П": "P", "п": "p", "Р": "R", "р": "r", "С": "S", "с": "s", "Т": "T", "т": "t",
    "Ћ": "Ć", "ћ": "ć", "У": "U", "у": "u", "Ф": "F", "ф": "f", "Х": "H", "х": "h",
    "Ц": "C", "ц": "c", "Ч": "Č", "ч": "č", "Ш": "Š", "ш": "š",
    "Љ": "Lj", "љ": "lj", "Њ": "Nj", "њ": "nj", "Џ": "Dž", "џ": "dž",
}


def cyr_to_lat(text: str) -> str:
    """Prevodi srpsku ćirilicu u latinicu, karakter po karakter (digrafi lj/nj/dž uključeni).
    Karakteri van mape (brojevi, interpunkcija, latinica) ostaju nepromenjeni."""
    if not text:
        return text
    return "".join(_CYR2LAT.get(ch, ch) for ch in text)
