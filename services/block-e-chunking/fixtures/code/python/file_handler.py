import os
import shutil
from typing import Optional

class FileHandler:
    """File system operations."""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
    
    def read_file(self, filepath: str) -> Optional[str]:
        """Read file contents."""
        full_path = os.path.join(self.base_path, filepath)
        try:
            with open(full_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return None
    
    def write_file(self, filepath: str, content: str) -> bool:
        """Write content to file."""
        full_path = os.path.join(self.base_path, filepath)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
            return True
        except Exception:
            return False
    
    def delete_file(self, filepath: str) -> bool:
        """Delete file."""
        full_path = os.path.join(self.base_path, filepath)
        try:
            os.remove(full_path)
            return True
        except Exception:
            return False
    
    def copy_file(self, src: str, dst: str) -> bool:
        """Copy file."""
        src_path = os.path.join(self.base_path, src)
        dst_path = os.path.join(self.base_path, dst)
        try:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            return True
        except Exception:
            return False
