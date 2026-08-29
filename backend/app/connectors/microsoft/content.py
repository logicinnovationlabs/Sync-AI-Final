"""OneDrive binary → plain text extraction."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
SKIP_FOLDER = True


async def extract_onedrive_text(
    graph_client,
    access_token: str,
    item: Dict[str, Any],
) -> str:
    """Download a OneDrive file and extract searchable text."""
    name = str(item.get("name") or "")
    item_id = str(item.get("id") or "")
    if not item_id:
        return name
    if item.get("folder") is not None:
        return name

    size = int(item.get("size") or 0)
    if size > MAX_DOWNLOAD_BYTES:
        logger.info("Skipping oversized OneDrive file %s (%s bytes)", item_id, size)
        return name

    mime = ""
    file_facet = item.get("file") if isinstance(item.get("file"), dict) else {}
    mime = str(file_facet.get("mimeType") or item.get("mimeType") or "")
    ext = ""
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()

    try:
        blob = await graph_client.download_drive_item(access_token, item_id)
    except Exception as exc:
        logger.warning("OneDrive download failed for %s: %s", item_id, type(exc).__name__)
        return name

    if not blob:
        return name

    try:
        from app.normalizer.ocr import OCRService
        from app.normalizer.text_extractor import TextExtractor

        extractor = TextExtractor(OCRService(), max_chars=500_000)
        text = await extractor.extract(blob, mime or "application/octet-stream", ext)
        if (text or "").strip():
            return text
    except Exception as exc:
        logger.warning("OneDrive text extract failed: %s", type(exc).__name__)
        try:
            return blob.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return name
