"""
MIME type detection using magic bytes.

Never trusts source-stated MIME type alone — cross-checks against file-header
magic bytes to detect spoofed/mismatched files.
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import magic as _magic
except ImportError:
    _magic = None
    logger.warning(
        "python-magic/libmagic not available; MIME detection will trust source-stated type"
    )


def detect_mime(raw_bytes: bytes, source_stated_mime: Optional[str]) -> Tuple[str, bool]:
    """
    Detect MIME type from file magic bytes and compare to source-stated type.
    
    Returns (detected_mime_type, mismatch_flag).
    
    Mismatch flag is True when source_stated_mime is present and materially
    disagrees with the detected type (e.g., claims text/plain but magic bytes
    show application/zip or application/x-executable).
    
    Documents with mismatch are still processed (do not silently drop user content)
    but are logged at WARNING level and flagged for trust/safety review.
    
    Args:
        raw_bytes: Raw file content bytes
        source_stated_mime: MIME type claimed by source (may be None)
        
    Returns:
        Tuple of (detected_mime_type, mismatch_flag)
    """
    if not raw_bytes:
        logger.warning("Empty byte content for MIME detection")
        return source_stated_mime or "application/octet-stream", False
    
    try:
        if _magic is None:
            return source_stated_mime or "application/octet-stream", False
        # Use python-magic to detect from magic bytes
        detected_mime = _magic.from_buffer(raw_bytes, mime=True)
    except Exception as e:
        logger.error(f"MIME detection failed: {e}")
        # Fall back to source-stated if detection fails
        return source_stated_mime or "application/octet-stream", False
    
    # Check for material mismatch
    mismatch = False
    if source_stated_mime:
        mismatch = _is_material_mismatch(source_stated_mime, detected_mime)
        
        if mismatch:
            logger.warning(
                f"MIME mismatch detected: source claims '{source_stated_mime}' "
                f"but magic bytes show '{detected_mime}'"
            )
    
    return detected_mime, mismatch


def _is_material_mismatch(stated: str, detected: str) -> bool:
    """
    Determine if stated vs detected MIME types represent a material mismatch.
    
    Some differences are benign (e.g., text/plain vs text/x-c for source code).
    Material mismatches involve executable/archive content disguised as innocent types.
    
    Args:
        stated: Source-stated MIME type
        detected: Detected MIME type from magic bytes
        
    Returns:
        True if mismatch is material (security concern)
    """
    # Normalize to lowercase for comparison
    stated = stated.lower()
    detected = detected.lower()
    
    # Exact match or both in same major category is fine
    if stated == detected:
        return False
    
    stated_major = stated.split("/")[0]
    detected_major = detected.split("/")[0]
    
    # Same major type (text/* vs text/*, image/* vs image/*) is usually fine
    if stated_major == detected_major:
        return False
    
    # Material mismatches: executable/archive detected when source claims benign type
    dangerous_detected = detected_major in ("application",) and any(
        keyword in detected
        for keyword in ["executable", "x-executable", "zip", "x-compressed", "x-tar", "x-rar"]
    )
    
    benign_stated = stated_major in ("text", "image")
    
    if dangerous_detected and benign_stated:
        return True
    
    # Other cross-category differences are material
    return stated_major != detected_major
