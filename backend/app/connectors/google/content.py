"""
Drive file content extraction: Google-native export + binary download.

Attaches extracted text onto the raw Drive file object as `_extracted_text`
so Block C's GoogleDriveNormalizer can consume it without owning API calls.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SKIP_MIME_TYPES = {
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.shortcut",
}

GOOGLE_EXPORT_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
    

async def extract_drive_text(
    drive_client,
    access_token: str,
    file_obj: Dict[str, Any],
) -> str:
    """Export or download a Drive file and return extracted plain text."""
    mime = file_obj.get("mimeType") or ""
    file_id = file_obj.get("id") or ""
    name = file_obj.get("name") or ""
    if not file_id or mime in SKIP_MIME_TYPES:
        return name

    try:
        if mime in GOOGLE_EXPORT_MAP:
            data = await drive_client.export_file(
                access_token, file_id, GOOGLE_EXPORT_MAP[mime]
            )
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="ignore")
            return str(data or name)

        size = int(file_obj.get("size") or 0)
        if size > MAX_DOWNLOAD_BYTES:
            logger.info("Skipping oversized Drive file %s (%s bytes)", file_id, size)
            return name

        blob = await drive_client.download_file(access_token, file_id)
        if not blob:
            logger.warning("Drive download empty for %s (%s)", file_id, name)
            return name
        text = await _extract_binary(blob, mime, file_obj.get("fileExtension"))
        if not (text or "").strip() or (text or "").strip() == (name or "").strip():
            logger.warning(
                "Drive text extract produced no body for %s mime=%s size=%s name=%s",
                file_id,
                mime,
                size or len(blob),
                name,
            )
        return text or ""
    except Exception as exc:
        logger.warning("Drive content extract failed for %s: %s", file_id, type(exc).__name__)
        return name


async def _extract_binary(content_bytes: bytes, mime_type: str, file_extension: Optional[str]) -> str:
    """Route binary bytes through Block E's TextExtractor when possible."""
    try:
        from app.normalizer.ocr import OCRService
        from app.normalizer.text_extractor import TextExtractor

        extractor = TextExtractor(OCRService(), max_chars=500_000)
        text = await extractor.extract(content_bytes, mime_type, file_extension)
        return text or ""
    except Exception as exc:
        logger.warning("Binary text extraction failed: %s", type(exc).__name__)
        try:
            return content_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""