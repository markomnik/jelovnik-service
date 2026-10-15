"""Bezbednost: zaglavlja i CORS za sve odgovore, i zaštita admin endpointa tokenom."""

import hmac
import os
from functools import wraps

from flask import abort, request


def init_security(app) -> None:
    """Dodaje bezbednosna zaglavlja (uključujući CORS) svakom odgovoru."""

    @app.after_request
    def add_security_headers(resp):
        # ALLOWED_ORIGIN: po želji suzi na tačan origin stranice (podrazumevano *)
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("ALLOWED_ORIGIN", "*")
        resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        return resp


def require_admin(fn):
    """
    Štiti skupe/interne endpoint-e. Token se šalje kao ?token=... ili zaglavlje X-Admin-Token.
    Ako ADMIN_TOKEN nije podešen ili token ne odgovara, endpoint se ponaša kao da ne postoji (404).
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.environ.get("ADMIN_TOKEN")
        token = request.args.get("token") or request.headers.get("X-Admin-Token", "")
        # poredi se kao bajtovi, da token sa ne-ASCII znacima ne izazove grešku 500
        if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
            abort(404)
        return fn(*args, **kwargs)

    return wrapper
