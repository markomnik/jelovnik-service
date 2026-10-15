import unittest
from unittest import mock

import menu_table as mt
from tests.support import EXPECTED_TUESDAY, MENU_TABLE_HTML, MENU_TABLE_RESPONSE, FakeResponse, patch_env


class GridToMenuTest(unittest.TestCase):
    def test_dani_su_redovi_obroci_su_kolone(self):
        menu = mt.grid_to_menu(mt.html_table_to_grid(MENU_TABLE_HTML))
        self.assertEqual(menu["Utorak"], EXPECTED_TUESDAY)
        self.assertEqual(list(menu), ["Ponedeljak", "Utorak", "Sreda", "Četvrtak", "Petak"])

    def test_ceo_tekst_je_latinica_a_zagrade_ostaju(self):
        menu = mt.grid_to_menu(mt.html_table_to_grid(MENU_TABLE_HTML))
        self.assertEqual(menu["Ponedeljak"]["dorucak"], "Jogurt (gluten)")

    def test_dani_su_kolone_obroci_su_redovi(self):
        grid = [["", "Ponedeljak", "Utorak"],
                ["Doručak", "Jogurt", "Čaj"],
                ["Ručak", "Čorba", "Špagete"]]
        menu = mt.grid_to_menu(grid)
        self.assertEqual(menu["Utorak"]["dorucak"], "Čaj")
        self.assertEqual(menu["Ponedeljak"]["rucak"], "Čorba")

    def test_dani_su_kolone_cirilica_postaje_latinica(self):
        grid = [["", "Понедељак", "Уторак"],
                ["Доручак", "Јогурт (глутен)", "Чај са лимуном"],
                ["Ручак", "Чорба", "Шпагете"]]
        menu = mt.grid_to_menu(grid)
        self.assertEqual(menu["Ponedeljak"]["dorucak"], "Jogurt (gluten)")
        self.assertEqual(menu["Utorak"]["rucak"], "Špagete")

    def test_zaglavlja_bez_dijakritika(self):
        grid = [["dan", "dorucak", "voce", "uzina", "rucak"], ["cetvrtak", "a", "b", "c", "d"]]
        self.assertEqual(mt.grid_to_menu(grid)["Četvrtak"], {"dorucak": "a", "voce": "b", "uzina": "c", "rucak": "d"})

    def test_nepoznat_raspored(self):
        with self.assertRaises(ValueError):
            mt.grid_to_menu([["a", "b"], ["c", "d"]])

    def test_prazna_ili_prekratka_tabela(self):
        for grid in ([], [["Ponedeljak"]]):
            with self.assertRaises(ValueError):
                mt.grid_to_menu(grid)


class ResponseTest(unittest.TestCase):
    def test_bira_najvecu_tabelu(self):
        # druga tabela na slici (nutritivne vrednosti) je manja i ne sme da pobedi
        self.assertEqual(mt.menu_from_table_response(MENU_TABLE_RESPONSE)["Utorak"], EXPECTED_TUESDAY)

    def test_nema_tabela(self):
        with self.assertRaises(ValueError):
            mt.menu_from_table_response({"tables": []})

    def test_extract_salje_sliku_freeocr_servisu(self):
        patch_env(self, FREEOCR_API_KEY="focr_test")
        with mock.patch("freeocr_client.requests.post", return_value=FakeResponse(200, MENU_TABLE_RESPONSE)) as post:
            menu = mt.extract_menu_table(b"\xff\xd8\xff")
        self.assertEqual(menu["Utorak"], EXPECTED_TUESDAY)
        self.assertTrue(post.call_args.args[0].endswith("/table"))
        self.assertEqual(post.call_args.kwargs["params"], {"format": "json"})


if __name__ == "__main__":
    unittest.main()
