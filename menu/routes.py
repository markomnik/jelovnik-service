"""Rute jelovnika vrtića (Flask Blueprint)."""

from datetime import datetime

from flask import Blueprint, abort, jsonify, redirect

from core.config import DAYS, TZ
from menu import service as menu_service

menu_bp = Blueprint("menu", __name__)

NOT_FOUND = "Jelovnik trenutno nije pronađen na sajtu."


@menu_bp.route("/jelovnik/vrtic")
def jelovnik_vrtic():
    """Preusmerava (302) na sliku jelovnika."""
    url = menu_service.resolve_cached_url()
    if not url:
        abort(404, description=NOT_FOUND)
    return redirect(url, code=302)


@menu_bp.route("/jelovnik/vrtic/danas")
def jelovnik_vrtic_danas():
    """Jela za današnji dan, pročitana sa slike."""
    url = menu_service.resolve_cached_url()
    if not url:
        return jsonify({"greska": NOT_FOUND}), 404

    # Server (Render) radi po UTC-u, a dan treba da se menja po srpskoj ponoći,
    # ne po UTC ponoći - zato eksplicitno računamo po Europe/Belgrade zoni.
    weekday_idx = datetime.now(TZ).weekday()   # 0=Pon ... 6=Ned
    dan = DAYS[weekday_idx]

    if weekday_idx >= 5:   # Subota / Nedelja
        return jsonify({"dan": dan, "poruka": "Vrtić ne radi vikendom."})

    try:
        table = menu_service.resolve_cached_table(url)
    except Exception as e:
        return jsonify({"dan": dan, "greska": f"AI čitanje jelovnika nije uspelo: {e}"}), 502

    obrok = (table or {}).get(dan)
    if not obrok:
        return jsonify({"dan": dan, "greska": "Dan nije pronađen u pročitanoj tabeli."}), 502

    return jsonify({
        "dan": dan,
        "dorucak": obrok.get("dorucak", ""),
        "voce": obrok.get("voce", ""),
        "uzina": obrok.get("uzina", ""),
        "rucak": obrok.get("rucak", ""),
    })


@menu_bp.route("/jelovnik/vrtic/nedelja")
def jelovnik_vrtic_nedelja():
    """Cela nedeljna tabela."""
    url = menu_service.resolve_cached_url()
    if not url:
        return jsonify({"greska": NOT_FOUND}), 404
    try:
        table = menu_service.resolve_cached_table(url)
    except Exception as e:
        return jsonify({"greska": f"AI čitanje jelovnika nije uspelo: {e}"}), 502
    return jsonify(table)
