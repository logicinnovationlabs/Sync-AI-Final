import re
from typing import List

class StringUtils:
    """String manipulation utilities."""
    
    @staticmethod
    def camel_to_snake(name: str) -> str:
        """Convert CamelCase to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    @staticmethod
    def snake_to_camel(name: str) -> str:
        """Convert snake_case to CamelCase."""
        components = name.split('_')
        return ''.join(x.title() for x in components)
    
    @staticmethod
    def truncate(text: str, max_length: int, suffix: str = '...') -> str:
        """Truncate text to max length."""
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def split_into_chunks(text: str, chunk_size: int) -> List[str]:
        """Split text into chunks of specified size."""
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
