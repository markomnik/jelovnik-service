"""
Datum i vreme u srpskom tekstu pozivnice (pravila, bez AI-ja).

find_dates(text, today)  svi datumi redom: 10.10.2026., 31. oktobra, 2026-10-10, sutra, u subotu...
find_times(text)         sva vremena redom: 18h, 18:30, 13.30h, od 21 do 02h, 6 pm...
Oba očekuju tekst u latinici (vidi core/text_utils.py).
"""

import re
from datetime import date, time as dtime, timedelta


_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "may": 5, "jun": 6, "jul": 7,
           "avg": 8, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12}


_MONTH_WORDS = "|".join(_MONTHS)


_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


_DATE_NUM = re.compile(r"(?<![\d.])(\d{1,2})\s?[./]\s?(\d{1,2})(?:\s?[./]\s?(\d{4}|\d{2})(?!\d))?\.?")


_DATE_TXT = re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s*({_MONTH_WORDS})[a-zčćšđž]*\.?(?:\s*(\d{{4}})(?!\d))?\.?", re.I)


_DATE_REL = re.compile(
    r"\b(danas|sutra|prekosutra|ponedeljak|ponedeljka|ponedeljku|utorak|utorka|utorku|"
    r"sredu|sreda|srede|cetvrtak|četvrtak|cetvrtka|četvrtka|petak|petka|petku|"
    r"subotu|subota|subote|nedelju|nedelja|nedelje)\b", re.I)


_WEEKDAY_STEMS = [("ponedelj", 0), ("utor", 1), ("sred", 2), ("cetvrt", 3), ("četvrt", 3),
                  ("pet", 4), ("subot", 5), ("nedelj", 6)]


def _build_date(day: int, month: int, year, today: date) -> tuple[date | None, bool]:
    """Vraća (datum, godina_pretpostavljena). Bez godine uzima najbliži predstojeći datum."""
    try:
        if year is None:
            candidate = date(today.year, month, day)
            if candidate < today:
                candidate = date(today.year + 1, month, day)
            return candidate, True
        year = int(year)
        return date(year + 2000 if year < 100 else year, month, day), False
    except ValueError:
        return None, False


def find_dates(text: str, today: date) -> list[dict]:
    """Svi datumi u tekstu, redom kojim se pojavljuju: {date, start, end, inferred_year, rel}."""
    found = []   # (start, end, prioritet, rečnik)

    def add(m, prio, dt, inferred, rel=None):
        if dt:
            found.append((m.start(), m.end(), prio,
                          {"date": dt, "start": m.start(), "end": m.end(), "inferred_year": inferred, "rel": rel}))

    for m in _DATE_ISO.finditer(text):
        dt, inf = _build_date(int(m.group(3)), int(m.group(2)), m.group(1), today)
        add(m, 0, dt, inf)
    for m in _DATE_TXT.finditer(text):
        dt, inf = _build_date(int(m.group(1)), _MONTHS[m.group(2).lower()], m.group(3), today)
        add(m, 1, dt, inf)
    for m in _DATE_NUM.finditer(text):
        dt, inf = _build_date(int(m.group(1)), int(m.group(2)), m.group(3), today)
        add(m, 2, dt, inf)

    if not found:   # relativni izrazi samo ako nema nijednog izričitog datuma
        for m in _DATE_REL.finditer(text):
            word = m.group(1).lower()
            if word in ("danas", "sutra", "prekosutra"):
                dt = today + timedelta(days={"danas": 0, "sutra": 1, "prekosutra": 2}[word])
            else:
                wd = next(w for stem, w in _WEEKDAY_STEMS if word.startswith(stem))
                dt = today + timedelta(days=(wd - today.weekday()) % 7 or 7)   # prvi sledeći takav dan
            add(m, 3, dt, False, rel=word)

    found.sort(key=lambda f: (f[0], f[2]))
    kept, last_end = [], -1
    for start, end, _, item in found:
        if start >= last_end:
            kept.append(item)
            last_end = end
    return kept


_UNIT = r"(?:h|č|časova|casova|sati)"


_T = r"(\d{1,2})(?:[.:]([0-5]\d))?"


_TIME_RANGE = re.compile(rf"(?<![\d.:]){_T}\s*{_UNIT}?\s*(?:-|–|—|do)\s*{_T}\s*{_UNIT}(?!\w)", re.I)


_TIME_AMPM = re.compile(r"(?<![\d.:])(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", re.I)


_TIME_COLON = re.compile(r"(?<![\d.:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")


_TIME_DOT_UNIT = re.compile(rf"(?<![\d.:])([01]?\d|2[0-3])\.([0-5]\d)\s*{_UNIT}(?!\w)", re.I)


_TIME_HOUR_UNIT = re.compile(rf"(?<![\d.:])([01]?\d|2[0-3])\s*{_UNIT}(?!\w)", re.I)


_TIME_U_DOT = re.compile(r"(?<!\w)u\s+([01]?\d|2[0-3])[.:]([0-5]\d)(?![\w.])", re.I)


def _mk_time(hour, minute) -> dtime | None:
    h, m = int(hour), int(minute or 0)
    return dtime(h, m) if h <= 23 and m <= 59 else None


def find_times(text: str) -> list[tuple[dtime, int, int]]:
    """Sva vremena u tekstu redom: (vreme, početak, kraj). Opseg '18-21h' daje dva vremena."""
    found = []   # (start, end, prioritet, [vremena])

    for m in _TIME_RANGE.finditer(text):
        t1, t2 = _mk_time(m.group(1), m.group(2)), _mk_time(m.group(3), m.group(4))
        if t1 and t2:
            found.append((m.start(), m.end(), 0, [t1, t2]))
    for m in _TIME_AMPM.finditer(text):
        hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        found.append((m.start(), m.end(), 1, [_mk_time(hour, m.group(2))]))
    for prio, rx in ((2, _TIME_COLON), (3, _TIME_DOT_UNIT), (4, _TIME_HOUR_UNIT), (5, _TIME_U_DOT)):
        for m in rx.finditer(text):
            t = _mk_time(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else 0)
            if t:
                found.append((m.start(), m.end(), prio, [t]))

    found.sort(key=lambda f: (f[0], f[2]))
    result, last_end = [], -1
    for start, end, _, times in found:
        if start >= last_end:
            result += [(t, start, end) for t in times]
            last_end = end
    return result


def mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Zamenjuje delove teksta razmacima (iste dužine), da datum ne bude pročitan kao vreme."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def time_from_field(value: str) -> dtime | None:
    """Vreme iz polja za koje već znamo da je vreme (dozvoljava i golo '18.00' ili '18')."""
    found = find_times(value)
    if found:
        return found[0][0]
    m = re.match(r"^\s*([01]?\d|2[0-3])(?:[.:,]([0-5]\d))?\s*$", value)
    return _mk_time(m.group(1), m.group(2)) if m else None


def relative_date_spans(text: str) -> list[tuple[int, int]]:
    """Položaji reči poput "sutra" ili "subotu" u tekstu (za čišćenje naslova)."""
    return [(m.start(), m.end()) for m in _DATE_REL.finditer(text)]
