import unittest
from unittest import mock

import requests

import telegram_api as tga
from app import create_app
from tests.support import TEST_CONFIG, FakeResponse, patch_env

TOKEN = "123456:SECRET-TOKEN"


class TelegramApiTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, TELEGRAM_BOT_TOKEN=TOKEN)
        ctx = create_app(TEST_CONFIG).app_context()
        ctx.push()
        self.addCleanup(ctx.pop)

    def test_token_iz_okruzenja(self):
        self.assertEqual(tga.token(), TOKEN)
        patch_env(self, TELEGRAM_BOT_TOKEN=None)
        self.assertIsNone(tga.token())

    def test_poziv_metode(self):
        with mock.patch.object(tga.requests, "post", return_value=FakeResponse(200, {"ok": True, "result": 1})) as post:
            result = tga.call("getMe", a=1)
        self.assertEqual(result, {"ok": True, "result": 1})
        self.assertEqual(post.call_args.args[0], f"https://api.telegram.org/bot{TOKEN}/getMe")
        self.assertEqual(post.call_args.kwargs["json"], {"a": 1})

    def test_http_greska_se_loguje_i_vraca_odgovor(self):
        with mock.patch.object(tga.requests, "post", return_value=FakeResponse(400, {"ok": False, "description": "loše"})), \
             self.assertLogs("app", level="ERROR") as logs:
            result = tga.call("sendMessage", chat_id=1)
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 400", logs.output[0])

    def test_mrezna_greska_ne_otkriva_token(self):
        with mock.patch.object(tga.requests, "post", side_effect=requests.ConnectionError(f"greška za https://api.telegram.org/bot{TOKEN}/x")), \
             self.assertLogs("app", level="ERROR") as logs:
            self.assertEqual(tga.call("sendMessage"), {})
        self.assertNotIn("SECRET-TOKEN", "\n".join(logs.output))   # token je u URL-u i ne sme u log

    def test_slanje_poruke(self):
        with mock.patch.object(tga, "call", return_value={"ok": True}) as call:
            tga.send_message(5, "Zdravo", reply_markup={"x": 1})
        call.assert_called_once_with("sendMessage", chat_id=5, text="Zdravo",
                                     link_preview_options={"is_disabled": True}, reply_markup={"x": 1})


class DownloadFileTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, TELEGRAM_BOT_TOKEN=TOKEN)
        ctx = create_app(TEST_CONFIG).app_context()
        ctx.push()
        self.addCleanup(ctx.pop)

    def test_preuzimanje(self):
        response = mock.Mock(content=b"\xff\xd8\xffFAKE")
        with mock.patch.object(tga, "call", return_value={"result": {"file_path": "photos/a.jpg"}}), \
             mock.patch.object(tga.requests, "get", return_value=response) as get:
            self.assertEqual(tga.download_file("fid"), b"\xff\xd8\xffFAKE")
        self.assertEqual(get.call_args.args[0], f"https://api.telegram.org/file/bot{TOKEN}/photos/a.jpg")

    def test_nema_putanje_fajla(self):
        with mock.patch.object(tga, "call", return_value={}):
            with self.assertRaises(tga.TelegramError):
                tga.download_file("fid")

    def test_greska_preuzimanja_nema_token_u_uzroku(self):
        with mock.patch.object(tga, "call", return_value={"result": {"file_path": "a.jpg"}}), \
             mock.patch.object(tga.requests, "get", side_effect=requests.ConnectionError(f"https://api.telegram.org/file/bot{TOKEN}/a.jpg")):
            with self.assertRaises(tga.TelegramError) as ctx:
                tga.download_file("fid")
        self.assertEqual(str(ctx.exception), "Nisam uspeo da preuzmem sliku sa Telegrama.")
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)   # izuzetak sa tokenom u URL-u se ne prenosi dalje


if __name__ == "__main__":
    unittest.main()
