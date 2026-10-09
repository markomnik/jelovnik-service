"""
Telegram bot (Flask Blueprint): prima tekst ili sliku pozivnice, parsira je, pokazuje
predlog događaja sa dugmadima Da/Ne i na "Da" upisuje događaj u Google Calendar.

Endpoint:
    POST /telegram/webhook      (poziva ga Telegram; zaštićen secret_token zaglavljem)

Environment varijable:
    TELEGRAM_BOT_TOKEN          token od @BotFather
    TELEGRAM_WEBHOOK_SECRET     proizvoljan tajni string (A-Z a-z 0-9 _ -), isti kao u setWebhook
    TELEGRAM_ALLOWED_USER_IDS   ID-jevi korisnika kojima je dozvoljeno upisivanje, odvojeni zarezom
    TELEGRAM_ALLOWED_CHAT_IDS   (opciono) dodatno suzi bota na ove čatove; ako USER_IDS nije
                                podešen, važi samo ovaj spisak
    ANTHROPIC_API_KEY           za parsiranje pozivnica (vidi event_parser.py)

Registracija u app.py:
    from telegram_routes import telegram_bp
    app.register_blueprint(telegram_bp)

Napomena: čekajući predlozi se drže u memoriji procesa. Ako se servis restartuje
(deploy, uspavljivanje na besplatnom planu), nepotvrđeni predlozi se gube i korisnik
dobija poruku da ponovo pošalje pozivnicu.
"""

import hmac
import os
import re
import secrets
import time
from collections import deque
from datetime import datetime

import requests
from flask import Blueprint, current_app, jsonify, request

from calendar_routes import DAY_SHORT, create_event
from event_parser import ParseError, parse_event

telegram_bp = Blueprint("telegram", __name__)

API = "https://api.telegram.org"
PENDING_TTL_SECONDS = 2 * 60 * 60
MAX_PENDING = 200

_pending: dict[str, dict] = {}
_seen_updates: deque = deque(maxlen=500)   # Telegram ume da ponovi isti update (npr. dok se servis budi)

HELP_TEXT = (
    "Pošalji mi tekst ili sliku pozivnice. Izvući ću naslov, datum, vreme i lokaciju, "
    "pokazati ti predlog, a ti potvrdiš sa Da ili Ne. Na Da upisujem događaj u kalendar.\n\n"
    "Slika može da ima i opis (tekst ispod slike), npr. \"sutra u 18h\", ako na pozivnici nema datuma."
)


# --------------------------------------------------------------------------
# Telegram API
# --------------------------------------------------------------------------

def _token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _id_set(name: str) -> set[int]:
    raw = os.environ.get(name, "")
    return {int(x) for x in re.split(r"[,\s]+", raw) if re.fullmatch(r"-?\d+", x)}


def _is_authorized(chat_id: int | None, user_id: int | None) -> bool:
    """
    Da li korisnik sme da šalje pozivnice i potvrđuje upis u kalendar.

    TELEGRAM_ALLOWED_USER_IDS podešen:  korisnik mora da bude na spisku (a ako je podešen i
                                        TELEGRAM_ALLOWED_CHAT_IDS, i čat mora da bude na spisku).
    TELEGRAM_ALLOWED_USER_IDS prazan:   važi samo spisak čatova (TELEGRAM_ALLOWED_CHAT_IDS).
    """
    users = _id_set("TELEGRAM_ALLOWED_USER_IDS")
    chats = _id_set("TELEGRAM_ALLOWED_CHAT_IDS")
    if users:
        return user_id in users and (not chats or chat_id in chats)
    return chat_id in chats


def _tg(method: str, **payload) -> dict:
    """Poziva Telegram Bot API. Greške se loguju bez URL-a (u njemu je token bota)."""
    try:
        resp = requests.post(f"{API}/bot{_token()}/{method}", json=payload, timeout=20)
        if not resp.ok:
            current_app.logger.error("Telegram %s: HTTP %s %s", method, resp.status_code, resp.text[:300])
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        current_app.logger.error("Telegram %s nije uspeo: %s", method, type(e).__name__)
        return {}


def _send(chat_id: int, text: str, **extra) -> dict:
    return _tg("sendMessage", chat_id=chat_id, text=text,
               link_preview_options={"is_disabled": True}, **extra)


