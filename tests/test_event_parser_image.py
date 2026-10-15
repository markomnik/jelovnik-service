import unittest
from unittest import mock

import event_parser as ep
from tests.support import FakeResponse, patch_env

IMAGE = (b"\xff\xd8\xffFAKE", "image/jpeg")


def extract_response(**fields):
    return FakeResponse(200, {"result": [{"key": k, "values": v} for k, v in fields.items()]})


class ImageParsingTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, FREEOCR_API_KEY="focr_test")

    def parse(self, routes, **kwargs):
        """routes: {'extract': odgovor, 'ocr': odgovor}; vraća (događaj, pozvani endpointi)."""
        called = []

        def fake_post(url, **kw):
            endpoint = url.rsplit("/", 1)[1]
            called.append(endpoint)
            return routes[endpoint]

        with mock.patch("freeocr_client.requests.post", side_effect=fake_post):
            return ep.parse_event(**kwargs), called

    def test_extract_je_dovoljan_i_ocr_se_ne_zove(self):
        event, called = self.parse({"extract": extract_response(
            title=["Крштење малог Луке"], date=["2026-10-17"], start_time=["12.30"], end_time=[],
            location=["Храм Светог Саве, Београд"], details=["Молимо потврдите долазак"])}, image=IMAGE)
        self.assertEqual(called, ["extract"])
        self.assertEqual((event["title"], event["start"], event["location"], event["description"]),
                         ("Krštenje malog Luke", "2026-10-17T12:30", "Hram Svetog Save, Beograd", "Molimo potvrdite dolazak"))

    def test_datum_stampan_recima_i_vreme_uz_datum(self):
        event, _ = self.parse({"extract": extract_response(
            title=["Rođendan"], date=["Subota, 24. oktobar 2026. u 18h"], location=["Restoran Delfi"])}, image=IMAGE)
        self.assertEqual(event["start"], "2026-10-24T18:00")

    def test_bez_datuma_koristi_se_ceo_tekst_sa_slike(self):
        event, called = self.parse({
            "extract": extract_response(title=["Poziv"]),
            "ocr": FakeResponse(200, {"text": "# POZIVNICA\n\n**Venčanje Ane i Marka**\n\nNedelja, 25.10.2026. u 15:00\n\nMesto: Hotel Moskva"}),
        }, image=IMAGE)
        self.assertEqual(called, ["extract", "ocr"])
        self.assertEqual((event["title"], event["start"], event["location"]),
                         ("Venčanje Ane i Marka", "2026-10-25T15:00", "Hotel Moskva"))   # "Poziv" je preopšte za naslov

    def test_opis_uz_sliku_popunjava_ono_sto_fali(self):
        event, _ = self.parse({"extract": extract_response(title=["Rođendan"]),
                               "ocr": FakeResponse(200, {"text": "Rođendan"})}, image=IMAGE, text="25.10.2026. u 18h")
        self.assertEqual((event["title"], event["start"]), ("Rođendan", "2026-10-25T18:00"))

    def test_slika_ima_prednost_nad_opisom(self):
        event, _ = self.parse({"extract": extract_response(title=["Slava"], date=["2026-10-24"], start_time=["19:00"])},
                              image=IMAGE, text="25.10.2026. u 18h")
        self.assertEqual(event["start"], "2026-10-24T19:00")

    def test_samo_tekst_ne_zove_ocr(self):
        event, called = self.parse({}, text="Sastanak 12.10.2026. u 10h")
        self.assertEqual((called, event["start"]), ([], "2026-10-12T10:00"))


class ImageErrorsTest(unittest.TestCase):
    def parse_with(self, response=None, key="focr_test", **kwargs):
        patch_env(self, FREEOCR_API_KEY=key)
        with mock.patch("freeocr_client.requests.post", return_value=response):
            return ep.parse_event(image=IMAGE, **kwargs)

    def test_poruke_za_korisnika(self):
        cases = [(FakeResponse(402, {"error": {"code": "insufficient_credits", "message": "x"}}), "kredita"),
                 (FakeResponse(401, {"error": {"code": "invalid_key", "message": "x"}}), "ključ"),
                 (FakeResponse(429, {"error": {"code": "rate_limited", "message": "x"}}), "preopterećen")]
        for response, fragment in cases:
            with self.assertRaises(ep.ParseError) as ctx:
                self.parse_with(response)
            self.assertIn(fragment, str(ctx.exception))

    def test_bez_kljuca(self):
        with self.assertRaises(ep.ParseError) as ctx:
            self.parse_with(key=None)
        self.assertIn("FREEOCR_API_KEY", str(ctx.exception))

    def test_ostale_greske_idu_u_log(self):
        from freeocr_client import FreeOCRError
        with self.assertRaises(FreeOCRError):
            self.parse_with(FakeResponse(500, {"error": {"code": "internal_error", "message": "x"}}))

    def test_nepodrzan_format_i_velicina(self):
        for image, fragment in (((b"%PDF", "application/pdf"), "Format"), ((b"x" * (ep.MAX_IMAGE_BYTES + 1), "image/jpeg"), "prevelika")):
            with self.assertRaises(ep.ParseError) as ctx:
                ep.parse_event(image=image)
            self.assertIn(fragment, str(ctx.exception))

    def test_nista_za_parsiranje(self):
        with self.assertRaises(ep.ParseError):
            ep.parse_event()
        with self.assertRaises(ep.ParseError):
            ep.parse_event(text="   ")


if __name__ == "__main__":
    unittest.main()
