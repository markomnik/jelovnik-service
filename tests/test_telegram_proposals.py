import unittest
from unittest import mock

import telegram_proposals as tp

TIMED = {"title": "Rođendan Mile", "all_day": False, "start": "2026-10-10T18:00", "end": "2026-10-10T19:00",
         "location": "Restoran Delfi", "description": "Poklon nije obavezan", "notes": "", "end_assumed": True}
ALL_DAY = {"title": "Izlet", "all_day": True, "start": "2026-10-17", "end": "2026-10-18",
           "location": "", "description": "", "notes": "Vreme nije pronađeno, pa je događaj za ceo dan.", "end_assumed": False}


class FormatProposalTest(unittest.TestCase):
    def test_dogadjaj_sa_vremenom(self):
        text = tp.format_proposal(TIMED, "Da li da upišem u kalendar?")
        self.assertEqual(text.splitlines(), [
            "📅 Predlog događaja", "", "Naslov: Rođendan Mile", "Početak: Sub 10.10.2026. 18:00",
            "Kraj: Sub 10.10.2026. 19:00 (pretpostavljeno trajanje 1 sat)", "Lokacija: Restoran Delfi",
            "Opis: Poklon nije obavezan", "", "Da li da upišem u kalendar?"])

    def test_kraj_bez_pretpostavke(self):
        event = {**TIMED, "end_assumed": False}
        self.assertIn("Kraj: Sub 10.10.2026. 19:00\n", tp.format_proposal(event, "x"))

    def test_ceo_dan_vise_dana_sa_napomenom(self):
        text = tp.format_proposal(ALL_DAY, "Upisano.")
        self.assertIn("Datum: Sub 17.10.2026. (ceo dan)", text)
        self.assertIn("Do: Ned 18.10.2026.", text)
        self.assertIn("⚠️ Napomena: Vreme nije pronađeno", text)
        self.assertNotIn("Lokacija", text)
        self.assertNotIn("Opis", text)
        self.assertTrue(text.endswith("\n\nUpisano."))

    def test_ceo_dan_jedan_dan_nema_do(self):
        self.assertNotIn("Do:", tp.format_proposal({**ALL_DAY, "end": "2026-10-17"}, "x"))


class PendingStoreTest(unittest.TestCase):
    def setUp(self):
        tp.clear()
        self.addCleanup(tp.clear)

    def test_dodavanje_i_dohvatanje(self):
        pid = tp.add(111, TIMED)
        entry = tp.get(pid)
        self.assertEqual((entry["chat_id"], entry["event"]), (111, TIMED))
        self.assertTrue(tp.has(pid))

    def test_id_staje_u_callback_data_i_jedinstven_je(self):
        ids = {tp.add(1, TIMED) for _ in range(50)}
        self.assertEqual(len(ids), 50)
        self.assertTrue(all(len(f"y:{pid}".encode()) <= 64 and ":" not in pid for pid in ids))   # ograničenje Telegrama

    def test_uklanjanje_i_vracanje(self):
        pid = tp.add(1, TIMED)
        entry = tp.get(pid)
        tp.remove(pid)
        self.assertFalse(tp.has(pid))
        tp.restore(pid, entry)
        self.assertEqual(tp.get(pid), entry)

    def test_nepoznat_id(self):
        self.assertIsNone(tp.get("nema"))
        self.assertFalse(tp.has("nema"))

    def test_istekli_predlozi_se_brisu(self):
        with mock.patch.object(tp.time, "time", return_value=1000.0):
            old = tp.add(1, TIMED)
        with mock.patch.object(tp.time, "time", return_value=1000.0 + tp.PENDING_TTL_SECONDS + 1):
            fresh = tp.add(1, TIMED)   # dodavanje čisti istekle
        self.assertFalse(tp.has(old))
        self.assertTrue(tp.has(fresh))

    def test_ogranicen_broj_predloga_izbacuje_najstariji(self):
        with mock.patch.object(tp, "MAX_PENDING", 3):
            ids = []
            for i in range(5):
                with mock.patch.object(tp.time, "time", return_value=1000.0 + i):
                    ids.append(tp.add(1, TIMED))
        self.assertEqual(sum(tp.has(pid) for pid in ids), 3)   # nikad više od MAX_PENDING
        self.assertFalse(tp.has(ids[0]))
        self.assertTrue(all(tp.has(pid) for pid in ids[-3:]))


if __name__ == "__main__":
    unittest.main()
