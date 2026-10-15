import unittest
from unittest import mock

import admin_routes
import menu_service
from tests.support import EXPECTED_TUESDAY, MENU_TABLE_RESPONSE, FakeResponse, make_client, patch_env

HOME = '<a href="/?page_id=7054">Јеловник</a><a href="/k">Kontakt</a>'
PAGE = '<img src="/logo.jpg"><img src="/Јеловник-вртић.jpg">'


class SecurityHeadersTest(unittest.TestCase):
    def test_zaglavlja_na_svakom_odgovoru(self):
        patch_env(self, ALLOWED_ORIGIN=None)
        client = make_client()
        for path in ("/", "/ne-postoji"):
            headers = client.get(path).headers
            self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer-when-downgrade")

    def test_allowed_origin_iz_okruzenja(self):
        patch_env(self, ALLOWED_ORIGIN="https://neko.github.io")
        self.assertEqual(make_client().get("/").headers["Access-Control-Allow-Origin"], "https://neko.github.io")


class HealthTest(unittest.TestCase):
    def test_health(self):
        menu_service.reset_cache()
        self.addCleanup(menu_service.reset_cache)
        self.assertEqual(make_client().get("/").get_json(), {"status": "ok", "cached_url": None})
        menu_service._cache["url"] = "http://x.rs/a.jpg"
        self.assertEqual(make_client().get("/").get_json()["cached_url"], "http://x.rs/a.jpg")


class AdminAccessTest(unittest.TestCase):
    PATHS = ("/debug", "/debug-ocr")

    def test_bez_tokena_endpoint_kao_da_ne_postoji(self):
        patch_env(self, ADMIN_TOKEN="tajna")
        client = make_client()
        for path in self.PATHS:
            self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.get(path + "?token=pogresno").status_code, 404)

    def test_token_koji_nije_ascii_ne_izaziva_gresku_500(self):
        patch_env(self, ADMIN_TOKEN="tajna")
        client = make_client()
        for path in self.PATHS:
            self.assertEqual(client.get(path, headers={"X-Admin-Token": "šđčćž".encode("utf-8").decode("latin-1")}).status_code, 404)
            self.assertEqual(client.get(path + "?token=šđčćž").status_code, 404)

    def test_bez_podesenog_admin_tokena_sve_je_ugaseno(self):
        patch_env(self, ADMIN_TOKEN=None)
        client = make_client()
        for path in self.PATHS:
            self.assertEqual(client.get(path + "?token=").status_code, 404)
            self.assertEqual(client.get(path + "?token=bilo-sta").status_code, 404)

    def test_token_u_zaglavlju(self):
        patch_env(self, ADMIN_TOKEN="tajna")
        with mock.patch.object(admin_routes, "fetch_html", return_value="<html></html>"):
            resp = make_client().get("/debug", headers={"X-Admin-Token": "tajna"})
        self.assertEqual(resp.status_code, 200)


class DebugTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, ADMIN_TOKEN="tajna", FREEOCR_API_KEY="focr_test")
        self.client = make_client()

    def test_debug_pokazuje_sta_server_vidi(self):
        pages = {admin_routes.BASE_URL: HOME, "https://www.pudecjidani.rs/?page_id=7054": PAGE}
        with mock.patch.object(admin_routes, "fetch_html", side_effect=lambda url: pages[url]):
            body = self.client.get("/debug?token=tajna").get_json()
        self.assertEqual(body["jelovnik_page_url"], "https://www.pudecjidani.rs/?page_id=7054")
        self.assertEqual(body["homepage_link_count"], 2)
        self.assertEqual(body["links_sample"], ["Јеловник", "Kontakt"])
        self.assertEqual(body["img_srcs"], ["/logo.jpg", "/Јеловник-вртић.jpg"])

    def test_debug_kad_sajt_ne_radi(self):
        with mock.patch.object(admin_routes, "fetch_html", side_effect=OSError("mreža")):
            body = self.client.get("/debug?token=tajna").get_json()
        self.assertEqual(body["error"], "OSError: mreža")

    def run_debug_ocr(self, response):
        with mock.patch.object(menu_service, "resolve_cached_url", return_value="http://x.rs/a.jpg"), \
             mock.patch.object(admin_routes, "download_image_bytes", return_value=b"\xff\xd8\xffFAKE"), \
             mock.patch("freeocr_client.requests.post", return_value=response) as post:
            body = self.client.get("/debug-ocr?token=tajna").get_json()
        return body, post

    def test_debug_ocr_jedan_poziv_i_mapirani_jelovnik(self):
        body, post = self.run_debug_ocr(FakeResponse(200, MENU_TABLE_RESPONSE))
        self.assertEqual(post.call_count, 1)   # ranije su plaćena dva poziva za isti rezultat
        self.assertEqual(body["mapped"]["Utorak"], EXPECTED_TUESDAY)
        self.assertEqual((body["status_code"], body["looks_like_jpeg"], body["image_bytes_len"]), (200, True, 7))
        self.assertIn("tables", body["raw_response"])

    def test_debug_ocr_greska_servisa(self):
        body, post = self.run_debug_ocr(FakeResponse(402, {"error": {"code": "insufficient_credits", "message": "x"}}))
        self.assertEqual(post.call_count, 1)
        self.assertEqual((body["status_code"], body["mapping_error"]), (402, "HTTP 402"))
        self.assertNotIn("mapped", body)

    def test_debug_ocr_bez_kljuca(self):
        patch_env(self, FREEOCR_API_KEY=None)
        with mock.patch.object(menu_service, "resolve_cached_url", return_value="http://x.rs/a.jpg"), \
             mock.patch.object(admin_routes, "download_image_bytes", return_value=b"x"):
            resp = self.client.get("/debug-ocr?token=tajna")
        self.assertEqual(resp.status_code, 500)

    def test_debug_ocr_bez_slike(self):
        with mock.patch.object(menu_service, "resolve_cached_url", return_value=None):
            resp = self.client.get("/debug-ocr?token=tajna")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
