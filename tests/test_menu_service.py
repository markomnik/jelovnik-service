import unittest
from unittest import mock

import menu_service as ms

URL_A = "http://x.rs/a.jpg"
URL_B = "http://x.rs/b.jpg"
TABLE = {"Ponedeljak": {"dorucak": "x"}}


class UrlCacheTest(unittest.TestCase):
    def setUp(self):
        ms.reset_cache()
        self.addCleanup(ms.reset_cache)

    def test_url_se_kesira(self):
        with mock.patch.object(ms, "find_vrtic_image_url", return_value=URL_A) as find:
            self.assertEqual(ms.resolve_cached_url(), URL_A)
            self.assertEqual(ms.resolve_cached_url(), URL_A)
        self.assertEqual(find.call_count, 1)
        self.assertEqual(ms.cached_url(), URL_A)

    def test_posle_isteka_roka_trazi_se_ponovo(self):
        with mock.patch.object(ms, "find_vrtic_image_url", side_effect=[URL_A, URL_B]) as find, \
             mock.patch.object(ms.time, "time", side_effect=[1000, 1000 + ms.CACHE_TTL_SECONDS + 1, 1000 + ms.CACHE_TTL_SECONDS + 1]):
            self.assertEqual(ms.resolve_cached_url(), URL_A)
            self.assertEqual(ms.resolve_cached_url(), URL_B)
        self.assertEqual(find.call_count, 2)

    def test_greska_pri_dohvatanju_vraca_stari_url(self):
        # sajt vrtića ne radi: bolje stara slika nego ništa (ranije je ovo davalo grešku 500)
        with mock.patch.object(ms, "find_vrtic_image_url", return_value=URL_A):
            ms.resolve_cached_url()
        ms._cache["ts"] = 0   # keš je istekao
        with mock.patch.object(ms, "find_vrtic_image_url", side_effect=OSError("mreža ne radi")):
            with self.assertLogs("menu_service", level="ERROR"):
                self.assertEqual(ms.resolve_cached_url(), URL_A)

    def test_greska_bez_starog_urla_daje_none(self):
        with mock.patch.object(ms, "find_vrtic_image_url", side_effect=OSError("mreža ne radi")):
            with self.assertLogs("menu_service", level="ERROR"):
                self.assertIsNone(ms.resolve_cached_url())

    def test_link_nije_pronadjen_vraca_stari_url(self):
        with mock.patch.object(ms, "find_vrtic_image_url", return_value=URL_A):
            ms.resolve_cached_url()
        ms._cache["ts"] = 0
        with mock.patch.object(ms, "find_vrtic_image_url", return_value=None):
            self.assertEqual(ms.resolve_cached_url(), URL_A)


class TableCacheTest(unittest.TestCase):
    def setUp(self):
        ms.reset_cache()
        self.addCleanup(ms.reset_cache)

    def test_tabela_se_cita_jednom_po_urlu(self):
        with mock.patch.object(ms, "download_image_bytes", return_value=b"img") as dl, \
             mock.patch.object(ms, "extract_menu_table", return_value=TABLE) as ocr:
            self.assertEqual(ms.resolve_cached_table(URL_A), TABLE)
            self.assertEqual(ms.resolve_cached_table(URL_A), TABLE)
        self.assertEqual((dl.call_count, ocr.call_count), (1, 1))

    def test_novi_url_znaci_novo_citanje(self):
        with mock.patch.object(ms, "download_image_bytes", return_value=b"img"), \
             mock.patch.object(ms, "extract_menu_table", return_value=TABLE) as ocr:
            ms.resolve_cached_table(URL_A)
            ms.resolve_cached_table(URL_B)
        self.assertEqual(ocr.call_count, 2)

    def test_neuspesno_citanje_se_ne_kesira(self):
        with mock.patch.object(ms, "download_image_bytes", return_value=b"img"), \
             mock.patch.object(ms, "extract_menu_table", side_effect=[ValueError("loše"), TABLE]) as ocr:
            with self.assertRaises(ValueError):
                ms.resolve_cached_table(URL_A)
            self.assertEqual(ms.resolve_cached_table(URL_A), TABLE)
        self.assertEqual(ocr.call_count, 2)


if __name__ == "__main__":
    unittest.main()
