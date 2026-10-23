"""Provera i normalizacija polja događaja pre upisa u kalendar."""

import re
from datetime import date, datetime, time as dtime, timedelta

from core.config import TZ
from events.errors import ParseError


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
