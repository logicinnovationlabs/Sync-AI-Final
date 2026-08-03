"""
OCR service for extracting text from images.

Wraps pytesseract with timeout and error handling.
FakeOCRService for tests (no real Tesseract invocation).
"""

import logging
from typing import Optional
from PIL import Image
import io
import os

logger = logging.getLogger(__name__)


class OCRService:
    """
    Real OCR service using pytesseract.
    
    Bounded by OCR_TIMEOUT_SECONDS to prevent hung workers.
    """
    
    def __init__(self, tesseract_path: Optional[str] = None, language: str = "eng", timeout: int = 30):
        """
        Initialize OCR service.
        
        Args:
            tesseract_path: Path to tesseract binary (optional, will use system default)
            language: Tesseract language code (default: eng)
            timeout: Maximum OCR processing time in seconds
        """
        self.tesseract_path = tesseract_path
        self.language = language
        self.timeout = timeout
        
        # Set tesseract path if provided
        if tesseract_path:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
    
    def extract_text(self, image_bytes: bytes) -> str:
        """
        Extract text from image bytes using OCR.
        
        Bounded by timeout — on timeout, returns empty string rather than hanging.
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Extracted text (may be empty on timeout or failure)
        """
        try:
            import pytesseract
            import signal
            
            # Open image from bytes
            image = Image.open(io.BytesIO(image_bytes))
            
            # Set timeout handler (Unix only; Windows will ignore)
            def timeout_handler(signum, frame):
                raise TimeoutError("OCR timeout")
            
            if hasattr(signal, 'SIGALRM'):
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(self.timeout)
            
            try:
                # Run OCR
                text = pytesseract.image_to_string(image, lang=self.language, timeout=self.timeout)
                return text.strip()
            finally:
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
        
        except TimeoutError:
            logger.warning(f"OCR timeout after {self.timeout} seconds")
            return ""
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""


class FakeOCRService:
    """
    Fake OCR service for tests.
    
    Returns pre-canned text keyed by a fixture identifier passed in metadata.
    No real Tesseract invocation — tests must not call external binaries.
    """
    
    def __init__(self):
        self.fixture_responses = {
            "test_image_1.jpg": "This is fake OCR text from test_image_1",
            "test_image_2.png": "Another fake OCR result",
            "ocr_fixture.jpg": "Fake OCR output for testing",
            "scanned_doc.pdf": "Fake OCR text extracted from scanned PDF",
        }
        self.default_response = "Fake OCR text"
    
    def extract_text(self, image_bytes: bytes, fixture_key: Optional[str] = None) -> str:
        """
        Return pre-canned OCR text for testing.
        
        Args:
            image_bytes: Ignored (tests don't provide real image data)
            fixture_key: Optional fixture identifier for keyed responses
            
        Returns:
            Pre-canned text
        """
        if fixture_key and fixture_key in self.fixture_responses:
            return self.fixture_responses[fixture_key]
        return self.default_response
    
    def register_fixture(self, key: str, text: str) -> None:
        """
        Register a fixture response for testing.
        
        Args:
            key: Fixture identifier
            text: Text to return for this fixture
        """
        self.fixture_responses[key] = text
