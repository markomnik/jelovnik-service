import unittest
from unittest import mock

from admin import routes as admin_routes
from tests.support import make_client, patch_env


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


if __name__ == "__main__":
    unittest.main()
