import unittest
from unittest import mock

import freeocr_client as fc
from tests.support import FakeResponse, patch_env


class FreeOcrClientTest(unittest.TestCase):
    def test_bez_kljuca(self):
        patch_env(self, FREEOCR_API_KEY=None)
        self.assertFalse(fc.is_configured())
        with self.assertRaises(fc.FreeOCRError) as ctx:
            fc.post_json("table", b"x")
        self.assertIsNone(ctx.exception.status)
        self.assertEqual(ctx.exception.code, "not_configured")

    def test_kljuc_sa_razmakom_se_ocisti(self):
        patch_env(self, FREEOCR_API_KEY="  focr_abc\n")
        with mock.patch("freeocr_client.requests.post", return_value=FakeResponse(200, {})) as post:
            fc.post_json("ocr", b"x")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer focr_abc"})

    def test_zahtev_je_ispravno_sastavljen(self):
        patch_env(self, FREEOCR_API_KEY="focr_abc")
        with mock.patch("freeocr_client.requests.post", return_value=FakeResponse(200, {"ok": 1})) as post:
            result = fc.post_json("extract", b"bajtovi", "image/png", params={"fields": ["a", "b"]})
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(post.call_args.args[0], "https://freeocr.ai/api/v1/platform/extract")
        self.assertEqual(post.call_args.kwargs["params"], {"fields": ["a", "b"]})
        self.assertEqual(post.call_args.kwargs["files"], {"image": ("slika.png", b"bajtovi", "image/png")})

    def test_greska_servisa_nosi_poruku_i_kod(self):
        patch_env(self, FREEOCR_API_KEY="focr_abc")
        body = {"error": {"code": "insufficient_credits", "message": "Insufficient balance."}}
        with mock.patch("freeocr_client.requests.post", return_value=FakeResponse(402, body)):
            with self.assertRaises(fc.FreeOCRError) as ctx:
                fc.post_json("table", b"x")
        self.assertEqual((ctx.exception.status, ctx.exception.code), (402, "insufficient_credits"))
        self.assertIn("Insufficient balance", str(ctx.exception))

    def test_greska_bez_json_tela(self):
        patch_env(self, FREEOCR_API_KEY="focr_abc")
        with mock.patch("freeocr_client.requests.post", return_value=FakeResponse(502, None, text="Bad gateway", content_type="text/html")):
            with self.assertRaises(fc.FreeOCRError) as ctx:
                fc.post_json("table", b"x")
        self.assertEqual((ctx.exception.status, ctx.exception.code, ctx.exception.message), (502, "http_error", "Bad gateway"))


if __name__ == "__main__":
    unittest.main()
