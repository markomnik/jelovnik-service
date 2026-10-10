"""
Parsiranje pozivnice (tekst i/ili slika) u parametre kalendarskog događaja.

parse_event(text=None, image=None) vraća rečnik spreman za upis u kalendar:
    {"title", "all_day", "start", "end", "location", "description", "notes", "end_assumed"}

    start / end:  "YYYY-MM-DDTHH:MM" (lokalno vreme, Europe/Belgrade),
                  ili "YYYY-MM-DD" za događaj celog dana.
                  Kod događaja celog dana "end" je POSLEDNJI dan (uključivo).

Kako se parsira:
  * slika  -> freeocr.ai /extract (AI izvlači polja: naslov, datum, vreme, lokacija, detalji);
              ako datum ili naslov fale, dodatno /ocr (ceo tekst sa slike) pa pravila ispod
  * tekst  -> pravila za srpske datume i vreme (isto se primenjuje na opis uz sliku)
Obe putanje na kraju prolaze kroz isti normalize_event().

Sav tekst se pretvara u latinicu (text_utils.cyr_to_lat), pa je i naslov događaja u kalendaru latinica.
Potrebna varijabla: FREEOCR_API_KEY (isti servis i klijent kao za jelovnik, vidi freeocr_client.py).
Modul ne zavisi od Flask-a.
"""

import re
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import freeocr_client
from freeocr_client import FreeOCRError
from text_utils import cyr_to_lat

TZ = ZoneInfo("Europe/Belgrade")
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
EXTRACT_FIELDS = ["title", "date", "start_time", "end_time", "location", "details"]


class ParseError(Exception):
    """Greška čija se poruka sme prikazati korisniku."""


