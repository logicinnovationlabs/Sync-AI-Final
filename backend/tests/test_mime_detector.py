"""
Tests for MIME type detection with magic bytes cross-checking.

Verifies that MIME spoofing is detected and flagged.
"""

import pytest
from app.normalizer.mime_detector import detect_mime, _is_material_mismatch


def test_detect_mime_plain_text():
    """Test detection of plain text file."""
    content = b"This is plain text content"
    detected, mismatch = detect_mime(content, "text/plain")
    
    assert detected.startswith("text/")
    assert not mismatch


def test_detect_mime_mismatch_detected():
    """Test detection of MIME spoofing (ZIP claiming to be text)."""
    # ZIP file magic bytes
    zip_content = b"PK\x03\x04" + b"\x00" * 100
    detected, mismatch = detect_mime(zip_content, "text/plain")
    
    # Should detect as application/zip and flag mismatch
    assert "zip" in detected.lower() or "application" in detected
    assert mismatch


def test_detect_mime_empty_bytes():
    """Test handling of empty byte content."""
    detected, mismatch = detect_mime(b"", "text/plain")
    
    # Should fall back to stated MIME
    assert detected == "text/plain"
    assert not mismatch


def test_detect_mime_no_stated_mime():
    """Test detection when no source-stated MIME is provided."""
    content = b"This is text"
    detected, mismatch = detect_mime(content, None)
    
    # Should detect from magic bytes, no mismatch (nothing to compare against)
    assert detected
    assert not mismatch


def test_is_material_mismatch_same_major_type():
    """Test that same major type (text/plain vs text/x-c) is not a material mismatch."""
    assert not _is_material_mismatch("text/plain", "text/x-c")
    assert not _is_material_mismatch("image/png", "image/jpeg")


def test_is_material_mismatch_benign_vs_executable():
    """Test that executable detected when text claimed is a material mismatch."""
    assert _is_material_mismatch("text/plain", "application/x-executable")
    assert _is_material_mismatch("image/png", "application/zip")


def test_is_material_mismatch_exact_match():
    """Test that exact match is not a mismatch."""
    assert not _is_material_mismatch("text/plain", "text/plain")
    assert not _is_material_mismatch("application/pdf", "application/pdf")