def _download_file(file_id: str) -> bytes:
    info = _tg("getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        raise ParseError("Nisam uspeo da preuzmem sliku sa Telegrama.")
    try:
        resp = requests.get(f"{API}/file/bot{_token()}/{path}", timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        raise ParseError("Nisam uspeo da preuzmem sliku sa Telegrama.") from None
    return resp.content


# --------------------------------------------------------------------------
# Predlog događaja
# --------------------------------------------------------------------------

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


def _purge_pending() -> None:
    cutoff = time.time() - PENDING_TTL_SECONDS
    for pid in [p for p, v in _pending.items() if v["ts"] < cutoff]:
        del _pending[pid]
    while len(_pending) >= MAX_PENDING:
        del _pending[min(_pending, key=lambda p: _pending[p]["ts"])]


def _store_pending(chat_id: int, event: dict) -> str:
    _purge_pending()
    pid = secrets.token_urlsafe(6)
    _pending[pid] = {"chat_id": chat_id, "event": event, "ts": time.time()}
    return pid


# --------------------------------------------------------------------------
# Obrada poruka
# --------------------------------------------------------------------------

def _handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    user_id = (msg.get("from") or {}).get("id")
    allowed = _is_authorized(chat_id, user_id)

    if command in ("/start", "/id"):
        ids = f"Tvoj korisnički ID: {user_id}\nID ovog čata: {chat_id}"
        if allowed:
            _send(chat_id, f"{HELP_TEXT}\n\n{ids}")
        else:
            _send(chat_id, f"{ids}\n\nDodaj korisnički ID u TELEGRAM_ALLOWED_USER_IDS na serveru "
                           "da bi ti bot dozvolio upisivanje.")
        return
    if not allowed:
        return  # ostalima se ne odgovara
    if text.startswith("/"):
        _send(chat_id, HELP_TEXT)
        return

    caption = (msg.get("caption") or text).strip()
    file_id, media_type = None, "image/jpeg"
    if msg.get("photo"):
        file_id = max(msg["photo"], key=lambda p: p.get("width", 0) * p.get("height", 0))["file_id"]
    elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
        file_id = msg["document"]["file_id"]
        media_type = msg["document"]["mime_type"]

    if not caption and not file_id:
        _send(chat_id, "Pošalji tekst ili sliku pozivnice.")
        return

    _tg("sendChatAction", chat_id=chat_id, action="typing")
    try:
        image = (_download_file(file_id), media_type) if file_id else None
        event = parse_event(text=caption, image=image)
    except ParseError as e:
        _send(chat_id, f"⚠️ {e}")
        return
    except Exception:
        current_app.logger.exception("Parsiranje pozivnice nije uspelo")
        _send(chat_id, "⚠️ Parsiranje trenutno nije uspelo. Pokušaj ponovo za koji minut.")
        return

    pid = _store_pending(chat_id, event)
    _send(chat_id, format_proposal(event, "Da li da upišem u kalendar?"),
          reply_markup={"inline_keyboard": [[
              {"text": "✅ Da", "callback_data": f"y:{pid}"},
              {"text": "❌ Ne", "callback_data": f"n:{pid}"},
          ]]})


def _handle_callback(cb: dict) -> None:
    cb_id = cb["id"]
    message = cb.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")

    if not _is_authorized(chat_id, (cb.get("from") or {}).get("id")):
        _tg("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
            text="Nemaš dozvolu za upisivanje u kalendar.")
        return

    action, _, pid = (cb.get("data") or "").partition(":")
    entry = _pending.get(pid)
    if action not in ("y", "n") or not entry or entry["chat_id"] != chat_id:
        _tg("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
            text="Predlog je istekao. Pošalji pozivnicu ponovo.")
        if message_id:
            _tg("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                reply_markup={"inline_keyboard": []})
        return

    event = entry["event"]
    if action == "n":
        del _pending[pid]
        _tg("answerCallbackQuery", callback_query_id=cb_id)
        _tg("editMessageText", chat_id=chat_id, message_id=message_id,
            text=format_proposal(event, "❌ Odbačeno, ništa nije upisano."))
        return

    del _pending[pid]   # pre upisa, da dvostruki klik ne napravi dva događaja
    try:
        created = create_event(event)
    except Exception as e:
        current_app.logger.exception("Upis događaja u kalendar nije uspeo")
        _pending[pid] = entry   # ostavi predlog, pa može ponovo
        forbidden = isinstance(e, requests.HTTPError) and getattr(e.response, "status_code", None) == 403
        _tg("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
            text=("Nema dozvolu za upis u kalendar. Ponovo izdaj token sa scope-om calendar.events."
                  if forbidden else "Upis u kalendar nije uspeo. Pokušaj ponovo."))
        return

    link = created.get("htmlLink", "")
    footer = "✅ Upisano u kalendar." + (f"\n{link}" if link else "")
    _tg("answerCallbackQuery", callback_query_id=cb_id)
    _tg("editMessageText", chat_id=chat_id, message_id=message_id,
        text=format_proposal(event, footer), link_preview_options={"is_disabled": True})


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------

@telegram_bp.route("/telegram/webhook", methods=["POST"])
def webhook():
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not (_token() and secret):
        return jsonify({"greska": "Telegram nije podešen na serveru."}), 503

    sent = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(sent.encode(), secret.encode()):
        return jsonify({"greska": "Zabranjeno."}), 403

    update = request.get_json(silent=True) or {}
    update_id = update.get("update_id")
    if update_id is not None:
        if update_id in _seen_updates:
            return jsonify({"ok": True})
        _seen_updates.append(update_id)

    try:
        if "callback_query" in update:
            _handle_callback(update["callback_query"])
        elif "message" in update:
            _handle_message(update["message"])
    except Exception:
        # uvek vraćamo 200, da Telegram ne bi ponavljao isti update
        current_app.logger.exception("Obrada Telegram update-a nije uspela")
    return jsonify({"ok": True})
