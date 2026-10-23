"""
Info ekran - pozadinski servis (Flask).

Ovaj fajl samo sastavlja aplikaciju; sva logika je u folderima:
    menu/             jelovnik vrtića: /jelovnik/vrtic* (scraper, table, service, routes)
    google_calendar/  Google Calendar: /calendar/next-days i upis događaja
    telegram_bot/     Telegram bot: /telegram/webhook (api, auth, proposals, handlers, routes)
    events/           pozivnica (tekst ili slika) -> parametri događaja
    admin/            health (/) i dijagnostika (/debug, /debug-ocr)
    core/             konfiguracija, limiter, bezbednost, tekst, klijent za freeocr.ai
    scripts/          jednokratne skripte (Google token)
    tests/            automatski testovi

Pokretanje lokalno:
    pip install -r requirements.txt
    python3 app.py            # zatim http://localhost:8000/jelovnik/vrtic

Na Render-u: gunicorn app:app --timeout 120 (vidi DEPLOY.md).
"""

from flask import Flask

from admin.routes import admin_bp
from core.extensions import limiter
from core.security import init_security
from google_calendar.routes import calendar_bp
from menu.routes import menu_bp
from telegram_bot.routes import telegram_bp


def create_app(config: dict | None = None) -> Flask:
    """Sastavlja aplikaciju. config (opciono) se primenjuje pre ekstenzija, npr. {"RATELIMIT_ENABLED": False}."""
    app = Flask(__name__)
    app.config.update(config or {})
    init_security(app)
    limiter.init_app(app)
    limiter.exempt(telegram_bp)   # pozivi dolaze sa Telegram IP adresa; štiti ih secret_token zaglavlje
    for blueprint in (menu_bp, admin_bp, calendar_bp, telegram_bp):
        app.register_blueprint(blueprint)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
