"""
Slika pozivnice -> polja događaja, preko freeocr.ai.

from_image(image, today):
  1. /extract izvuče naslov, datum, vreme, lokaciju i detalje
  2. ako datum ili naslov fale, /ocr pročita ceo tekst sa slike, pa se čita pravilima (event_text)
"""

from datetime import date

import freeocr_client
from event_datetime import find_dates, find_times, mask_spans, time_from_field
from event_fields import apply_dates, capitalize_first, merge_fields
from event_text import from_text, is_generic_heading, strip_markdown
from text_utils import cyr_to_lat


EXTRACT_FIELDS = ["title", "date", "start_time", "end_time", "location", "details"]


def from_image(image: tuple[bytes, str], today: date) -> dict:
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
    apply_dates(raw, notes, [d for v in values.get("date", []) for d in find_dates(v, today)])

    start = next((t for v in values.get("start_time", []) if (t := time_from_field(v))), None)
    end = next((t for v in values.get("end_time", []) if (t := time_from_field(v))), None)
    if start is None:   # vreme ponekad stoji uz datum, npr. "10.10.2026. u 18h"
        in_date = [t for v in values.get("date", []) for t, _, _ in find_times(mask_spans(v, [
            (d["start"], d["end"]) for d in find_dates(v, today)]))]
        start = in_date[0] if in_date else None
        end = end or (in_date[1] if len(in_date) > 1 and in_date[1] != in_date[0] else None)
    if start:
        raw["start_time"] = start.strftime("%H:%M")
    if end:
        raw["end_time"] = end.strftime("%H:%M")

    if values.get("title") and not is_generic_heading(values["title"][0]):   # "Pozivnica" nije naslov događaja
        raw["title"] = capitalize_first(values["title"][0])[:120]
    if values.get("location"):
        raw["location"] = values["location"][0][:200]
    if values.get("details"):
        raw["description"] = " ".join(values["details"])[:300]
    if notes:
        raw["notes"] = " ".join(notes)

    if "start_date" not in raw or "title" not in raw:   # rezerva: ceo tekst sa slike, pa pravila
        ocr = freeocr_client.post_json("ocr", data, media_type, params={"format": "json"})
        raw = merge_fields(raw, from_text(strip_markdown(ocr.get("text") or ""), today))
    return raw
