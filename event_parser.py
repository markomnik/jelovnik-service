"""
Parsiranje pozivnice (tekst i/ili slika) u parametre kalendarskog događaja.

parse_event(text=None, image=None) vraća rečnik spreman za upis u kalendar:
    {"title", "all_day", "start", "end", "location", "description", "notes", "end_assumed"}

    start / end:  "YYYY-MM-DDTHH:MM" (lokalno vreme, Europe/Belgrade),
                  ili "YYYY-MM-DD" za događaj celog dana.
                  Kod događaja celog dana "end" je POSLEDNJI dan (uključivo).

Ovaj modul samo povezuje delove:
    event_image.py      slika -> polja (freeocr.ai /extract, rezerva /ocr)
    event_text.py       tekst -> polja (pravila za srpski jezik), uz event_datetime.py
    event_fields.py     spajanje polja iz više izvora
    event_normalize.py  provera polja i računanje početka/kraja
    event_errors.py     ParseError (poruka se sme prikazati korisniku)

Potrebna varijabla za slike: FREEOCR_API_KEY (vidi freeocr_client.py).
Modul ne zavisi od Flask-a.
"""

from datetime import datetime

from config import TZ
from event_errors import ParseError
from event_fields import merge_fields
from event_image import from_image
from event_normalize import normalize_event
from event_text import from_text
from freeocr_client import FreeOCRError

__all__ = ["ParseError", "parse_event"]

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _ocr_error_message(error: FreeOCRError) -> str | None:
    """Poruka za korisnika za greške OCR servisa koje on može da razume (None: nepoznata greška)."""
    if error.status is None:
        return "OCR servis nije podešen na serveru (FREEOCR_API_KEY)."
    return {
        402: "OCR servis nema dovoljno kredita. Dopuni balans na freeocr.ai.",
        401: "OCR servis je odbio ključ (FREEOCR_API_KEY).",
        429: "OCR servis je trenutno preopterećen. Pokušaj za minut.",
    }.get(error.status)


def parse_event(text: str | None = None, image: tuple[bytes, str] | None = None) -> dict:
    """text: tekst pozivnice (ili opis uz sliku); image: (bajtovi, media_type)."""
    text = (text or "").strip()
    if not text and not image:
        raise ParseError("Nema ničega za parsiranje. Pošalji tekst ili sliku pozivnice.")
    if image:
        data, media_type = image
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ParseError("Format slike nije podržan (JPEG, PNG ili WEBP).")
        if len(data) > MAX_IMAGE_BYTES:
            raise ParseError("Slika je prevelika (najviše 5 MB).")

    today = datetime.now(TZ).date()
    try:
        raw = from_image(image, today) if image else {}
    except FreeOCRError as e:
        message = _ocr_error_message(e)
        if message is None:
            raise   # ostale greške idu u log, korisnik dobija opštu poruku
        raise ParseError(message) from None
    if text:
        raw = merge_fields(raw, from_text(text, today))   # opis uz sliku popunjava ono što na slici nedostaje
    return normalize_event(raw)
