import unittest
from datetime import date

import event_fields as ef


def found(day, inferred=False):
    return {"date": day, "start": 0, "end": 0, "inferred_year": inferred, "rel": None}


class MergeFieldsTest(unittest.TestCase):
    def test_popunjava_samo_ono_sto_fali(self):
        merged = ef.merge_fields({"title": "Slava", "location": ""}, {"title": "Drugo", "location": "Hotel", "start_date": "2026-10-10"})
        self.assertEqual(merged, {"title": "Slava", "location": "Hotel", "start_date": "2026-10-10"})

    def test_beleske_se_spajaju(self):
        self.assertEqual(ef.merge_fields({"notes": "a"}, {"notes": "b"})["notes"], "a b")
        self.assertEqual(ef.merge_fields({}, {"notes": "b"})["notes"], "b")
        self.assertEqual(ef.merge_fields({"notes": "a"}, {})["notes"], "a")

    def test_ne_menja_ulazne_recnike(self):
        primary, fallback = {"title": "A"}, {"title": "B", "notes": "n"}
        ef.merge_fields(primary, fallback)
        self.assertEqual((primary, fallback), ({"title": "A"}, {"title": "B", "notes": "n"}))


class ApplyDatesTest(unittest.TestCase):
    def apply(self, dates):
        raw, notes = {}, []
        ef.apply_dates(raw, notes, dates)
        return raw, notes

    def test_bez_datuma_nista_se_ne_upisuje(self):
        self.assertEqual(self.apply([]), ({}, []))

    def test_jedan_datum(self):
        self.assertEqual(self.apply([found(date(2026, 10, 10))]), ({"start_date": "2026-10-10"}, []))

    def test_kraj_je_prvi_kasniji_razlicit_datum(self):
        raw, _ = self.apply([found(date(2026, 10, 10)), found(date(2026, 10, 10)), found(date(2026, 10, 9)), found(date(2026, 10, 12))])
        self.assertEqual((raw["start_date"], raw["end_date"]), ("2026-10-10", "2026-10-12"))

    def test_pretpostavljena_godina_ostavlja_napomenu(self):
        _, notes = self.apply([found(date(2027, 3, 5), inferred=True)])
        self.assertEqual(notes, ["Godina nije navedena, pretpostavljena 2027."])


class CapitalizeTest(unittest.TestCase):
    def test_prvo_slovo(self):
        self.assertEqual(ef.capitalize_first("rođendan kod Mile"), "Rođendan kod Mile")
        self.assertEqual(ef.capitalize_first("šljiva"), "Šljiva")
        self.assertEqual(ef.capitalize_first(""), "")


if __name__ == "__main__":
    unittest.main()
