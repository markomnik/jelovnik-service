"""
Mali web servis (Flask) koji:
  1. Otvori https://www.pudecjidani.rs/ i nađe link čiji je tekst "Јеловник"
  2. Otvori tu ciljnu stranicu i nađe <img> čiji URL sadrži "Вртић"
  3. Redirect-uje (302) na taj URL slike

Rezultat kešira u memoriji nekoliko sati, da ne opterećujemo sajt
pri svakom otvaranju naše stranice.

Pokretanje lokalno:
    pip install flask
    python3 app.py
    # zatim otvori http://localhost:8000/jelovnik/vrtic

Deploy: vidi DEPLOY.md
"""

import base64
import json
import os
import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin

import requests
from flask import Flask, redirect, abort, jsonify

app = Flask(__name__)

BASE_URL = "https://www.pudecjidani.rs/"
LINK_TEXT = "Јеловник"
IMG_HINT = "Вртић"
CACHE_TTL_SECONDS = 6 * 60 * 60       # 6h - koliko često proveravamo da li je URL slike promenjen
TABLE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 dana - tabela se menja samo jednom nedeljno

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

# OCR_PROVIDER: "anthropic" (podrazumevano) ili "freeai"
OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "anthropic").lower()
FREE_AI_API_KEY = os.environ.get("FREE_AI_API_KEY")

DANI = ["Ponedeljak", "Utorak", "Sreda", "Četvrtak", "Petak", "Subota", "Nedelja"]

_cache = {"url": None, "ts": 0, "table": None, "table_ts": 0, "table_for_url": None}


class LinkFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []


class ImgFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            a = dict(attrs)
            src = a.get("src") or a.get("data-src")
            if src:
                self.imgs.append(src)


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.pudecjidani.rs/",
}


def fetch_html(url: str) -> str:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=15) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def find_jelovnik_page_url() -> str | None:
    html = fetch_html(BASE_URL)
    parser = LinkFinder()
    parser.feed(html)
    for href, text in parser.links:
        if text == LINK_TEXT and href:
            return urljoin(BASE_URL, href)
    for href, text in parser.links:
        if LINK_TEXT in text and href:
            return urljoin(BASE_URL, href)
    return None


def find_vrtic_image_url() -> str | None:
    page_url = find_jelovnik_page_url()
    if not page_url:
        return None
    html = fetch_html(page_url)
    parser = ImgFinder()
    parser.feed(html)
    hint_lower = IMG_HINT.lower()
    for src in parser.imgs:
        if hint_lower in src.lower():
            return urljoin(page_url, src)
    return None


def download_image_bytes(url: str) -> bytes:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=20) as resp:
        return resp.read()


def extract_menu_table(image_bytes: bytes) -> dict:
    """Dispečer: šalje sliku odabranom OCR provajderu i vraća {"Ponedeljak": {...}, ...}."""
    if OCR_PROVIDER == "freeai":
        return extract_menu_table_freeai(image_bytes)
    return extract_menu_table_anthropic(image_bytes)


DAN_HINTS = {
    "ponedeljak": "Ponedeljak", "понедељак": "Ponedeljak",
    "utorak": "Utorak", "уторак": "Utorak",
    "sreda": "Sreda", "среда": "Sreda",
    "cetvrtak": "Četvrtak", "četvrtak": "Četvrtak", "четвртак": "Četvrtak",
    "petak": "Petak", "петак": "Petak",
}
OBROK_HINTS = {
    "dorucak": "dorucak", "doručak": "dorucak", "доручак": "dorucak",
    "voce": "voce", "voće": "voce", "воће": "voce",
    "uzina": "uzina", "užina": "uzina", "ужина": "uzina",
    "rucak": "rucak", "ručak": "rucak", "ручак": "rucak",
}


def _match_hint(label: str, hints: dict) -> str | None:
    low = (label or "").strip().lower()
    for key, val in hints.items():
        if key in low:
            return val
    return None


