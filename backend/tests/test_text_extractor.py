"""
Tests for text extraction orchestrator.

Verifies bounded extraction, OCR fallback, and error handling.
"""

import pytest
from app.normalizer.text_extractor import TextExtractor
from app.normalizer.ocr import FakeOCRService


@pytest.fixture
def text_extractor():
    """Create text extractor with fake OCR."""
    ocr = FakeOCRService()
    return TextExtractor(ocr, max_chars=100)  # Small limit for testing


@pytest.mark.asyncio
async def test_extract_plain_text(text_extractor):
    """Test extraction of plain text."""
    content = b"This is plain text content"
    text = await text_extractor.extract(content, "text/plain")
    
    assert text == "This is plain text content"


@pytest.mark.asyncio
async def test_extract_html_strips_tags(text_extractor):
    """Test HTML extraction strips tags."""
    content = b"<html><body><p>Hello world</p></body></html>"
    text = await text_extractor.extract(content, "text/html")
    
    assert "Hello world" in text
    assert "<p>" not in text
    assert "<body>" not in text


@pytest.mark.asyncio
async def test_extract_truncates_at_max_chars(text_extractor):
    """Test that extracted text is truncated at max_chars."""
    # Create content longer than max_chars (100)
    content = b"A" * 200
    text = await text_extractor.extract(content, "text/plain")
    
    assert len(text) == 100


@pytest.mark.asyncio
async def test_extract_image_uses_ocr(text_extractor):
    """Test that image extraction falls back to OCR."""
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    text = await text_extractor.extract(content, "image/png", fixture_key="test_image.png")
    
    # Should return fake OCR text
    assert "Fake OCR" in text or text != ""


@pytest.mark.asyncio
async def test_extract_unknown_mime_returns_empty(text_extractor):
    """Test that unknown MIME type returns empty string."""
    content = b"unknown binary content"
    text = await text_extractor.extract(content, "application/x-unknown")
    
    assert text == ""


@pytest.mark.asyncio
async def test_extract_empty_content_returns_empty(text_extractor):
    """Test that empty content returns empty string."""
    text = await text_extractor.extract(b"", "text/plain")
    
    assert text == ""
