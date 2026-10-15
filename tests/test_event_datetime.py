import unittest
from datetime import date, time

import event_datetime as edt

TODAY = date(2026, 10, 9)   # petak


class FindDatesTest(unittest.TestCase):
    def dates(self, text):
        return [d["date"] for d in edt.find_dates(text, TODAY)]

    def test_oblici_zapisa(self):
        self.assertEqual(self.dates("10.10.2026."), [date(2026, 10, 10)])
        self.assertEqual(self.dates("10/10/26"), [date(2026, 10, 10)])
        self.assertEqual(self.dates("2026-10-10"), [date(2026, 10, 10)])
        self.assertEqual(self.dates("31. oktobra 2026."), [date(2026, 10, 31)])
        self.assertEqual(self.dates("3 mar 2027"), [date(2027, 3, 3)])

    def test_bez_godine_uzima_najblizi_predstojeci_datum(self):
        self.assertEqual(self.dates("25.10."), [date(2026, 10, 25)])
        self.assertEqual(self.dates("5.3."), [date(2027, 3, 5)])   # mart je već prošao ove godine

    def test_relativni_izrazi(self):
        self.assertEqual(self.dates("sutra"), [date(2026, 10, 10)])
        self.assertEqual(self.dates("prekosutra"), [date(2026, 10, 11)])
        self.assertEqual(self.dates("u subotu"), [date(2026, 10, 10)])
        self.assertEqual(self.dates("u petak"), [date(2026, 10, 16)])   # danas je petak: prvi sledeći

    def test_izricit_datum_ima_prednost_nad_relativnim(self):
        self.assertEqual(self.dates("u subotu, 17.10.2026."), [date(2026, 10, 17)])

    def test_nevalidan_datum_i_cene_nisu_datumi(self):
        self.assertEqual(self.dates("31.2.2026."), [])
        self.assertEqual(self.dates("karte 1.500 din, ulaz 12.50 eur"), [])


class FindTimesTest(unittest.TestCase):
    def times(self, text):
        return [t for t, _, _ in edt.find_times(text)]

    def test_oblici_zapisa(self):
        self.assertEqual(self.times("u 18h"), [time(18, 0)])
        self.assertEqual(self.times("u 18:30"), [time(18, 30)])
        self.assertEqual(self.times("u 13.30h"), [time(13, 30)])
        self.assertEqual(self.times("u 19.30"), [time(19, 30)])
        self.assertEqual(self.times("u 9 časova"), [time(9, 0)])
        self.assertEqual(self.times("at 6 pm"), [time(18, 0)])
        self.assertEqual(self.times("at 12 am"), [time(0, 0)])

    def test_opsezi(self):
        self.assertEqual(self.times("10:00-11:30"), [time(10, 0), time(11, 30)])
        self.assertEqual(self.times("od 21 do 02h"), [time(21, 0), time(2, 0)])
        self.assertEqual(self.times("18-21h"), [time(18, 0), time(21, 0)])

    def test_nevalidna_vremena(self):
        self.assertEqual(self.times("u 25h"), [])
        self.assertEqual(self.times("u 12:75"), [])


class HelpersTest(unittest.TestCase):
    def test_polozaji_relativnih_reci(self):
        text = "Vidimo se sutra u 18h, a u subotu ne"
        self.assertEqual([text[a:b] for a, b in edt.relative_date_spans(text)], ["sutra", "subotu"])

    def test_maskiranje_cuva_duzinu_teksta(self):
        text = "10.10.2026. u 18h"
        masked = edt.mask_spans(text, [(0, 11)])
        self.assertEqual(len(masked), len(text))
        self.assertEqual(masked, " " * 12 + "u 18h")

    def test_vreme_iz_polja_dozvoljava_golo_vreme(self):
        for value, expected in (("18", time(18, 0)), ("18.30", time(18, 30)), ("18:30", time(18, 30)), ("u 18h", time(18, 0))):
            self.assertEqual(edt.time_from_field(value), expected, value)
        self.assertIsNone(edt.time_from_field("nije vreme"))


if __name__ == "__main__":
    unittest.main()
