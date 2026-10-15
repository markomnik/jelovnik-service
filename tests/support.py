"""Zajednički pomoćnici za testove."""

import json
import os
from unittest import mock

TEST_CONFIG = {"TESTING": True, "RATELIMIT_ENABLED": False}


def make_client():
    from app import create_app
    return create_app(TEST_CONFIG).test_client()


def patch_env(testcase, **values):
    """Postavlja environment varijable za trajanje testa (None znači: ukloni varijablu)."""
    snapshot = mock.patch.dict(os.environ)   # vraća originalno stanje kad se test završi
    snapshot.start()
    testcase.addCleanup(snapshot.stop)
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class FakeResponse:
    """Dovoljno slično requests.Response za kod koji testiramo."""

    def __init__(self, status=200, body=None, text=None, content_type="application/json"):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.text = text if text is not None else json.dumps(body)
        self.headers = {"content-type": content_type}

    def json(self):
        if self._body is None:
            raise ValueError("nije JSON")
        return self._body


# Tabela jelovnika kakvu vraća freeocr.ai (ćirilica; dani su redovi, obroci kolone).
_DAYS = [
    ("Понедељак", "05.10.2026.", "Јогурт (глутен)", "Јабука", "Жито са орасима", "Чорба од поврћа, хлеб"),
    ("Уторак", "06.10.2026.", "Чај са лимуном", "Грожђе", "Јогурт, мекика", "Шпагете, салата"),
    ("Среда", "07.10.2026.", "Млеко, хлеб", "Крушка", "Пудинг", "Пилећа супа"),
    ("Четвртак", "08.10.2026.", "Какао", "Грожђе", "Лимунада", "Купус са месом"),
    ("Петак", "09.10.2026.", "Млеко, хлеб", "Јабука", "Јогурт", "Шарени пасуљ"),
]
MENU_TABLE_HTML = (
    "<table><thead><tr><th>ДАН ДАТУМ</th><th>8.30h<br>ДОРУЧАК</th><th>10.30h<br>ВОЋЕ</th>"
    "<th>11.30h<br>УЖИНА</th><th>14.30h<br>РУЧАК</th></tr></thead><tbody>"
    + "".join(f"<tr><td>{d}<br>{dt}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{e}</td></tr>"
              for d, dt, a, b, c, e in _DAYS)
    + "</tbody></table>"
)
MENU_TABLE_RESPONSE = {"tables": [
    {"title": "Jelovnik", "html": MENU_TABLE_HTML},
    {"title": "Nutritivne vrednosti", "html": "<table><tr><td>1</td></tr></table>"},
]}
EXPECTED_TUESDAY = {"dorucak": "Čaj sa limunom", "voce": "Grožđe", "uzina": "Jogurt, mekika", "rucak": "Špagete, salata"}
