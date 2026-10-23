import datetime as dt
import unittest
from unittest import mock

from menu import routes as menu_routes
from menu import service as menu_service
from tests.support import EXPECTED_TUESDAY, make_client

URL = "http://www.pudecjidani.rs/wp-content/uploads/2026/10/slika.jpg"
TABLE = {"Utorak": EXPECTED_TUESDAY, "Sreda": {"dorucak": "Mleko", "voce": "Kruška", "uzina": "Puding", "rucak": "Supa"}}


class FakeDatetime:
    weekday = 0

    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 10, 5 + cls.weekday, 9, 0, tzinfo=tz)   # 5.10.2026. je ponedeljak


class MenuRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = make_client()
        for target, value in (("resolve_cached_url", URL), ("resolve_cached_table", TABLE)):
            patcher = mock.patch.object(menu_service, target, return_value=value)
            self.mocks = getattr(self, "mocks", {})
            self.mocks[target] = patcher.start()
            self.addCleanup(patcher.stop)
        datetime_patch = mock.patch.object(menu_routes, "datetime", FakeDatetime)
        datetime_patch.start()
        self.addCleanup(datetime_patch.stop)

    def get_today(self, weekday):
        FakeDatetime.weekday = weekday
        return self.client.get("/jelovnik/vrtic/danas")

    def test_radni_dan_vraca_jela(self):
        resp = self.get_today(1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"dan": "Utorak", **EXPECTED_TUESDAY})

    def test_vikend_nema_jelovnika(self):
        for weekday, day in ((5, "Subota"), (6, "Nedelja")):
            body = self.get_today(weekday).get_json()
            self.assertEqual(body, {"dan": day, "poruka": "Vrtić ne radi vikendom."})

    def test_dan_koga_nema_u_tabeli(self):
        resp = self.get_today(0)   # ponedeljka nema u lažnoj tabeli
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.get_json()["dan"], "Ponedeljak")

    def test_greska_citanja_tabele(self):
        self.mocks["resolve_cached_table"].side_effect = ValueError("nema tabele")
        resp = self.get_today(1)
        self.assertEqual(resp.status_code, 502)
        self.assertIn("nema tabele", resp.get_json()["greska"])

    def test_nema_urla_slike(self):
        self.mocks["resolve_cached_url"].return_value = None
        for path in ("/jelovnik/vrtic/danas", "/jelovnik/vrtic/nedelja"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.get_json(), {"greska": "Jelovnik trenutno nije pronađen na sajtu."})
        self.assertEqual(self.client.get("/jelovnik/vrtic").status_code, 404)

    def test_cela_nedelja(self):
        self.assertEqual(self.client.get("/jelovnik/vrtic/nedelja").get_json(), TABLE)

    def test_preusmerenje_na_sliku(self):
        resp = self.client.get("/jelovnik/vrtic")
        self.assertEqual((resp.status_code, resp.headers["Location"]), (302, URL))


if __name__ == "__main__":
    unittest.main()
