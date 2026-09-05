"""SharePoint file content extraction with the same size/type limits as Drive."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SKIP_FOLDER = True
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
MAX_EXTRACTED_CHARS = 500_000

SKIP_MIME_TYPES = {
    "application/vnd.ms-outlook",
}


def is_folder(item: Dict[str, Any]) -> bool:
    if item.get("folder") is not None:
        return True
    mime = _mime(item)
    return mime in {"application/vnd.ms-folder", "inode/directory"}


def _mime(item: Dict[str, Any]) -> str:
    file_obj = item.get("file") or {}
    return str(item.get("mimeType") or file_obj.get("mimeType") or "")


def _extension(item: Dict[str, Any]) -> str:
    name = str(item.get("name") or "")
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return str(item.get("file_extension") or "")


async def extract_sharepoint_text(graph_client, access_token: str, item: Dict[str, Any]) -> str:
    """Download (when needed) and extract plain text. Caps at 15MB / 500k chars."""
    injected = item.get("_extracted_text") or item.get("_test_extracted_text")
    if isinstance(injected, str) and injected.strip():
        return injected[:MAX_EXTRACTED_CHARS]

    name = str(item.get("name") or "")
    if is_folder(item):
        return name

    mime = _mime(item)
    if mime in SKIP_MIME_TYPES:
        return name

    size = int(item.get("size") or 0)
    if size > MAX_DOWNLOAD_BYTES:
        logger.info("Skipping oversized SharePoint file %s (%s bytes)", item.get("id"), size)
        return name

    drive_id = item.get("_drive_id") or (item.get("parentReference") or {}).get("driveId") or ""
    raw_id = str(item.get("id") or "")
    item_id = raw_id.split(":")[-1] if ":" in raw_id else raw_id
    if not drive_id or not item_id:
        return name

    try:
        blob = await graph_client.download_content(access_token, drive_id, item_id)
        if not blob:
            return name
        if mime.startswith("text/") or _extension(item) in {"txt", "md", "csv", "json"}:
            text = blob.decode("utf-8", errors="ignore") if isinstance(blob, bytes) else str(blob)
            extracted = text[:MAX_EXTRACTED_CHARS]
            logger.info(
                "SharePoint extracted file=%s chars=%s snippet=%s",
                name,
                len(extracted),
                extracted[:180].replace("\n", " "),
            )
            return extracted
        extracted = await _extract_binary(blob, mime, _extension(item)) or name
        logger.info(
            "SharePoint extracted file=%s mime=%s chars=%s snippet=%s",
            name,
            mime,
            len(extracted or ""),
            (extracted or "")[:180].replace("\n", " "),
        )
        return extracted
    except Exception as exc:
        logger.warning("SharePoint content extract failed for %s: %s", raw_id, type(exc).__name__)
        return name


async def _extract_binary(content_bytes: bytes, mime_type: str, file_extension: Optional[str]) -> str:
    try:
        from app.normalizer.ocr import FakeOCRService
        from app.normalizer.text_extractor import TextExtractor

        extractor = TextExtractor(FakeOCRService(), max_chars=MAX_EXTRACTED_CHARS)
        text = await extractor.extract(content_bytes, mime_type, file_extension)
        return (text or "")[:MAX_EXTRACTED_CHARS]
    except Exception as exc:
        logger.warning("SharePoint binary text extraction failed: %s", type(exc).__name__)
        try:
            return content_bytes.decode("utf-8", errors="ignore")[:MAX_EXTRACTED_CHARS]
        except Exception:
            return ""