def _grid_to_menu(grid: list[list[str]]) -> dict:
    """
    Pretvara generičku tabelu (lista redova, svaki red lista ćelija) u naš oblik,
    bez obzira da li su dani u header redu ili header koloni.
    """
    if not grid or len(grid) < 2:
        raise ValueError("Tabela iz OCR odgovora je prazna ili prekratka.")

    header_row = grid[0]
    header_col = [row[0] if row else "" for row in grid]

    days_in_row = {i: _match_hint(c, DAN_HINTS) for i, c in enumerate(header_row)}
    days_in_col = {i: _match_hint(c, DAN_HINTS) for i, c in enumerate(header_col)}
    meals_in_row = {i: _match_hint(c, OBROK_HINTS) for i, c in enumerate(header_row)}
    meals_in_col = {i: _match_hint(c, OBROK_HINTS) for i, c in enumerate(header_col)}

    days_found_in_row = any(v for v in days_in_row.values())
    meals_found_in_col = any(v for v in meals_in_col.values())

    result = {d: {"dorucak": "", "voce": "", "uzina": "", "rucak": ""} for d in
              ["Ponedeljak", "Utorak", "Sreda", "Četvrtak", "Petak"]}

    if days_found_in_row and meals_found_in_col:
        # dani su kolone (header red), obroci su redovi (header kolona)
        for r_idx, row in enumerate(grid):
            meal = meals_in_col.get(r_idx)
            if not meal:
                continue
            for c_idx, cell in enumerate(row):
                day = days_in_row.get(c_idx)
                if day:
                    result[day][meal] = (cell or "").strip()
        return result

    # obrnuto: dani su redovi (header kolona), obroci su kolone (header red)
    days_found_in_col = any(v for v in days_in_col.values())
    meals_found_in_row = any(v for v in meals_in_row.values())
    if days_found_in_col and meals_found_in_row:
        for r_idx, row in enumerate(grid):
            day = days_in_col.get(r_idx)
            if not day:
                continue
            for c_idx, cell in enumerate(row):
                meal = meals_in_row.get(c_idx)
                if meal:
                    result[day][meal] = (cell or "").strip()
        return result

    raise ValueError("Nisam uspeo da prepoznam raspored dana/obroka u OCR tabeli.")


