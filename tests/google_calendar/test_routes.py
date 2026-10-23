import unittest
from datetime import datetime, timedelta
from unittest import mock

from google_calendar import routes as cr
from tests.support import FakeResponse, make_client, patch_env


def today_midnight():
    return datetime.now(cr.TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def timed(title, start, end, **extra):
    return {"summary": title, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}, **extra}


def all_day(title, first, last_exclusive):
    return {"summary": title, "start": {"date": first.date().isoformat()}, "end": {"date": last_exclusive.date().isoformat()}}


class BuildDaysTest(unittest.TestCase):
    def setUp(self):
        self.today = today_midnight()

    def days(self, events):
        return cr._build_days(self.today, events)

    def test_cetiri_dana_sa_oznakama(self):
        days = self.days([])
        self.assertEqual(len(days), 4)
        self.assertEqual([d["label"] for d in days[:2]], ["Danas", "Sutra"])
        self.assertEqual(days[3]["label"], f"{['Pon','Uto','Sre','Čet','Pet','Sub','Ned'][(self.today + timedelta(days=3)).weekday()]} "
                                           f"{(self.today + timedelta(days=3)).day}.{(self.today + timedelta(days=3)).month}.")

    def test_dogadjaj_sa_vremenom_i_lokacijom(self):
        start = self.today + timedelta(days=1, hours=10)
        days = self.days([timed("Test", start, start + timedelta(hours=1), location="kod kuće")])
        self.assertEqual(days[0]["events"], [])
        self.assertEqual(days[1]["events"], [{"title": "Test", "location": "kod kuće", "allDay": False, "time": "10:00", "continues": False}])

    def test_dogadjaj_preko_ponoci_se_nastavlja_sutradan(self):
        start = self.today + timedelta(days=2, hours=22)
        days = self.days([timed("Žurka", start, start + timedelta(hours=3))])
        self.assertEqual((days[2]["events"][0]["time"], days[2]["events"][0]["continues"]), ("22:00", False))
        self.assertEqual((days[3]["events"][0]["time"], days[3]["events"][0]["continues"]), ("", True))

    def test_vise_dana_za_ceo_dan(self):
        first = self.today + timedelta(days=2)
        days = self.days([all_day("Izlet", first, first + timedelta(days=2))])
        self.assertEqual([len(d["events"]) for d in days], [0, 0, 1, 1])
        self.assertTrue(days[2]["events"][0]["allDay"])
        self.assertEqual(days[2]["events"][0]["time"], "")

    def test_dogadjaj_bez_naslova(self):
        start = self.today + timedelta(hours=9)
        self.assertEqual(self.days([timed("", start, start + timedelta(hours=1))])[0]["events"][0]["title"], "(bez naziva)")


class CreateEventTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, GOOGLE_CALENDAR_ID=None)
        self.post = mock.patch.object(cr.requests, "post", return_value=FakeResponse(200, {"htmlLink": "https://cal/x"}))
        self.token = mock.patch.object(cr, "_get_access_token", return_value="tok")
        self.post_mock, _ = self.post.start(), self.token.start()
        self.addCleanup(self.post.stop)
        self.addCleanup(self.token.stop)

    def body(self):
        return self.post_mock.call_args.kwargs["json"]

    def test_dogadjaj_sa_vremenom(self):
        result = cr.create_event({"title": "Rođendan", "all_day": False, "start": "2026-10-10T18:00", "end": "2026-10-10T19:00",
                                  "location": "Restoran X", "description": "Poklon"})
        self.assertEqual(result["htmlLink"], "https://cal/x")
        self.assertTrue(self.post_mock.call_args.args[0].endswith("/calendars/primary/events"))
        self.assertEqual(self.body(), {
            "summary": "Rođendan", "location": "Restoran X", "description": "Poklon",
            "start": {"dateTime": "2026-10-10T18:00:00", "timeZone": "Europe/Belgrade"},
            "end": {"dateTime": "2026-10-10T19:00:00", "timeZone": "Europe/Belgrade"}})

    def test_ceo_dan_ima_iskljuciv_kraj(self):
        cr.create_event({"title": "Izlet", "all_day": True, "start": "2026-10-17", "end": "2026-10-18", "location": "", "description": ""})
        self.assertEqual(self.body(), {"summary": "Izlet", "start": {"date": "2026-10-17"}, "end": {"date": "2026-10-19"}})

    def test_kes_se_ponistava(self):
        cr._cache.update(data={"stale": True}, ts=1.0, day="2026-10-09")
        cr.create_event({"title": "X", "all_day": True, "start": "2026-10-17", "end": "2026-10-17"})
        self.assertIsNone(cr._cache["data"])


class CalendarRouteTest(unittest.TestCase):
    def setUp(self):
        cr._cache.update(data=None, ts=0.0, day=None)
        self.addCleanup(lambda: cr._cache.update(data=None, ts=0.0, day=None))
        patch_env(self, GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="s", GOOGLE_REFRESH_TOKEN="r")
        self.client = make_client()

    def test_nije_podeseno(self):
        patch_env(self, GOOGLE_REFRESH_TOKEN=None)
        resp = self.client.get("/calendar/next-days")
        self.assertEqual(resp.status_code, 503)

    def test_odgovor_i_kes(self):
        start = today_midnight() + timedelta(days=1, hours=10)
        with mock.patch.object(cr, "_fetch_events", return_value=[timed("Test", start, start + timedelta(hours=1))]) as fetch:
            first = self.client.get("/calendar/next-days").get_json()
            self.client.get("/calendar/next-days")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["days"][1]["events"][0]["title"], "Test")

    def test_greska_google_a_bez_kesa(self):
        with mock.patch.object(cr, "_fetch_events", side_effect=RuntimeError("pao")), \
             self.assertLogs("app", level="ERROR"):
            resp = self.client.get("/calendar/next-days")
        self.assertEqual((resp.status_code, resp.get_json()), (502, {"greska": "Kalendar trenutno nije dostupan."}))

    def test_greska_google_a_sa_starim_kesom(self):
        with mock.patch.object(cr, "_fetch_events", return_value=[]):
            self.client.get("/calendar/next-days")
        cr._cache["ts"] = 0.0   # keš je istekao, ali je isti dan
        with mock.patch.object(cr, "_fetch_events", side_effect=RuntimeError("pao")), \
             self.assertLogs("app", level="ERROR"):
            body = self.client.get("/calendar/next-days").get_json()
        self.assertTrue(body["stale"])
        self.assertEqual(len(body["days"]), 4)

    def test_kes_ne_prelazi_u_novi_dan(self):
        with mock.patch.object(cr, "_fetch_events", return_value=[]) as fetch:
            self.client.get("/calendar/next-days")
            cr._cache["day"] = "2000-01-01"   # keš je od juče
            self.client.get("/calendar/next-days")
        self.assertEqual(fetch.call_count, 2)


class AccessTokenTest(unittest.TestCase):
    def setUp(self):
        patch_env(self, GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="s", GOOGLE_REFRESH_TOKEN="r")
        cr._token.update(value=None, exp=0.0)
        self.addCleanup(lambda: cr._token.update(value=None, exp=0.0))

    def test_token_se_osvezava_i_kesira(self):
        with mock.patch.object(cr.requests, "post", return_value=FakeResponse(200, {"access_token": "AT", "expires_in": 3600})) as post:
            self.assertEqual(cr._get_access_token(), "AT")
            self.assertEqual(cr._get_access_token(), "AT")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")


if __name__ == "__main__":
    unittest.main()
