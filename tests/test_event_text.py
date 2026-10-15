import unittest
from datetime import date, datetime

import event_normalize
import event_text
from config import TZ
from event_errors import ParseError

TODAY = date(2026, 10, 9)   # petak
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=TZ)


def parse(text):
    return event_normalize.normalize_event(event_text.from_text(text, TODAY), NOW)


class TextParsingTest(unittest.TestCase):
    def check(self, text, **expected):
        event = parse(text)
        for key, value in expected.items():
            self.assertEqual(event[key], value, f"{key} za: {text!r}")
        return event

    def test_jedna_recenica(self):
        self.check("Pozivam te sutra u 18h na rođendan kod Mile",
                   title="Rođendan kod Mile", start="2026-10-10T18:00", end="2026-10-10T19:00", end_assumed=True)

    def test_pozivnica_u_vise_redova(self):
        self.check("POZIVNICA\nKrštenje malog Luke\nSubota, 17.10.2026. u 12:30\n"
                   "Mesto: Hram Svetog Save, Beograd\nMolimo potvrdite dolazak na 064/123-4567",
                   title="Krštenje malog Luke", start="2026-10-17T12:30", location="Hram Svetog Save, Beograd",
                   description="Molimo potvrdite dolazak na 064/123-4567")

    def test_cirilica_postaje_latinica(self):
        self.check("Позивам вас на рођендан у суботу у 18:00 у ресторану Делфи",
                   title="Rođendan u restoranu Delfi", start="2026-10-10T18:00")

    def test_lokacija_posle_zareza(self):
        self.check("Venčanje Ane i Marka 24.10.2026. u 16h, Hotel Moskva, Terazije 20",
                   title="Venčanje Ane i Marka", start="2026-10-24T16:00", location="Hotel Moskva", description="Terazije 20")

    def test_labele(self):
        self.check("Naslov: Roditeljski sastanak\nDatum: 14.10.2026.\nVreme: 17:30\nLokacija: OŠ Vuk Karadžić, učionica 12",
                   title="Roditeljski sastanak", start="2026-10-14T17:30", location="OŠ Vuk Karadžić, učionica 12", description="")

    def test_opseg_vremena(self):
        self.check("Sastanak sutra 10:00-11:30", title="Sastanak", start="2026-10-10T10:00", end="2026-10-10T11:30", end_assumed=False)

    def test_kraj_posle_ponoci(self):
        self.check("Doček 12.12.2026. 22:00 - 01:00", start="2026-12-12T22:00", end="2026-12-13T01:00")
        self.check("Žurka 31. oktobra 2026. od 21 do 02h u klubu Drugstore",
                   title="Žurka u klubu Drugstore", start="2026-10-31T21:00", end="2026-11-01T02:00")

    def test_bez_vremena_je_ceo_dan(self):
        event = self.check("Piknik 25.10.", title="Piknik", start="2026-10-25", end="2026-10-25", all_day=True)
        self.assertIn("pretpostavljena 2026", event["notes"])
        self.assertIn("Vreme nije pronađeno", event["notes"])

    def test_relativni_datum_ostavlja_napomenu(self):
        event = self.check("Ručak u petak u 13.30h", title="Ručak", start="2026-10-16T13:30")
        self.assertIn("petak", event["notes"])

    def test_engleski_predlozi(self):
        self.check("Meeting on 15.10.2026. at 6 pm, Zoom", title="Meeting", start="2026-10-15T18:00", description="Zoom")

    def test_vreme_bez_jedinice_posle_u(self):
        self.check("Večera 20.10.2026. u 19.30", title="Večera", start="2026-10-20T19:30")
        self.check("Sastanak 12.10.2026. u 9:15 u kancelariji", title="Sastanak u kancelariji", start="2026-10-12T09:15")

    def test_cene_se_ne_citaju_kao_datum(self):
        self.check("Koncert 20.11.2026. u 20h, karte 1.500 din, ulaz 12.50 eur", start="2026-11-20T20:00")

    def test_bez_datuma_trazi_se_dopuna(self):
        with self.assertRaises(ParseError) as ctx:
            parse("Vidimo se uskoro na kafi")
        self.assertIn("datum", str(ctx.exception))


class HelpersTest(unittest.TestCase):
    def test_genericki_naslovi(self):
        for title in ("Pozivnica", "POZIVNICA!", "Save the date", "Pozivamo vas na"):
            self.assertTrue(event_text.is_generic_heading(title), title)
        self.assertFalse(event_text.is_generic_heading("Pozivnica za venčanje Ane i Marka"))

    def test_markdown_se_uklanja(self):
        self.assertEqual(event_text.strip_markdown("# Naslov\n**debelo** <b>x</b>").split(), ["Naslov", "debelo", "x"])


if __name__ == "__main__":
    unittest.main()