def extract_menu_table_freeai(image_bytes: bytes) -> dict:
    """Šalje sliku Free.ai Table OCR API-ju i mapira generičku tabelu na naš oblik."""
    if not FREE_AI_API_KEY:
        raise RuntimeError("FREE_AI_API_KEY nije podešen u environment varijablama.")

    b64 = base64.b64encode(image_bytes).decode("ascii")

    resp = requests.post(
        "https://api.free.ai/v1/ocr/",
        headers={
            "Authorization": f"Bearer {FREE_AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "image": f"data:image/jpeg;base64,{b64}",
            "language": "auto",
            "output_format": "json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    # Pokušaj da nađemo listu redova u odgovoru pod nekoliko mogućih ključeva -
    # tačna šema Free.ai odgovora nije bila javno dokumentovana u trenutku pisanja,
    # pa /debug-ocr endpoint postoji da bismo videli stvarni oblik i doterali ovo.
    grid = None
    for key in ("table", "tables", "rows", "data", "cells", "result"):
        val = data.get(key) if isinstance(data, dict) else None
        if isinstance(val, list) and val:
            # ako je "tables": [[[...]]] (lista tabela), uzmi prvu
            if isinstance(val[0], list) and val[0] and isinstance(val[0][0], list):
                grid = val[0]
            else:
                grid = val
            break

    if grid is None:
        raise ValueError(f"Nisam prepoznao oblik Free.ai odgovora. Sirov odgovor: {json.dumps(data)[:500]}")

    return _grid_to_menu(grid)


def extract_menu_table_anthropic(image_bytes: bytes) -> dict:
    """Šalje sliku Anthropic API-ju i vraća tabelu kao dict: {"Ponedeljak": {...}, ...}."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY nije podešen u environment varijablama.")

    b64 = base64.b64encode(image_bytes).decode("ascii")

    prompt = (
        "Ovo je slika jelovnika za vrtić, organizovana kao tabela sa danima u nedelji "
        "(Ponedeljak–Petak) i obrocima (doručak, voće, užina, ručak). "
        "Pročitaj tekst iz tabele i vrati ISKLJUČIVO JSON, bez ikakvog drugog teksta, "
        "bez markdown ograda, u sledećem obliku:\n"
        '{"Ponedeljak":{"dorucak":"...","voce":"...","uzina":"...","rucak":"..."},'
        '"Utorak":{...},"Sreda":{...},"Četvrtak":{...},"Petak":{...}}\n'
        'Ako neko polje nije čitljivo ili ne postoji, stavi praznu vrednost "".'
    )

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1500,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = text.strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:].strip()
    return json.loads(text)


def resolve_cached_table(image_url: str) -> dict | None:
    now = time.time()
    fresh = (
        _cache["table"] is not None
        and _cache["table_for_url"] == image_url
        and (now - _cache["table_ts"]) < TABLE_CACHE_TTL_SECONDS
    )
    if fresh:
        return _cache["table"]

    img_bytes = download_image_bytes(image_url)
    table = extract_menu_table(img_bytes)
    _cache["table"] = table
    _cache["table_ts"] = now
    _cache["table_for_url"] = image_url
    return table


def resolve_cached_url() -> str | None:
    now = time.time()
    if _cache["url"] and (now - _cache["ts"]) < CACHE_TTL_SECONDS:
        return _cache["url"]

    url = find_vrtic_image_url()
    if url:
        _cache["url"] = url
        _cache["ts"] = now
        return url

    # scraping nije uspeo ovog puta - vrati stari keširani URL ako postoji,
    # bolje stara slika nego ništa
    return _cache["url"]


@app.route("/jelovnik/vrtic")
def jelovnik_vrtic():
    url = resolve_cached_url()
    if not url:
        abort(404, description="Jelovnik trenutno nije pronađen na sajtu.")
    return redirect(url, code=302)


@app.route("/jelovnik/vrtic/danas")
def jelovnik_vrtic_danas():
    url = resolve_cached_url()
    if not url:
        return jsonify({"greska": "Jelovnik trenutno nije pronađen na sajtu."}), 404

    weekday_idx = time.localtime().tm_wday  # 0=Pon ... 6=Ned
    dan = DANI[weekday_idx]

    if weekday_idx >= 5:  # Subota / Nedelja
        return jsonify({"dan": dan, "poruka": "Vrtić ne radi vikendom."})

    try:
        table = resolve_cached_table(url)
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


@app.route("/jelovnik/vrtic/nedelja")
def jelovnik_vrtic_nedelja():
    """Cela nedeljna tabela, za slučaj da zatreba i to."""
    url = resolve_cached_url()
    if not url:
        return jsonify({"greska": "Jelovnik trenutno nije pronađen na sajtu."}), 404
    try:
        table = resolve_cached_table(url)
    except Exception as e:
        return jsonify({"greska": f"AI čitanje jelovnika nije uspelo: {e}"}), 502
    return jsonify(table)


@app.route("/")
def health():
    return {"status": "ok", "cached_url": _cache["url"]}


@app.route("/debug-ocr")
def debug_ocr():
    """Prikazuje sirov odgovor OCR provajdera i rezultat mapiranja, za dijagnostiku."""
    url = resolve_cached_url()
    if not url:
        return jsonify({"greska": "Jelovnik slika trenutno nije pronađena."}), 404

    out = {"provider": OCR_PROVIDER, "image_url": url}
    try:
        img_bytes = download_image_bytes(url)
        if OCR_PROVIDER == "freeai":
            if not FREE_AI_API_KEY:
                return jsonify({"greska": "FREE_AI_API_KEY nije podešen."}), 500
            b64 = base64.b64encode(img_bytes).decode("ascii")
            resp = requests.post(
                "https://api.free.ai/v1/ocr/",
                headers={"Authorization": f"Bearer {FREE_AI_API_KEY}", "Content-Type": "application/json"},
                json={"image": f"data:image/jpeg;base64,{b64}", "language": "auto", "output_format": "json"},
                timeout=60,
            )
            out["status_code"] = resp.status_code
            out["raw_response"] = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:2000]
            try:
                out["mapped"] = extract_menu_table_freeai(img_bytes)
            except Exception as e:
                out["mapping_error"] = str(e)
        else:
            out["mapped"] = extract_menu_table_anthropic(img_bytes)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return jsonify(out)


@app.route("/debug")
def debug():
    """Pokazuje šta server stvarno vidi — korisno za dijagnostiku ako scraping ne uspe."""
    out = {"base_url": BASE_URL}
    try:
        html = fetch_html(BASE_URL)
        out["homepage_len"] = len(html)
        parser = LinkFinder()
        parser.feed(html)
        out["homepage_link_count"] = len(parser.links)
        # svi linkovi čiji tekst sadrži bilo šta slično "Јеловник" (case-insensitive, širi filter)
        out["links_sample"] = [t for (h, t) in parser.links if t][:40]
        jelovnik_url = None
        for href, text in parser.links:
            if text == LINK_TEXT and href:
                jelovnik_url = urljoin(BASE_URL, href)
                break
        if not jelovnik_url:
            for href, text in parser.links:
                if LINK_TEXT in text and href:
                    jelovnik_url = urljoin(BASE_URL, href)
                    break
        out["jelovnik_page_url"] = jelovnik_url

        if jelovnik_url:
            page_html = fetch_html(jelovnik_url)
            out["jelovnik_page_len"] = len(page_html)
            img_parser = ImgFinder()
            img_parser.feed(page_html)
            out["img_srcs"] = img_parser.imgs[:40]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
