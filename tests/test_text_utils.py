import unittest

from text_utils import cyr_to_lat


class CyrToLatTest(unittest.TestCase):
    def test_osnovna_slova_i_dijakritici(self):
        self.assertEqual(cyr_to_lat("Ђорђе је шћућурио чорбу"), "Đorđe je šćućurio čorbu")

    def test_digrafi(self):
        self.assertEqual(cyr_to_lat("Љубав џем њушка"), "Ljubav džem njuška")

    def test_ostalo_ostaje_nepromenjeno(self):
        self.assertEqual(cyr_to_lat("Čaj 12.10. (gluten), hleb"), "Čaj 12.10. (gluten), hleb")

    def test_prazan_tekst(self):
        self.assertEqual(cyr_to_lat(""), "")
        self.assertIsNone(cyr_to_lat(None))


if __name__ == "__main__":
    unittest.main()
