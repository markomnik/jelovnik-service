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

import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from flask import Flask, redirect, abort

app = Flask(__name__)

BASE_URL = "https://www.pudecjidani.rs/"
LINK_TEXT = "Јеловник"
IMG_HINT = "Вртић"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6h - dovoljno sveže, a ne davi sajt

_cache = {"url": None, "ts": 0}


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


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
    for src in parser.imgs:
        if IMG_HINT in src:
            return urljoin(page_url, src)
    return None


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


@app.route("/")
def health():
    return {"status": "ok", "cached_url": _cache["url"]}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
