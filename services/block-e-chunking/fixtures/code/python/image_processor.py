from PIL import Image, ImageFilter
from typing import Tuple, Optional

class ImageProcessor:
    """Image processing utilities."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.image: Optional[Image.Image] = None
    
    def load(self) -> bool:
        """Load image from file."""
        try:
            self.image = Image.open(self.filepath)
            return True
        except Exception:
            return False
    
    def resize(self, size: Tuple[int, int]) -> bool:
        """Resize image."""
        if not self.image:
            return False
        self.image = self.image.resize(size)
        return True
    
    def rotate(self, degrees: float) -> bool:
        """Rotate image."""
        if not self.image:
            return False
        self.image = self.image.rotate(degrees)
        return True
    
    def blur(self, radius: float = 2) -> bool:
        """Apply blur filter."""
        if not self.image:
            return False
        self.image = self.image.filter(ImageFilter.GaussianBlur(radius))
        return True
    
    def save(self, output_path: str) -> bool:
        """Save image to file."""
        if not self.image:
            return False
        try:
            self.image.save(output_path)
            return True
        except Exception:
            return False
    
    def get_size(self) -> Optional[Tuple[int, int]]:
        """Get image dimensions."""
        if not self.image:
            return None
        return self.image.size
