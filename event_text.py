"""
Tekst pozivnice -> polja događaja (pravila, bez AI-ja).

from_text(text, today) vraća rečnik u formi koju razume event_normalize.normalize_event():
    title, start_date, start_time, end_date, end_time, location, description, notes
Sav tekst se pretvara u latinicu.
"""

import re
from datetime import date

from event_datetime import find_dates, find_times, mask_spans, relative_date_spans
from event_fields import apply_dates, capitalize_first
from text_utils import cyr_to_lat


_LABEL = re.compile(
    r"^(?P<key>naslov|povod|dogadjaj|događaj|event|title|mesto|lokacija|adresa|gde|place|where|venue|location|"
    r"datum|date|kada|when|vreme|time|pocetak|početak)\s*[:\-–]\s*(?P<val>.+)$", re.I)


_LABEL_KIND = {"naslov": "title", "povod": "title", "dogadjaj": "title", "događaj": "title", "event": "title",
               "title": "title", "mesto": "location", "lokacija": "location", "adresa": "location",
               "gde": "location", "place": "location", "where": "location", "venue": "location",
               "location": "location"}


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
    spans += relative_date_spans(line)
    spans += [(s, e) for _, s, e in find_times(mask_spans(line, spans))]
    return _strip_spans(line, spans)


def strip_markdown(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[#*_`>|]", " ", text)


def from_text(text: str, today: date) -> dict:
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
    apply_dates(raw, notes, dates)
    if dates and dates[0]["rel"]:
        notes.append(f"Datum izveden iz reči „{dates[0]['rel']}“.")
    times = find_times(mask_spans(whole, [(d["start"], d["end"]) for d in dates]))
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
        raw["title"] = capitalize_first(title.strip())[:120]

    location = labeled.get("location", "")
    if not location:
        for line in cleaned:
            m = _LOC_RE.search(line)
            if m:
                location = capitalize_first(m.group(1).strip(" ,.;"))
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


def is_generic_heading(text: str) -> bool:
    """Naslovi poput "Pozivnica" ili "Save the date" nisu naslov događaja."""
    return bool(_GENERIC_HEADING.match(text))
