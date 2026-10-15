"""
Info ekran - pozadinski servis (Flask).

Ovaj fajl samo sastavlja aplikaciju; sva logika je u modulima:
    menu_routes.py      jelovnik vrtića (/jelovnik/vrtic*), uz menu_scraper, menu_table, menu_service
    calendar_routes.py  Google Calendar (/calendar/next-days)
    telegram_routes.py  Telegram bot (/telegram/webhook), uz telegram_handlers, telegram_proposals,
                        telegram_auth, telegram_api i event_parser (event_text, event_image, ...)
    admin_routes.py     health (/) i dijagnostika (/debug, /debug-ocr)
    security.py         zaglavlja/CORS i zaštita admin endpointa
    extensions.py       limiter (ograničenje broja zahteva)
    freeocr_client.py   klijent za freeocr.ai, deli ga jelovnik i bot
    config.py           vremenska zona i nazivi dana

Pokretanje lokalno:
    pip install -r requirements.txt
    python3 app.py            # zatim http://localhost:8000/jelovnik/vrtic

Na Render-u: gunicorn app:app --timeout 120 (vidi DEPLOY.md).
"""

from flask import Flask

from admin_routes import admin_bp
from calendar_routes import calendar_bp
from extensions import limiter
from menu_routes import menu_bp
from security import init_security
from telegram_routes import telegram_bp


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
