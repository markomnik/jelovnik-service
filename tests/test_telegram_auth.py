import unittest

from telegram_auth import id_set, is_authorized
from tests.support import patch_env


class IdSetTest(unittest.TestCase):
    def test_razdvajanje_i_ciscenje(self):
        patch_env(self, X_IDS="111, 222  -333,abc,,4x4")
        self.assertEqual(id_set("X_IDS"), {111, 222, -333})

    def test_nepodesena_varijabla(self):
        patch_env(self, X_IDS=None)
        self.assertEqual(id_set("X_IDS"), set())


class IsAuthorizedTest(unittest.TestCase):
    def configure(self, users="", chats=""):
        patch_env(self, TELEGRAM_ALLOWED_USER_IDS=users, TELEGRAM_ALLOWED_CHAT_IDS=chats)

    def test_samo_spisak_korisnika(self):
        self.configure(users="1,2")
        self.assertTrue(is_authorized(chat_id=1, user_id=1))
        self.assertTrue(is_authorized(chat_id=-100, user_id=2))   # grupa: važi korisnik
        self.assertFalse(is_authorized(chat_id=3, user_id=3))
        self.assertFalse(is_authorized(chat_id=1, user_id=None))

    def test_oba_spiska_moraju_da_se_poklope(self):
        self.configure(users="1", chats="-100")
        self.assertTrue(is_authorized(chat_id=-100, user_id=1))
        self.assertFalse(is_authorized(chat_id=1, user_id=1))      # korisnik jeste, čat nije
        self.assertFalse(is_authorized(chat_id=-100, user_id=2))   # čat jeste, korisnik nije

    def test_samo_spisak_cetova(self):
        self.configure(chats="1")
        self.assertTrue(is_authorized(chat_id=1, user_id=999))
        self.assertFalse(is_authorized(chat_id=2, user_id=1))

    def test_bez_spiskova_niko_nema_pristup(self):
        self.configure()
        self.assertFalse(is_authorized(chat_id=1, user_id=1))
        self.assertFalse(is_authorized(chat_id=None, user_id=None))


if __name__ == "__main__":
    unittest.main()
