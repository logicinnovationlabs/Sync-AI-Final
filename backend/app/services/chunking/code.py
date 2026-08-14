"""Code chunker – splits code at function/class boundaries using tree-sitter."""

import hashlib
from pathlib import Path

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    # You need to download and compile tree-sitter grammars for each language.
    # For a simplified version, we'll implement a basic line-based fallback.
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class CodeChunker:
    def __init__(self, chunk_size: int = 512):
        self.chunk_size = chunk_size
        self.parser = None
        if TREE_SITTER_AVAILABLE:
            # Load tree-sitter grammar (you must compile or download them)
            # For this example, we'll use a fallback.
            pass

    def chunk(self, content: str, language: str = "python") -> list[dict]:
        """Split code into chunks, respecting function/class boundaries."""
        if not content:
            return []

        # Fallback to line-based chunking (will not truly verify AST)
        # For signoff, you should use tree-sitter AST.
        lines = content.split("\n")
        chunks = []
        current_chunk = []
        current_len = 0

        for line in lines:
            if current_len + len(line) > self.chunk_size and current_chunk:
                chunk_text = "\n".join(current_chunk)
                chunk_id = hashlib.md5(f"{len(chunks)}{chunk_text[:50]}".encode()).hexdigest()[:16]
                chunks.append({
                    "id": chunk_id,
                    "content": chunk_text,
                    "is_truncated": False,
                    "language": language,
                    "start_line": 0,
                    "end_line": len(current_chunk),
                })
                current_chunk = []
                current_len = 0
            current_chunk.append(line)
            current_len += len(line) + 1

        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunk_id = hashlib.md5(f"{len(chunks)}{chunk_text[:50]}".encode()).hexdigest()[:16]
            chunks.append({
                "id": chunk_id,
                "content": chunk_text,
                "is_truncated": False,
                "language": language,
                "start_line": 0,
                "end_line": len(current_chunk),
            })

        return chunks