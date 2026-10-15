"""Pronalaženje slike jelovnika na sajtu vrtića (scraping)."""

from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

BASE_URL = "https://www.pudecjidani.rs/"
LINK_TEXT = "Јеловник"   # tekst linka na početnoj strani (ćirilica)
IMG_HINT = "Вртић"       # deo imena fajla slike (poredi se bez obzira na velika/mala slova)

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
    "Referer": BASE_URL,
}


class LinkFinder(HTMLParser):
    """Beleži svaki <a href> zajedno sa tekstom unutar njega: links = [(href, tekst), ...]."""

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
    """Beleži src (ili data-src kod lazy-loadinga) svakog <img>: imgs = [src, ...]."""

    def __init__(self):
        super().__init__()
        self.imgs = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            a = dict(attrs)
            src = a.get("src") or a.get("data-src")
            if src:
                self.imgs.append(src)


def quote_url(url: str) -> str:
    """Percent-enkoduje ne-ASCII karaktere (npr. ćirilicu) u putanji/query-ju URL-a,
    da bi bio bezbedan za HTTP zahteve i za Location header u redirect-u."""
    parts = urlsplit(url)
    path = quote(parts.path, safe="/%")
    query = quote(parts.query, safe="=&%")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def fetch_html(url: str) -> str:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=15) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def download_image_bytes(url: str) -> bytes:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=20) as resp:
        return resp.read()


def pick_jelovnik_url(links: list[tuple[str, str]], base_url: str = BASE_URL) -> str | None:
    """Iz liste (href, tekst) bira link "Јеловник": prvo tačan tekst, pa tekst koji ga sadrži."""
    for href, text in links:
        if text == LINK_TEXT and href:
            return urljoin(base_url, href)
    for href, text in links:
        if LINK_TEXT in text and href:
            return urljoin(base_url, href)
    return None


def pick_vrtic_image_url(imgs: list[str], page_url: str) -> str | None:
    """Iz liste slika bira prvu čije ime sadrži "вртић" (bez obzira na velika/mala slova)."""
    hint = IMG_HINT.lower()
    for src in imgs:
        if hint in src.lower():
            return quote_url(urljoin(page_url, src))
    return None


def find_jelovnik_page_url() -> str | None:
    parser = LinkFinder()
    parser.feed(fetch_html(BASE_URL))
    return pick_jelovnik_url(parser.links)


def find_vrtic_image_url() -> str | None:
    page_url = find_jelovnik_page_url()
    if not page_url:
        return None
    parser = ImgFinder()
    parser.feed(fetch_html(page_url))
    return pick_vrtic_image_url(parser.imgs, page_url)
