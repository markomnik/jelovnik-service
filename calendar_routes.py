"""
Google Calendar endpointi (Flask Blueprint), izdvojeni iz app.py.

Endpointi:
    GET /calendar/next-days   -> događaji za danas + 3 naredna dana, grupisani po danu

Potrebne environment varijable (vrednosti daje get_refresh_token.py):
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    GOOGLE_REFRESH_TOKEN
    GOOGLE_CALENDAR_ID      (opciono, podrazumevano "primary")

Registracija u app.py:
    from calendar_routes import calendar_bp
    app.register_blueprint(calendar_bp)

Napomena: fajl se zove calendar_routes.py, a ne calendar.py, da ne bi zasenio
istoimeni modul iz Python standardne biblioteke.
"""

import os
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from flask import Blueprint, current_app, jsonify

calendar_bp = Blueprint("calendar", __name__)

TZ = ZoneInfo("Europe/Belgrade")
DAYS_AHEAD = 4                   # danas + 3 naredna dana
CACHE_TTL_SECONDS = 5 * 60       # koliko dugo čuvamo odgovor Google-a
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{cal}/events"
DAY_SHORT = ["Pon", "Uto", "Sre", "Čet", "Pet", "Sub", "Ned"]

_token = {"value": None, "exp": 0.0}
_cache = {"data": None, "ts": 0.0, "day": None}


def _check_google(resp: requests.Response, what: str) -> None:
    """Ako Google vrati grešku, upiši status i telo odgovora u log (tu piše pravi uzrok)."""
    if not resp.ok:
        current_app.logger.error("%s: HTTP %s %s", what, resp.status_code, resp.text[:500])
        resp.raise_for_status()


# --------------------------------------------------------------------------
# Autentikacija
# --------------------------------------------------------------------------

def _is_configured() -> bool:
    return all(os.environ.get(k) for k in
               ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"))


def _get_access_token() -> str:
    """Vraća važeći access token; osvežava ga preko refresh token-a kad istekne."""
    now = time.time()
    if _token["value"] and now < _token["exp"] - 60:
        return _token["value"]

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    _check_google(resp, "Google token request")
    data = resp.json()
    _token["value"] = data["access_token"]
    _token["exp"] = now + int(data.get("expires_in", 3600))
    return _token["value"]


# --------------------------------------------------------------------------
# Dohvatanje i obrada događaja
# --------------------------------------------------------------------------

def _fetch_events(window_start: datetime, window_end: datetime) -> list[dict]:
    # REST API vraća događaje pod ključem "items" (MCP konektor koristi "events").
    calendar_id = quote(os.environ.get("GOOGLE_CALENDAR_ID", "primary"), safe="")
    resp = requests.get(
        EVENTS_URL.format(cal=calendar_id),
        headers={"Authorization": f"Bearer {_get_access_token()}"},
        params={
            "timeMin": window_start.isoformat(),
            "timeMax": window_end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 100,
            "timeZone": "Europe/Belgrade",
        },
        timeout=15,
    )
    _check_google(resp, "Google Calendar events request")
    return resp.json().get("items", [])


def _event_bounds(ev: dict) -> tuple[datetime, datetime, bool]:
    """Vraća (početak, kraj, ceo_dan) u beogradskoj zoni."""
    start, end = ev.get("start", {}), ev.get("end", {})
    if "dateTime" in start:
        return (
            datetime.fromisoformat(start["dateTime"]).astimezone(TZ),
            datetime.fromisoformat(end["dateTime"]).astimezone(TZ),
            False,
        )
    # događaj za ceo dan: Google daje datume, a kraj je isključiv
    return (
        datetime.combine(date.fromisoformat(start["date"]), datetime.min.time(), tzinfo=TZ),
        datetime.combine(date.fromisoformat(end["date"]), datetime.min.time(), tzinfo=TZ),
        True,
    )


def _day_label(index: int, day: datetime) -> str:
    if index == 0:
        return "Danas"
    if index == 1:
        return "Sutra"
    return f"{DAY_SHORT[day.weekday()]} {day.day}.{day.month}."


def _build_days(today: datetime, raw_events: list[dict]) -> list[dict]:
    """Raspoređuje događaje po danima; događaj koji traje više dana pojavljuje se u svakom."""
    bounds = [(ev, *_event_bounds(ev)) for ev in raw_events]
    days = []
    for i in range(DAYS_AHEAD):
        day_start = today + timedelta(days=i)
        day_end = today + timedelta(days=i + 1)
        events = []
        for ev, ev_start, ev_end, all_day in bounds:
            starts_today = day_start <= ev_start < day_end
            overlaps = ev_start < day_end and (ev_end > day_start or starts_today)
            if not overlaps:
                continue
            events.append({
                "title": ev.get("summary") or "(bez naziva)",
                "location": ev.get("location", ""),
                "allDay": all_day,
                "time": "" if all_day or not starts_today else ev_start.strftime("%H:%M"),
                "continues": not all_day and not starts_today,
            })
        days.append({
            "date": day_start.date().isoformat(),
            "label": _day_label(i, day_start),
            "events": events,
        })
    return days


def _build_response() -> dict:
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = today + timedelta(days=DAYS_AHEAD)
    raw = _fetch_events(today, window_end)
    return {"generated": datetime.now(TZ).isoformat(), "days": _build_days(today, raw)}


# --------------------------------------------------------------------------
# Endpointi
# --------------------------------------------------------------------------

@calendar_bp.route("/calendar/next-days")
def next_days():
    if not _is_configured():
        return jsonify({"greska": "Kalendar nije podešen na serveru."}), 503

    now = time.time()
    today_key = datetime.now(TZ).date().isoformat()

    # keš važi samo dok traje isti dan, da se "Danas" pravilno promeni u ponoć
    if _cache["data"] and _cache["day"] == today_key and now - _cache["ts"] < CACHE_TTL_SECONDS:
        return jsonify(_cache["data"])

    try:
        data = _build_response()
    except Exception:
        current_app.logger.exception("Dohvatanje Google Calendar događaja nije uspelo")
        if _cache["data"] and _cache["day"] == today_key:
            return jsonify({**_cache["data"], "stale": True})
        return jsonify({"greska": "Kalendar trenutno nije dostupan."}), 502

    _cache.update(data=data, ts=now, day=today_key)
    return jsonify(data)
