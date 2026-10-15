import unittest
from unittest import mock

import menu_scraper as sc

HOME = ('<html><a href="/?page_id=1">Kontakt</a>'
        '<a href="/?page_id=7054"><span>Јеловник</span></a></html>')
IMG_VRTIC = "http://www.pudecjidani.rs/wp-content/uploads/2026/10/Јеловник-вртић-05-09.10.2026.-ПУ-Дечји-дани.jpg"
IMG_JASLE = "http://www.pudecjidani.rs/wp-content/uploads/2026/10/Јеловник-јасле-05-09.10.2026.-ПУ-Дечји-дани.jpg"


class LinkTest(unittest.TestCase):
    def parse(self, html):
        parser = sc.LinkFinder()
        parser.feed(html)
        return parser.links

    def test_tekst_linka_unutar_ugnjezdenog_taga(self):
        self.assertIn(("/?page_id=7054", "Јеловник"), self.parse(HOME))

    def test_tacan_tekst_ima_prednost(self):
        links = [("/a", "Stari Јеловник arhiva"), ("/b", "Јеловник")]
        self.assertEqual(sc.pick_jelovnik_url(links), "https://www.pudecjidani.rs/b")

    def test_rezerva_je_tekst_koji_sadrzi_rec(self):
        self.assertEqual(sc.pick_jelovnik_url([("/a", "Наш Јеловник")]), "https://www.pudecjidani.rs/a")

    def test_nema_linka(self):
        self.assertIsNone(sc.pick_jelovnik_url([("/a", "Kontakt")]))

    def test_link_bez_href_se_preskace(self):
        self.assertIsNone(sc.pick_jelovnik_url([("", "Јеловник")]))


class ImageTest(unittest.TestCase):
    def test_img_i_lazy_load(self):
        parser = sc.ImgFinder()
        parser.feed('<img src="/a.jpg"><img data-src="/b.jpg"><img alt="bez izvora">')
        self.assertEqual(parser.imgs, ["/a.jpg", "/b.jpg"])

    def test_slika_se_trazi_bez_obzira_na_velika_mala_slova(self):
        # na sajtu piše malim slovima "вртић", a konstanta je "Вртић" (ranije greška)
        url = sc.pick_vrtic_image_url(["/logo.jpg", IMG_JASLE, IMG_VRTIC], "https://www.pudecjidani.rs/?page_id=7054")
        self.assertIn("%D0%B2%D1%80%D1%82%D0%B8%D1%9B", url)   # vrtić, percent-enkodovano
        self.assertNotIn("%D1%98%D0%B0%D1%81%D0%BB%D0%B5", url)  # ne uzima jasle

    def test_url_je_ascii_bezbedan(self):
        url = sc.pick_vrtic_image_url([IMG_VRTIC], "https://www.pudecjidani.rs/")
        url.encode("ascii")   # ne sme da baci grešku

    def test_nema_slike(self):
        self.assertIsNone(sc.pick_vrtic_image_url(["/logo.jpg"], "https://www.pudecjidani.rs/"))

    def test_relativna_putanja_se_dopunjuje(self):
        url = sc.pick_vrtic_image_url(["/wp-content/Јеловник-вртић.jpg"], "https://www.pudecjidani.rs/?page_id=7054")
        self.assertTrue(url.startswith("https://www.pudecjidani.rs/wp-content/"))


class FindTest(unittest.TestCase):
    def test_ceo_tok_pronalazenja_slike(self):
        pages = {sc.BASE_URL: HOME,
                 "https://www.pudecjidani.rs/?page_id=7054": f'<img src="{IMG_JASLE}"><img src="{IMG_VRTIC}">'}
        with mock.patch.object(sc, "fetch_html", side_effect=lambda url: pages[url]):
            url = sc.find_vrtic_image_url()
        self.assertTrue(url.startswith("http://www.pudecjidani.rs/wp-content/uploads/2026/10/"))
        self.assertIn("%D0%B2%D1%80%D1%82%D0%B8%D1%9B", url)

    def test_bez_linka_nema_ni_zahteva_za_stranicu(self):
        with mock.patch.object(sc, "fetch_html", return_value="<html></html>") as fetch:
            self.assertIsNone(sc.find_vrtic_image_url())
        fetch.assert_called_once_with(sc.BASE_URL)


class QuoteUrlTest(unittest.TestCase):
    def test_cirilica_u_putanji(self):
        self.assertEqual(sc.quote_url("http://x.rs/a/Јеловник.jpg"), "http://x.rs/a/%D0%88%D0%B5%D0%BB%D0%BE%D0%B2%D0%BD%D0%B8%D0%BA.jpg")

    def test_vec_enkodovan_url_se_ne_menja(self):
        url = "http://x.rs/a/%D0%88.jpg?x=1&y=2"
        self.assertEqual(sc.quote_url(url), url)


if __name__ == "__main__":
    unittest.main()
