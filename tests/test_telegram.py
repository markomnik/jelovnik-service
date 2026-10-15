import unittest
from unittest import mock

import requests

import telegram_routes as tr
from tests.support import make_client, patch_env

EVENT = {"title": "Rođendan Mile", "all_day": False, "start": "2026-10-10T18:00", "end": "2026-10-10T19:00",
         "location": "Restoran Delfi", "description": "", "notes": "", "end_assumed": True}
SECRET = {"X-Telegram-Bot-Api-Secret-Token": "tajna_123"}


class TelegramBase(unittest.TestCase):
    def setUp(self):
        patch_env(self, TELEGRAM_BOT_TOKEN="123:TEST", TELEGRAM_WEBHOOK_SECRET="tajna_123",
                  TELEGRAM_ALLOWED_USER_IDS="111", TELEGRAM_ALLOWED_CHAT_IDS="")
        tr._pending.clear()
        tr._seen_updates.clear()
        self.client = make_client()
        self.calls = []
        self.created = []
        for name, value in (("_tg", mock.Mock(side_effect=lambda m, **p: self.calls.append((m, p)) or {"ok": True})),
                            ("_download_file", mock.Mock(return_value=b"\xff\xd8\xffFAKE")),
                            ("parse_event", mock.Mock(return_value=dict(EVENT))),
                            ("create_event", mock.Mock(side_effect=lambda ev: self.created.append(ev) or {"htmlLink": "https://cal/x"}))):
            patcher = mock.patch.object(tr, name, value)
            setattr(self, name.strip("_") + "_mock", patcher.start())
            self.addCleanup(patcher.stop)
        self.update_id = 0

    def post(self, update, headers=SECRET):
        self.update_id += 1
        return self.client.post("/telegram/webhook", json={"update_id": self.update_id, **update}, headers=headers)

    def message(self, text, chat=111, user=111, **extra):
        return self.post({"message": {"chat": {"id": chat}, "from": {"id": user}, "text": text, **extra}})

    def callback(self, data, chat=111, user=111, message_id=1):
        return self.post({"callback_query": {"id": "cb", "from": {"id": user}, "data": data,
                                             "message": {"chat": {"id": chat}, "message_id": message_id}}})

    def sent(self, method="sendMessage"):
        return [p for m, p in self.calls if m == method]

    def propose(self, **kwargs):
        self.calls.clear()
        self.message("pozivnica", **kwargs)
        sent = self.sent()
        return sent[0]["reply_markup"]["inline_keyboard"][0] if sent else None


class WebhookAccessTest(TelegramBase):
    def test_nije_podeseno(self):
        patch_env(self, TELEGRAM_WEBHOOK_SECRET=None)
        self.assertEqual(self.post({}).status_code, 503)

    def test_tajno_zaglavlje(self):
        self.assertEqual(self.post({}, headers={}).status_code, 403)
        self.assertEqual(self.post({}, headers={"X-Telegram-Bot-Api-Secret-Token": "pogresno"}).status_code, 403)
        self.assertEqual(self.post({}).status_code, 200)

    def test_dupliran_update_se_obradjuje_jednom(self):
        update = {"update_id": 777, "message": {"chat": {"id": 111}, "from": {"id": 111}, "text": "/help"}}
        self.client.post("/telegram/webhook", json=update, headers=SECRET)
        self.client.post("/telegram/webhook", json=update, headers=SECRET)
        self.assertEqual(len(self.sent()), 1)

    def test_greska_u_obradi_ne_ponavlja_update(self):
        self.tg_mock.side_effect = RuntimeError("pao")
        with self.assertLogs("app", level="ERROR"):
            self.assertEqual(self.message("/help").status_code, 200)   # uvek 200, da Telegram ne ponavlja isto


class AuthorizationTest(TelegramBase):
    def test_korisnik_sa_spiska(self):
        self.assertIsNotNone(self.propose())

    def test_korisnik_van_spiska_se_ignorise(self):
        self.assertIsNone(self.propose(chat=333, user=333))
        self.parse_event_mock.assert_not_called()

    def test_clan_grupe_van_spiska(self):
        self.assertIsNotNone(self.propose(chat=-100, user=111))
        self.assertIsNone(self.propose(chat=-100, user=999))

    def test_oba_spiska_moraju_da_se_poklope(self):
        patch_env(self, TELEGRAM_ALLOWED_CHAT_IDS="111")
        self.assertIsNotNone(self.propose(chat=111, user=111))
        self.assertIsNone(self.propose(chat=-100, user=111))

    def test_samo_spisak_cetova_stara_postavka(self):
        patch_env(self, TELEGRAM_ALLOWED_USER_IDS="", TELEGRAM_ALLOWED_CHAT_IDS="111")
        self.assertIsNotNone(self.propose(chat=111, user=111))
        self.assertIsNone(self.propose(chat=333, user=333))

    def test_bez_ijednog_spiska_niko_nema_pristup(self):
        patch_env(self, TELEGRAM_ALLOWED_USER_IDS="", TELEGRAM_ALLOWED_CHAT_IDS="")
        self.assertIsNone(self.propose())

    def test_start_nepoznatom_korisniku_daje_njegove_id_jeve(self):
        self.calls.clear()
        self.message("/start", chat=555, user=555)
        text = self.sent()[0]["text"]
        self.assertIn("Tvoj korisnički ID: 555", text)
        self.assertIn("TELEGRAM_ALLOWED_USER_IDS", text)

    def test_potvrda_od_korisnika_van_spiska(self):
        buttons = self.propose(chat=-100, user=111)
        self.calls.clear()
        self.callback(buttons[0]["callback_data"], chat=-100, user=999)
        self.assertEqual(self.created, [])
        self.assertIn("Nemaš dozvolu", self.sent("answerCallbackQuery")[0]["text"])


