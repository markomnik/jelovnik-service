"""
Zajednički klijent za freeocr.ai API. Koriste ga čitanje jelovnika (app.py)
i parsiranje pozivnica (event_parser.py), da se poziv ka OCR servisu ne duplira.

Endpointi (https://freeocr.ai/platform/docs):
    table    slika -> tabele (HTML)
    ocr      slika -> tekst
    extract  slika -> tražena polja (parametar fields)

Potrebna varijabla: FREEOCR_API_KEY
"""

import os

import requests

BASE_URL = "https://freeocr.ai/api/v1/platform"
_FILENAMES = {"image/jpeg": "slika.jpg", "image/png": "slika.png", "image/webp": "slika.webp"}


class FreeOCRError(Exception):
    """Greška freeocr.ai servisa. status je None kad ključ uopšte nije podešen."""

    def __init__(self, status: int | None, code: str, message: str):
        super().__init__(f"freeocr.ai {status or ''} {code}: {message}".replace("  ", " "))
        self.status, self.code, self.message = status, code, message


def _api_key() -> str | None:
    return (os.environ.get("FREEOCR_API_KEY") or "").strip() or None


def is_configured() -> bool:
    return _api_key() is not None


def request(endpoint: str, image_bytes: bytes, media_type: str = "image/jpeg",
            params: dict | None = None, timeout: int = 60) -> requests.Response:
    """Sirov poziv: ne baca grešku za HTTP status (koristi ga i /debug-ocr da vidi tačan odgovor)."""
    key = _api_key()
    if not key:
        raise FreeOCRError(None, "not_configured", "FREEOCR_API_KEY nije podešen u environment varijablama.")
    return requests.post(
        f"{BASE_URL}/{endpoint}",
        headers={"Authorization": f"Bearer {key}"},
        params=params,
        files={"image": (_FILENAMES.get(media_type, "slika.jpg"), image_bytes, media_type)},
        timeout=timeout,
    )


def post_json(endpoint: str, image_bytes: bytes, media_type: str = "image/jpeg",
              params: dict | None = None, timeout: int = 60) -> dict:
    """Poziv koji vraća JSON odgovor ili baca FreeOCRError sa porukom koju je poslao servis."""
    resp = request(endpoint, image_bytes, media_type, params, timeout)
    if not resp.ok:
        error = {}
        try:
            body = resp.json()
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                error = body["error"]
        except ValueError:
            pass
        raise FreeOCRError(resp.status_code, error.get("code") or "http_error",
                           error.get("message") or resp.text[:200])
    return resp.json()
