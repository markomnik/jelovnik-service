"""Health provera i dijagnostički endpointi (Flask Blueprint)."""

from flask import Blueprint, jsonify

import freeocr_client
import menu_service
import menu_table
from extensions import limiter
from menu_scraper import (BASE_URL, ImgFinder, LinkFinder, download_image_bytes, fetch_html,
                          pick_jelovnik_url)
from security import require_admin

admin_bp = Blueprint("admin", __name__)


def _json_or_text(resp):
    if resp.headers.get("content-type", "").startswith("application/json"):
        return resp.json()
    return resp.text[:2000]


@admin_bp.route("/")
def health():
    return {"status": "ok", "cached_url": menu_service.cached_url()}


@admin_bp.route("/debug-ocr")
@require_admin
@limiter.limit("5 per hour")
def debug_ocr():
    """Sirov odgovor freeocr.ai-ja i rezultat mapiranja, za dijagnostiku (jedan OCR poziv)."""
    out = {"provider": "freeocr"}
    try:
        url = menu_service.resolve_cached_url()
        out["image_url"] = url
        if not url:
            return jsonify({**out, "greska": "Jelovnik slika trenutno nije pronađena."}), 404

        img_bytes = download_image_bytes(url)
        out["image_bytes_len"] = len(img_bytes)
        out["image_magic_hex"] = img_bytes[:8].hex()
        out["looks_like_jpeg"] = img_bytes[:3] == b"\xff\xd8\xff"
        if not out["looks_like_jpeg"]:
            out["first_200_bytes_as_text"] = img_bytes[:200].decode("utf-8", errors="replace")

        if not freeocr_client.is_configured():
            return jsonify({"greska": "FREEOCR_API_KEY nije podešen."}), 500
        resp = freeocr_client.request("table", img_bytes, "image/jpeg", params={"format": "json"})
        out["status_code"] = resp.status_code
        out["raw_response"] = _json_or_text(resp)
        if resp.ok:
            try:
                out["mapped"] = menu_table.menu_from_table_response(resp.json())
            except Exception as e:
                out["mapping_error"] = str(e)
        else:
            out["mapping_error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return jsonify(out)


@admin_bp.route("/debug")
@require_admin
def debug():
    """Šta server stvarno vidi na sajtu vrtića - korisno ako scraping ne uspe."""
    out = {"base_url": BASE_URL}
    try:
        html = fetch_html(BASE_URL)
        out["homepage_len"] = len(html)
        parser = LinkFinder()
        parser.feed(html)
        out["homepage_link_count"] = len(parser.links)
        out["links_sample"] = [text for _, text in parser.links if text][:40]
        jelovnik_url = pick_jelovnik_url(parser.links)
        out["jelovnik_page_url"] = jelovnik_url

        if jelovnik_url:
            page_html = fetch_html(jelovnik_url)
            out["jelovnik_page_len"] = len(page_html)
            img_parser = ImgFinder()
            img_parser.feed(page_html)
            out["img_srcs"] = img_parser.imgs[:40]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out
