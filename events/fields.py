"""
Pomoćnici za "sirova" polja događaja: rečnik sa ključevima title, start_date, start_time,
end_date, end_time, location, description, notes (vidi events/normalize.py).
Koriste ga čitanje teksta (events/text.py) i čitanje slike (events/image.py).
"""


def capitalize_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def merge_fields(primary: dict, fallback: dict) -> dict:
    """Popunjava samo polja koja nedostaju u primary. Beleške se spajaju."""
    merged = dict(primary)
    for key, value in fallback.items():
        if key == "notes":
            merged["notes"] = " ".join(n for n in (primary.get("notes"), value) if n)
        elif not merged.get(key):
            merged[key] = value
    return merged


def apply_dates(raw: dict, notes: list[str], dates: list[dict]) -> None:
    """
    Iz liste datuma (events/datetime_text.py, find_dates) upisuje datum početka, datum kraja (prvi
    kasniji različit datum, ako ga ima) i, ako godina nije bila navedena, napomenu o tome.
    """
    if not dates:
        return
    first = dates[0]
    raw["start_date"] = first["date"].isoformat()
    later = next((d["date"] for d in dates[1:] if d["date"] > first["date"]), None)
    if later:
        raw["end_date"] = later.isoformat()
    if first["inferred_year"]:
        notes.append(f"Godina nije navedena, pretpostavljena {first['date'].year}.")
