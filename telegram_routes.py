"""
Telegram bot (Flask Blueprint): prima tekst ili sliku pozivnice, parsira je, pokazuje
predlog događaja sa dugmadima Da/Ne i na "Da" upisuje događaj u Google Calendar.

Endpoint:
    POST /telegram/webhook      (poziva ga Telegram; zaštićen secret_token zaglavljem)

Ovaj modul samo prima i proverava zahtev; ostalo je u:
    telegram_handlers.py   obrada poruka i klikova (poslovna logika)
    telegram_proposals.py  tekst predloga i predlozi koji čekaju potvrdu
    telegram_auth.py       ko sme da koristi bota
    telegram_api.py        pozivi ka Telegram Bot API-ju
    event_parser.py        pozivnica -> parametri događaja

Environment varijable:
    TELEGRAM_BOT_TOKEN          token od @BotFather
    TELEGRAM_WEBHOOK_SECRET     proizvoljan tajni string (A-Z a-z 0-9 _ -), isti kao u setWebhook
    TELEGRAM_ALLOWED_USER_IDS   ID-jevi korisnika kojima je dozvoljeno upisivanje, odvojeni zarezom
    TELEGRAM_ALLOWED_CHAT_IDS   (opciono) dodatno suzi bota na ove čatove; ako USER_IDS nije
                                podešen, važi samo ovaj spisak
    FREEOCR_API_KEY             za čitanje slika pozivnica (vidi freeocr_client.py)

Blueprint se registruje u app.create_app().
"""

import hmac
import os
from collections import deque

from flask import Blueprint, current_app, jsonify, request

import telegram_api
import telegram_handlers

telegram_bp = Blueprint("telegram", __name__)

_seen_updates: deque = deque(maxlen=500)   # Telegram ume da ponovi isti update (npr. dok se servis budi)


@telegram_bp.route("/telegram/webhook", methods=["POST"])
def webhook():
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not (telegram_api.token() and secret):
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
            telegram_handlers.handle_callback(update["callback_query"])
        elif "message" in update:
            telegram_handlers.handle_message(update["message"])
    except Exception:
        # uvek vraćamo 200, da Telegram ne bi ponavljao isti update
        current_app.logger.exception("Obrada Telegram update-a nije uspela")
    return jsonify({"ok": True})