# --------------------------------------------------------------------------
# Datum
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Vreme
# --------------------------------------------------------------------------

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


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    """Zamenjuje delove teksta razmacima (iste dužine), da datum ne bude pročitan kao vreme."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def _time_from_field(value: str) -> dtime | None:
    """Vreme iz polja za koje već znamo da je vreme (dozvoljava i golo '18.00' ili '18')."""
    found = find_times(value)
    if found:
        return found[0][0]
    m = re.match(r"^\s*([01]?\d|2[0-3])(?:[.:,]([0-5]\d))?\s*$", value)
    return _mk_time(m.group(1), m.group(2)) if m else None


# --------------------------------------------------------------------------
# Tekst -> polja
# --------------------------------------------------------------------------

_LABEL = re.compile(
    r"^(?P<key>naslov|povod|dogadjaj|događaj|event|title|mesto|lokacija|adresa|gde|place|where|venue|location|"
    r"datum|date|kada|when|vreme|time|pocetak|početak)\s*[:\-–]\s*(?P<val>.+)$", re.I)
_LABEL_KIND = {"naslov": "title", "povod": "title", "dogadjaj": "title", "događaj": "title", "event": "title",
               "title": "title", "mesto": "location", "lokacija": "location", "adresa": "location",
               "gde": "location", "place": "location", "where": "location", "venue": "location",
               "location": "location"}   # ostale labele (datum, vreme) ne treba posebno: datum/vreme se traže u celom tekstu

_PREP_BEFORE = re.compile(r"\b(?:u|na|dana|od|do|oko|on|at|from|to)\s*$", re.I)
_PREAMBLE = re.compile(
    r"^(?:(?:pozivam|pozivamo|zovem|zovemo)\s+(?:te|vas)(?:\s+sve)?\s*(?:na|u)?\s+|(?:poziv|pozivnica)\s+(?:za|na)\s+)", re.I)
_GENERIC_HEADING = re.compile(r"^(?:pozivnica|poziv|invitation|save the date|pozivamo vas|pozivamo vas na)\W*$", re.I)

_LOC_KEYWORDS = (r"(?:restoran|kafe|kafić|kafic|sala|sali|klub|hotel|vila|dom|domu|hram|crkva|crkvi|park|parku|"
                 r"bioskop|pozorište|pozoriste|galerija|galeriji|škola|skola|školi|stan|kuća|kuci|kući|bašta|basta)")
_LOC_RE = re.compile(
    rf"(?:(?:^|[,;]\s*)|\b(?:u|na|kod)\s+)({_LOC_KEYWORDS}\w*"
    r"(?:\s+(?!(?:na|za|i|da|jer|u|kod|sa|od|do)\b)[\w\"„“'.\-]+){0,3})", re.I)
_ADDR_RE = re.compile(r"\b((?:ul\.|ulica|bul\.|bulevar|trg|kej)\s+[^,;\n]+?\d+\w?(?:/\d+)?)", re.I)


def _strip_spans(line: str, spans: list[tuple[int, int]]) -> str:
    """Izbacuje datum/vreme iz reda (zajedno sa predlogom ispred, npr. 'u 18h')."""
    parts, pos = [], 0
    for start, end in sorted(spans):
        start = max(start, pos)
        m = _PREP_BEFORE.search(line[pos:start])
        parts.append(line[pos:pos + m.start()] if m else line[pos:start])
        pos = max(end, pos)
    parts.append(line[pos:])
    out = re.sub(r"\s+", " ", " ".join(p.strip() for p in parts if p.strip()))
    out = re.sub(r"\s+([,;.])", r"\1", out)
    return out.strip(" ,;:-–—.")


def _clean_line(line: str, today: date) -> str:
    dates = find_dates(line, today)
    spans = [(d["start"], d["end"]) for d in dates]
    spans += [(m.start(), m.end()) for m in _DATE_REL.finditer(line)]
    spans += [(s, e) for _, s, e in find_times(_mask(line, spans))]
    return _strip_spans(line, spans)


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _strip_markdown(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[#*_`>|]", " ", text)


def _from_text(text: str, today: date) -> dict:
    """Pravila za srpski tekst pozivnice. Vraća polja u formi koju razume normalize_event()."""
    text = cyr_to_lat(text)
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    raw: dict = {}
    notes = []

    labeled, rest = {}, []
    for line in lines:
        m = _LABEL.match(line)
        kind = _LABEL_KIND.get(m.group("key").lower()) if m else None
        if kind:
            labeled.setdefault(kind, m.group("val").strip())
        else:
            rest.append(m.group("val").strip() if m else line)   # "Datum: 14.10." -> "14.10."

    # datum i vreme: traže se u celom tekstu
    whole = "\n".join(lines)
    dates = find_dates(whole, today)
    if dates:
        raw["start_date"] = dates[0]["date"].isoformat()
        other = next((d["date"] for d in dates[1:] if d["date"] > dates[0]["date"]), None)
        if other:
            raw["end_date"] = other.isoformat()
        if dates[0]["inferred_year"]:
            notes.append(f"Godina nije navedena, pretpostavljena {dates[0]['date'].year}.")
        if dates[0]["rel"]:
            notes.append(f"Datum izveden iz reči „{dates[0]['rel']}“.")
    times = find_times(_mask(whole, [(d["start"], d["end"]) for d in dates]))
    if times:
        raw["start_time"] = times[0][0].strftime("%H:%M")
        if len(times) > 1 and times[1][0] != times[0][0]:
            raw["end_time"] = times[1][0].strftime("%H:%M")

    # naslov, opis, lokacija
    cleaned = []
    for line in rest:
        c = _clean_line(line, today)
        if len(re.sub(r"\W", "", c)) >= 3 and not _GENERIC_HEADING.match(c):
            cleaned.append(c)
    title = labeled.get("title")
    desc_lines = cleaned
    if not title and cleaned:
        title = _PREAMBLE.sub("", cleaned[0]).strip()
        desc_lines = cleaned[1:]
        if "," in title:   # "Venčanje Ane i Marka, Hotel Moskva" -> naslov je prvi deo
            head, _, tail = title.partition(",")
            if len(head.strip()) >= 6:
                title = head.strip()
                desc_lines = [tail.strip()] + desc_lines
    if title:
        raw["title"] = _capitalize(title.strip())[:120]

    location = labeled.get("location", "")
    if not location:
        for line in cleaned:
            m = _LOC_RE.search(line)
            if m:
                location = _capitalize(m.group(1).strip(" ,.;"))
                break
        addr = next((m.group(1).strip() for l in cleaned for m in [_ADDR_RE.search(l)] if m), "")
        if addr and addr.lower() not in location.lower():
            location = f"{location}, {addr}" if location else addr
    if location:
        raw["location"] = location[:200]

    description = " ".join(d for d in desc_lines if d and d != raw.get("title"))
    if location:
        description = re.sub(re.escape(location), "", description, flags=re.I).strip(" ,;")
    if description:
        raw["description"] = description[:300]
    if notes:
        raw["notes"] = " ".join(notes)
    return raw


# --------------------------------------------------------------------------
# Slika -> polja (freeocr.ai)
# --------------------------------------------------------------------------

def _from_image(image: tuple[bytes, str], today: date) -> dict:
    data, media_type = image

    result = freeocr_client.post_json("extract", data, media_type, params={"fields": EXTRACT_FIELDS})
    values: dict[str, list[str]] = {}
    for item in result.get("result") or []:
        key = str(item.get("key", "")).strip().lower()
        vals = [cyr_to_lat(str(v)).strip() for v in (item.get("values") or []) if str(v).strip()]
        if key:
            values[key] = vals

    raw: dict = {}
    notes = []
    dates = [d for v in values.get("date", []) for d in find_dates(v, today)]
    if dates:
        raw["start_date"] = dates[0]["date"].isoformat()
        other = next((d["date"] for d in dates[1:] if d["date"] > dates[0]["date"]), None)
        if other:
            raw["end_date"] = other.isoformat()
        if dates[0]["inferred_year"]:
            notes.append(f"Godina nije navedena, pretpostavljena {dates[0]['date'].year}.")

    start = next((t for v in values.get("start_time", []) if (t := _time_from_field(v))), None)
    end = next((t for v in values.get("end_time", []) if (t := _time_from_field(v))), None)
    if start is None:   # vreme ponekad stoji uz datum, npr. "10.10.2026. u 18h"
        in_date = [t for v in values.get("date", []) for t, _, _ in find_times(_mask(v, [
            (d["start"], d["end"]) for d in find_dates(v, today)]))]
        start = in_date[0] if in_date else None
        end = end or (in_date[1] if len(in_date) > 1 and in_date[1] != in_date[0] else None)
    if start:
        raw["start_time"] = start.strftime("%H:%M")
    if end:
        raw["end_time"] = end.strftime("%H:%M")

    if values.get("title") and not _GENERIC_HEADING.match(values["title"][0]):   # "Pozivnica" nije naslov događaja
        raw["title"] = _capitalize(values["title"][0])[:120]
    if values.get("location"):
        raw["location"] = values["location"][0][:200]
    if values.get("details"):
        raw["description"] = " ".join(values["details"])[:300]
    if notes:
        raw["notes"] = " ".join(notes)

    if "start_date" not in raw or "title" not in raw:   # rezerva: ceo tekst sa slike, pa pravila
        ocr = freeocr_client.post_json("ocr", data, media_type, params={"format": "json"})
        raw = _merge(raw, _from_text(_strip_markdown(ocr.get("text") or ""), today))
    return raw


def _merge(primary: dict, fallback: dict) -> dict:
    """Popunjava samo polja koja nedostaju u primary. Beleške se spajaju."""
    merged = dict(primary)
    for key, value in fallback.items():
        if key == "notes":
            merged["notes"] = " ".join(n for n in (primary.get("notes"), value) if n)
        elif not merged.get(key):
            merged[key] = value
    return merged


# --------------------------------------------------------------------------
# Normalizacija i provera
# --------------------------------------------------------------------------

def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _parse_time(value) -> dtime | None:
    if not value or not isinstance(value, str):
        return None
    match = re.match(r"^\s*(\d{1,2}):(\d{2})", value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return dtime(hour, minute)


def normalize_event(raw: dict, now: datetime | None = None) -> dict:
    """Proverava polja i pretvara ih u događaj spreman za upis."""
    now = now or datetime.now(TZ)

    if raw.get("is_event") is False:
        raise ParseError(str(raw.get("notes") or "Ovo ne liči na pozivnicu za događaj.").strip())

    start_date = _parse_date(raw.get("start_date"))
    if not start_date:
        raise ParseError("Nisam uspeo da pronađem datum događaja. Dodaj ga u poruku, "
                         "npr. „sutra u 18h“ ili „10.10.2026. u 18h“.")

    title = str(raw.get("title") or "").strip() or "Događaj"
    notes = []
    if raw.get("notes"):
        notes.append(str(raw["notes"]).strip())

    start_time = _parse_time(raw.get("start_time"))
    end_date = _parse_date(raw.get("end_date"))
    end_time = _parse_time(raw.get("end_time"))
    end_assumed = False

    if start_time is None:
        # događaj celog dana; "end" je poslednji dan (uključivo)
        all_day = True
        notes.append("Vreme nije pronađeno, pa je događaj za ceo dan.")
        if end_date is None or end_date < start_date:
            end_date = start_date
        start_dt = datetime.combine(start_date, dtime.min, tzinfo=TZ)
        start_s, end_s = start_date.isoformat(), end_date.isoformat()
    else:
        all_day = False
        start_dt = datetime.combine(start_date, start_time, tzinfo=TZ)
        end_dt = None
        if end_time is not None:
            end_dt = datetime.combine(end_date or start_date, end_time, tzinfo=TZ)
            if end_dt <= start_dt:
                # npr. 22:00 - 01:00 bez navedenog datuma kraja: kraj je sledećeg dana
                if end_date is None and end_dt < start_dt:
                    end_dt += timedelta(days=1)
                else:
                    end_dt = None
        if end_dt is None:
            end_dt = start_dt + timedelta(hours=1)
            end_assumed = True
        start_s = start_dt.strftime("%Y-%m-%dT%H:%M")
        end_s = end_dt.strftime("%Y-%m-%dT%H:%M")

    if start_dt < now - timedelta(days=1):
        notes.append("Datum je u prošlosti, proveri godinu.")

    return {
        "title": title,
        "all_day": all_day,
        "start": start_s,
        "end": end_s,
        "location": str(raw.get("location") or "").strip(),
        "description": str(raw.get("description") or "").strip()[:500],
        "notes": " ".join(n for n in notes if n),
        "end_assumed": end_assumed,
    }


# --------------------------------------------------------------------------
# Javni ulaz
# --------------------------------------------------------------------------

def parse_event(text: str | None = None, image: tuple[bytes, str] | None = None) -> dict:
    """text: tekst pozivnice (ili opis uz sliku); image: (bajtovi, media_type)."""
    text = (text or "").strip()
    if not text and not image:
        raise ParseError("Nema ničega za parsiranje. Pošalji tekst ili sliku pozivnice.")
    if image:
        data, media_type = image
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ParseError("Format slike nije podržan (JPEG, PNG ili WEBP).")
        if len(data) > MAX_IMAGE_BYTES:
            raise ParseError("Slika je prevelika (najviše 5 MB).")

    today = datetime.now(TZ).date()
    try:
        raw = _from_image(image, today) if image else {}
    except FreeOCRError as e:
        if e.status is None:
            raise ParseError("OCR servis nije podešen na serveru (FREEOCR_API_KEY).") from None
        if e.status == 402:
            raise ParseError("OCR servis nema dovoljno kredita. Dopuni balans na freeocr.ai.") from None
        if e.status == 401:
            raise ParseError("OCR servis je odbio ključ (FREEOCR_API_KEY).") from None
        if e.status == 429:
            raise ParseError("OCR servis je trenutno preopterećen. Pokušaj za minut.") from None
        raise   # ostale greške idu u log, korisnik dobija opštu poruku
    if text:
        raw = _merge(raw, _from_text(text, today))   # opis uz sliku popunjava ono što na slici nedostaje
    return normalize_event(raw)
