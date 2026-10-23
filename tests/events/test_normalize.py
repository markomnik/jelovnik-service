import unittest
from datetime import datetime

from events import normalize as event_normalize
from core.config import TZ
from events.errors import ParseError

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=TZ)


def normalize(**raw):
    return event_normalize.normalize_event(raw, NOW)


class NormalizeEventTest(unittest.TestCase):
    def test_bez_kraja_pretpostavlja_se_sat_trajanja(self):
        e = normalize(title="Rođendan", start_date="2026-10-10", start_time="18:00")
        self.assertEqual((e["start"], e["end"], e["end_assumed"], e["all_day"]), ("2026-10-10T18:00", "2026-10-10T19:00", True, False))

    def test_kraj_posle_ponoci(self):
        e = normalize(title="Žurka", start_date="2026-10-10", start_time="22:00", end_time="01:00")
        self.assertEqual((e["end"], e["end_assumed"]), ("2026-10-11T01:00", False))

    def test_isto_vreme_pocetka_i_kraja_se_ispravlja(self):
        e = normalize(title="X", start_date="2026-10-10", start_time="18:00", end_time="18:00")
        self.assertEqual((e["end"], e["end_assumed"]), ("2026-10-10T19:00", True))

    def test_vise_dana_za_ceo_dan(self):
        e = normalize(title="Izlet", start_date="2026-10-17", end_date="2026-10-18")
        self.assertEqual((e["start"], e["end"], e["all_day"]), ("2026-10-17", "2026-10-18", True))

    def test_kraj_pre_pocetka_za_ceo_dan(self):
        e = normalize(title="Izlet", start_date="2026-10-17", end_date="2026-10-10")
        self.assertEqual(e["end"], "2026-10-17")

    def test_datum_u_proslosti_ostavlja_napomenu(self):
        self.assertIn("u prošlosti", normalize(title="Staro", start_date="2025-03-01", start_time="10:00")["notes"])
        self.assertNotIn("u prošlosti", normalize(title="Danas", start_date="2026-10-09", start_time="10:00")["notes"])

    def test_naslov_po_defaultu(self):
        self.assertEqual(normalize(title="  ", start_date="2026-10-10", start_time="10:00")["title"], "Događaj")

    def test_nije_pozivnica(self):
        with self.assertRaises(ParseError) as ctx:
            normalize(is_event=False, notes="Ovo je račun.")
        self.assertEqual(str(ctx.exception), "Ovo je račun.")

    def test_bez_datuma(self):
        for raw in ({"title": "X"}, {"title": "X", "start_date": "nije datum"}):
            with self.assertRaises(ParseError):
                event_normalize.normalize_event(raw, NOW)

    def test_opis_se_skracuje(self):
        self.assertEqual(len(normalize(title="X", start_date="2026-10-10", description="a" * 900)["description"]), 500)


if __name__ == "__main__":
    unittest.main()
