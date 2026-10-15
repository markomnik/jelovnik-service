"""Ko sme da koristi bota: spiskovi korisnika i čatova iz environment varijabli."""

import os
import re


def id_set(name: str) -> set[int]:
    raw = os.environ.get(name, "")
    return {int(x) for x in re.split(r"[,\s]+", raw) if re.fullmatch(r"-?\d+", x)}


def is_authorized(chat_id: int | None, user_id: int | None) -> bool:
    """
    Da li korisnik sme da šalje pozivnice i potvrđuje upis u kalendar.

    TELEGRAM_ALLOWED_USER_IDS podešen:  korisnik mora da bude na spisku (a ako je podešen i
                                        TELEGRAM_ALLOWED_CHAT_IDS, i čat mora da bude na spisku).
    TELEGRAM_ALLOWED_USER_IDS prazan:   važi samo spisak čatova (TELEGRAM_ALLOWED_CHAT_IDS).
    """
    users = id_set("TELEGRAM_ALLOWED_USER_IDS")
    chats = id_set("TELEGRAM_ALLOWED_CHAT_IDS")
    if users:
        return user_id in users and (not chats or chat_id in chats)
    return chat_id in chats