class ProposalFlowTest(TelegramBase):
    def test_predlog_sadrzi_polja_i_dugmad(self):
        self.calls.clear()
        self.message("Pozivam te na rođendan")
        sent = self.sent()[0]
        for fragment in ("Naslov: Rođendan Mile", "Početak: Sub 10.10.2026. 18:00", "pretpostavljeno trajanje 1 sat", "Lokacija: Restoran Delfi"):
            self.assertIn(fragment, sent["text"])
        self.assertEqual([b["text"] for b in sent["reply_markup"]["inline_keyboard"][0]], ["✅ Da", "❌ Ne"])

    def test_da_upisuje_samo_jednom(self):
        yes = self.propose()[0]["callback_data"]
        self.callback(yes)
        self.callback(yes)   # dvostruki klik
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0]["title"], "Rođendan Mile")
        self.assertIn("✅ Upisano u kalendar.", self.sent("editMessageText")[0]["text"])

    def test_ne_odbacuje(self):
        no = self.propose()[1]["callback_data"]
        self.callback(no)
        self.assertEqual(self.created, [])
        self.assertIn("Odbačeno", self.sent("editMessageText")[0]["text"])

    def test_istekao_predlog(self):
        self.calls.clear()
        self.callback("y:nepostojeci")
        self.assertIn("istekao", self.sent("answerCallbackQuery")[0]["text"])
        self.assertEqual(self.created, [])

    def test_greska_dozvole_ostavlja_predlog(self):
        response = mock.Mock(status_code=403)
        self.create_event_mock.side_effect = requests.HTTPError("403", response=response)
        yes = self.propose()[0]["callback_data"]
        self.calls.clear()
        with self.assertLogs("app", level="ERROR"):
            self.callback(yes)
        self.assertIn("calendar.events", self.sent("answerCallbackQuery")[0]["text"])
        self.assertIn(yes.split(":")[1], tr._pending)   # može ponovo kad se token ispravi


class InputTest(TelegramBase):
    def test_slika_se_preuzima_najveca_i_salje_parseru(self):
        self.post({"message": {"chat": {"id": 111}, "from": {"id": 111}, "caption": "sutra u 18h", "photo": [
            {"file_id": "mala", "width": 90, "height": 90}, {"file_id": "velika", "width": 1280, "height": 960}]}})
        self.download_file_mock.assert_called_once_with("velika")
        kwargs = self.parse_event_mock.call_args.kwargs
        self.assertEqual((kwargs["text"], kwargs["image"][1]), ("sutra u 18h", "image/jpeg"))

    def test_slika_kao_dokument(self):
        self.post({"message": {"chat": {"id": 111}, "from": {"id": 111},
                               "document": {"file_id": "dok", "mime_type": "image/png"}}})
        self.assertEqual(self.parse_event_mock.call_args.kwargs["image"][1], "image/png")

    def test_greska_parsera_se_pokazuje_korisniku(self):
        self.parse_event_mock.side_effect = tr.ParseError("Nisam uspeo da pronađem datum događaja.")
        self.calls.clear()
        self.message("nešto")
        self.assertEqual(self.sent()[0]["text"], "⚠️ Nisam uspeo da pronađem datum događaja.")

    def test_neocekivana_greska_parsera(self):
        self.parse_event_mock.side_effect = RuntimeError("pao")
        self.calls.clear()
        with self.assertLogs("app", level="ERROR"):
            self.message("nešto")
        self.assertIn("Parsiranje trenutno nije uspelo", self.sent()[0]["text"])

    def test_prazna_poruka_i_nepoznata_komanda(self):
        self.calls.clear()
        self.post({"message": {"chat": {"id": 111}, "from": {"id": 111}, "sticker": {}}})
        self.assertIn("Pošalji tekst ili sliku", self.sent()[0]["text"])
        self.calls.clear()
        self.message("/nesto")
        self.assertIn("Pošalji mi tekst ili sliku pozivnice", self.sent()[0]["text"])


if __name__ == "__main__":
    unittest.main()
