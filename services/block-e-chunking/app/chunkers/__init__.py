"""
Chunkers for prose and code
"""

# Per v7.0 §7: chunker_version is a correctness-critical field, not documentation.
# A change to chunking logic without a corresponding version bump means old chunks
# silently coexist with new ones under an identical version tag, defeating the
# re-chunk/re-embed detection this whole design relies on.
# This constant must be bumped whenever chunking logic changes.
CHUNKER_VERSION = "1.2.0"

from .chunk_id_generator import ChunkIDGenerator
from .prose_chunker import ProseChunker
from .code_chunker import CodeChunker

__all__ = ["ChunkIDGenerator", "ProseChunker", "CodeChunker", "CHUNKER_VERSION"]
