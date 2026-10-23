"""Jelovnik: pronalaženje slike i čitanje tabele, uz keš u memoriji procesa."""

import logging
import time

from menu.scraper import download_image_bytes, find_vrtic_image_url
from menu.table import extract_menu_table

CACHE_TTL_SECONDS = 6 * 60 * 60               # koliko često proveravamo da li je URL slike promenjen
TABLE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60    # tabela se menja samo jednom nedeljno

log = logging.getLogger(__name__)

_cache = {"url": None, "ts": 0, "table": None, "table_ts": 0, "table_for_url": None}


def cached_url() -> str | None:
    """Poslednji pronađeni URL slike (bez ikakvog dohvatanja), za health proveru."""
    return _cache["url"]


def reset_cache() -> None:
    _cache.update(url=None, ts=0, table=None, table_ts=0, table_for_url=None)


def resolve_cached_url() -> str | None:
    now = time.time()
    if _cache["url"] and (now - _cache["ts"]) < CACHE_TTL_SECONDS:
        return _cache["url"]

    try:
        url = find_vrtic_image_url()
    except Exception:
        # sajt vrtića nije dostupan: ne rušimo zahtev, nego koristimo stari URL ako ga imamo
        log.exception("Dohvatanje slike jelovnika sa sajta vrtića nije uspelo")
        url = None
    if url:
        _cache["url"] = url
        _cache["ts"] = now
        return url

    # scraping nije uspeo ovog puta (greška ili nema linka) - vrati stari keširani URL ako postoji,
    # bolje stara slika nego ništa
    return _cache["url"]


def resolve_cached_table(image_url: str) -> dict | None:
    now = time.time()
    fresh = (
        _cache["table"] is not None
        and _cache["table_for_url"] == image_url
        and (now - _cache["table_ts"]) < TABLE_CACHE_TTL_SECONDS
    )
    if fresh:
        return _cache["table"]

    table = extract_menu_table(download_image_bytes(image_url))
    _cache["table"] = table
    _cache["table_ts"] = now
    _cache["table_for_url"] = image_url
    return table
