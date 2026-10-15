"""Tanak klijent za Telegram Bot API (bez poslovne logike bota)."""

import os

import requests
from flask import current_app

API = "https://api.telegram.org"


class TelegramError(Exception):
    """Greška čija se poruka sme prikazati korisniku."""


def token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def call(method: str, **payload) -> dict:
    """Poziva Telegram Bot API. Greške se loguju bez URL-a (u njemu je token bota)."""
    try:
        resp = requests.post(f"{API}/bot{token()}/{method}", json=payload, timeout=20)
        if not resp.ok:
            current_app.logger.error("Telegram %s: HTTP %s %s", method, resp.status_code, resp.text[:300])
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        current_app.logger.error("Telegram %s nije uspeo: %s", method, type(e).__name__)
        return {}


def send_message(chat_id: int, text: str, **extra) -> dict:
    return call("sendMessage", chat_id=chat_id, text=text,
               link_preview_options={"is_disabled": True}, **extra)


def download_file(file_id: str) -> bytes:
    info = call("getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        raise TelegramError("Nisam uspeo da preuzmem sliku sa Telegrama.")
    try:
        resp = requests.get(f"{API}/file/bot{token()}/{path}", timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        raise TelegramError("Nisam uspeo da preuzmem sliku sa Telegrama.") from None
    return resp.content
