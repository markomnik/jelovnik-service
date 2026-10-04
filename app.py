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
