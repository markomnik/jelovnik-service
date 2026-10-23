"""
Obrada Telegram poruka i klikova na dugmad Da/Ne (poslovna logika bota).

handle_message(msg)     tekst ili slika pozivnice -> predlog sa dugmadima
handle_callback(cb)     klik na Da (upis u kalendar) ili Ne (odbacivanje)
"""

import requests
from flask import current_app

from events.errors import ParseError
from events.parser import parse_event
from google_calendar.routes import create_event
from telegram_bot import api as tg
from telegram_bot import proposals
from telegram_bot.api import TelegramError
from telegram_bot.auth import is_authorized

HELP_TEXT = (
    "Pošalji mi tekst ili sliku pozivnice. Izvući ću naslov, datum, vreme i lokaciju, "
    "pokazati ti predlog, a ti potvrdiš sa Da ili Ne. Na Da upisujem događaj u kalendar.\n\n"
    "Slika može da ima i opis (tekst ispod slike), npr. \"sutra u 18h\", ako na pozivnici nema datuma.\n\n"
    "Za tekst: datum piši kao 10.10.2026. ili \"sutra\", \"u subotu\", a vreme kao 18h ili 18:30. "
    "Lokaciju možeš da navedeš kao \"Mesto: ...\"."
)


def handle_message(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    user_id = (msg.get("from") or {}).get("id")
    allowed = is_authorized(chat_id, user_id)

    if command in ("/start", "/id"):
        ids = f"Tvoj korisnički ID: {user_id}\nID ovog čata: {chat_id}"
        if allowed:
            tg.send_message(chat_id, f"{HELP_TEXT}\n\n{ids}")
        else:
            tg.send_message(chat_id, f"{ids}\n\nDodaj korisnički ID u TELEGRAM_ALLOWED_USER_IDS na serveru "
                            "da bi ti bot dozvolio upisivanje.")
        return
    if not allowed:
        return  # ostalima se ne odgovara
    if text.startswith("/"):
        tg.send_message(chat_id, HELP_TEXT)
        return

    caption = (msg.get("caption") or text).strip()
    file_id, media_type = None, "image/jpeg"
    if msg.get("photo"):
        file_id = max(msg["photo"], key=lambda p: p.get("width", 0) * p.get("height", 0))["file_id"]
    elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
        file_id = msg["document"]["file_id"]
        media_type = msg["document"]["mime_type"]

    if not caption and not file_id:
        tg.send_message(chat_id, "Pošalji tekst ili sliku pozivnice.")
        return

    tg.call("sendChatAction", chat_id=chat_id, action="typing")
    try:
        image = (tg.download_file(file_id), media_type) if file_id else None
        event = parse_event(text=caption, image=image)
    except (ParseError, TelegramError) as e:
        tg.send_message(chat_id, f"⚠️ {e}")
        return
    except Exception:
        current_app.logger.exception("Parsiranje pozivnice nije uspelo")
        tg.send_message(chat_id, "⚠️ Parsiranje trenutno nije uspelo. Pokušaj ponovo za koji minut.")
        return

    pid = proposals.add(chat_id, event)
    tg.send_message(chat_id, proposals.format_proposal(event, "Da li da upišem u kalendar?"),
                    reply_markup={"inline_keyboard": [[
                        {"text": "✅ Da", "callback_data": f"y:{pid}"},
                        {"text": "❌ Ne", "callback_data": f"n:{pid}"},
                    ]]})


def handle_callback(cb: dict) -> None:
    cb_id = cb["id"]
    message = cb.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")

    if not is_authorized(chat_id, (cb.get("from") or {}).get("id")):
        tg.call("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
                text="Nemaš dozvolu za upisivanje u kalendar.")
        return

    action, _, pid = (cb.get("data") or "").partition(":")
    entry = proposals.get(pid)
    if action not in ("y", "n") or not entry or entry["chat_id"] != chat_id:
        tg.call("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
                text="Predlog je istekao. Pošalji pozivnicu ponovo.")
        if message_id:
            tg.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                    reply_markup={"inline_keyboard": []})
        return

    event = entry["event"]
    if action == "n":
        proposals.remove(pid)
        tg.call("answerCallbackQuery", callback_query_id=cb_id)
        tg.call("editMessageText", chat_id=chat_id, message_id=message_id,
                text=proposals.format_proposal(event, "❌ Odbačeno, ništa nije upisano."))
        return

    proposals.remove(pid)   # pre upisa, da dvostruki klik ne napravi dva događaja
    try:
        created = create_event(event)
    except Exception as e:
        current_app.logger.exception("Upis događaja u kalendar nije uspeo")
        proposals.restore(pid, entry)   # ostavi predlog, pa može ponovo
        forbidden = isinstance(e, requests.HTTPError) and getattr(e.response, "status_code", None) == 403
        tg.call("answerCallbackQuery", callback_query_id=cb_id, show_alert=True,
                text=("Nema dozvolu za upis u kalendar. Ponovo izdaj token sa scope-om calendar.events."
                      if forbidden else "Upis u kalendar nije uspeo. Pokušaj ponovo."))
        return

    link = created.get("htmlLink", "")
    footer = "✅ Upisano u kalendar." + (f"\n{link}" if link else "")
    tg.call("answerCallbackQuery", callback_query_id=cb_id)
    tg.call("editMessageText", chat_id=chat_id, message_id=message_id,
            text=proposals.format_proposal(event, footer), link_preview_options={"is_disabled": True})
