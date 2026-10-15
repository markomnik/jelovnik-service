"""Čitanje tabele jelovnika: freeocr.ai vraća HTML tabelu, a ovde se mapira na dane i obroke."""

from html.parser import HTMLParser

import freeocr_client
from config import DAYS
from text_utils import cyr_to_lat

# Zaglavlja koja prepoznajemo (ćirilica, latinica i latinica bez dijakritika) -> naš naziv.
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


class TableGridParser(HTMLParser):
    """Parsira <table> HTML (iz freeocr.ai odgovora) u listu redova/ćelija."""

    def __init__(self):
        super().__init__()
        self.grid = []
        self._row = None
        self._in_cell = False
        self._cell_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_text = []

    def handle_data(self, data):
        if self._in_cell:
            self._cell_text.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._in_cell = False
            if self._row is not None:
                self._row.append("".join(self._cell_text).strip())
        elif tag == "tr":
            if self._row is not None:
                self.grid.append(self._row)
            self._row = None


def html_table_to_grid(html: str) -> list[list[str]]:
    parser = TableGridParser()
    parser.feed(html)
    return parser.grid


def _match_hint(label: str, hints: dict) -> str | None:
    low = (label or "").strip().lower()
    for key, val in hints.items():
        if key in low:
            return val
    return None


def grid_to_menu(grid: list[list[str]]) -> dict:
    """
    Pretvara generičku tabelu (lista redova, svaki red lista ćelija) u
    {"Ponedeljak": {"dorucak", "voce", "uzina", "rucak"}, ...}, bez obzira da li su dani
    u header redu ili u header koloni. Tekst ćelija se prevodi u latinicu.
    """
    if not grid or len(grid) < 2:
        raise ValueError("Tabela iz OCR odgovora je prazna ili prekratka.")

    header_row = grid[0]
    header_col = [row[0] if row else "" for row in grid]

    days_in_row = {i: _match_hint(c, DAN_HINTS) for i, c in enumerate(header_row)}
    days_in_col = {i: _match_hint(c, DAN_HINTS) for i, c in enumerate(header_col)}
    meals_in_row = {i: _match_hint(c, OBROK_HINTS) for i, c in enumerate(header_row)}
    meals_in_col = {i: _match_hint(c, OBROK_HINTS) for i, c in enumerate(header_col)}

    result = {d: {"dorucak": "", "voce": "", "uzina": "", "rucak": ""} for d in DAYS[:5]}

    if any(days_in_row.values()) and any(meals_in_col.values()):
        # dani su kolone (header red), obroci su redovi (header kolona)
        for r_idx, row in enumerate(grid):
            meal = meals_in_col.get(r_idx)
            if not meal:
                continue
            for c_idx, cell in enumerate(row):
                day = days_in_row.get(c_idx)
                if day:
                    result[day][meal] = cyr_to_lat((cell or "").strip())
        return result

    if any(days_in_col.values()) and any(meals_in_row.values()):
        # obrnuto: dani su redovi (header kolona), obroci su kolone (header red)
        for r_idx, row in enumerate(grid):
            day = days_in_col.get(r_idx)
            if not day:
                continue
            for c_idx, cell in enumerate(row):
                meal = meals_in_row.get(c_idx)
                if meal:
                    result[day][meal] = cyr_to_lat((cell or "").strip())
        return result

    raise ValueError("Nisam uspeo da prepoznam raspored dana/obroka u OCR tabeli.")


def menu_from_table_response(data: dict) -> dict:
    """Iz odgovora freeocr.ai /table (već učitan JSON) pravi jelovnik. Ne zove mrežu."""
    tables = data.get("tables") or []
    if not tables:
        raise ValueError("freeocr.ai nije pronašao nijednu tabelu na slici.")
    # Ako ima više tabela na slici, uzmi najveću (najviše <tr>) - verovatno glavna tabela jelovnika
    best_html = max(tables, key=lambda t: (t.get("html") or "").count("<tr")).get("html", "")
    return grid_to_menu(html_table_to_grid(best_html))


def extract_menu_table(image_bytes: bytes) -> dict:
    """Šalje sliku jelovnika freeocr.ai-ju i vraća jelovnik po danima i obrocima."""
    data = freeocr_client.post_json("table", image_bytes, "image/jpeg", params={"format": "json"})
    return menu_from_table_response(data)
