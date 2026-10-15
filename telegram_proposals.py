"""
Predlozi događaja: tekst poruke sa predlogom i čuvanje predloga koji čekaju Da/Ne.

Predlozi se drže u memoriji procesa. Ako se servis restartuje (deploy, uspavljivanje na
besplatnom planu), nepotvrđeni predlozi se gube i korisnik dobija poruku da ponovo pošalje pozivnicu.
"""

import secrets
import time
from datetime import datetime

from config import DAY_SHORT

PENDING_TTL_SECONDS = 2 * 60 * 60
MAX_PENDING = 200

_pending: dict[str, dict] = {}


def _fmt_dt(iso: str, all_day: bool) -> str:
    d = datetime.fromisoformat(iso)
    day = f"{DAY_SHORT[d.weekday()]} {d.day:02d}.{d.month:02d}.{d.year}."
    return day if all_day else f"{day} {d:%H:%M}"


def format_proposal(event: dict, footer: str) -> str:
    lines = ["📅 Predlog događaja", "", f"Naslov: {event['title']}"]
    if event["all_day"]:
        lines.append(f"Datum: {_fmt_dt(event['start'], True)} (ceo dan)")
        if event["end"] != event["start"]:
            lines.append(f"Do: {_fmt_dt(event['end'], True)}")
    else:
        lines.append(f"Početak: {_fmt_dt(event['start'], False)}")
        end_line = f"Kraj: {_fmt_dt(event['end'], False)}"
        if event.get("end_assumed"):
            end_line += " (pretpostavljeno trajanje 1 sat)"
        lines.append(end_line)
    if event["location"]:
        lines.append(f"Lokacija: {event['location']}")
    if event["description"]:
        lines.append(f"Opis: {event['description']}")
    if event["notes"]:
        lines += ["", f"⚠️ Napomena: {event['notes']}"]
    lines += ["", footer]
    return "\n".join(lines)


def _purge() -> None:
    cutoff = time.time() - PENDING_TTL_SECONDS
    for pid in [p for p, v in _pending.items() if v["ts"] < cutoff]:
        del _pending[pid]
    while len(_pending) >= MAX_PENDING:
        del _pending[min(_pending, key=lambda p: _pending[p]["ts"])]


def add(chat_id: int, event: dict) -> str:
    _purge()
    pid = secrets.token_urlsafe(6)
    _pending[pid] = {"chat_id": chat_id, "event": event, "ts": time.time()}
    return pid


def get(pid: str) -> dict | None:
    return _pending.get(pid)


def remove(pid: str) -> None:
    del _pending[pid]


def restore(pid: str, entry: dict) -> None:
    """Vraća predlog (npr. kad upis u kalendar nije uspeo, pa korisnik može ponovo da klikne Da)."""
    _pending[pid] = entry


def has(pid: str) -> bool:
    return pid in _pending


def clear() -> None:
    _pending.clear()
