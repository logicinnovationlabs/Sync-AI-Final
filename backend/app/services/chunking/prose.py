"""Prose chunker – splits text at sentence boundaries."""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)


class ProseChunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, content: str, *, parent_doc_id: str = "") -> list[dict]:
        """Split prose into chunks of ~chunk_size characters, preserving sentences.

        Args:
            content: Text to chunk.
            parent_doc_id: Document ID that owns these chunks (Rule #4).
        """
        if not content:
            return []

        # Split into sentences (simple heuristic)
        sentences = re.split(r'(?<=[.!?])\s+', content)
        chunks = []
        current_chunk = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunk_id = hashlib.md5(f"{len(chunks)}{chunk_text[:50]}".encode()).hexdigest()[:16]
                chunks.append({
                    "id": chunk_id,
                    "content": chunk_text,
                    "start": 0,
                    "end": len(chunk_text),
                    "ends_mid_sentence": False,
                    "parent_doc_id": parent_doc_id,
                })
                # Overlap: keep last sentence for continuity (if within overlap)
                if self.overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1]
                    current_chunk = [overlap_text]
                    current_len = len(overlap_text)
                else:
                    current_chunk = []
                    current_len = 0
            current_chunk.append(sent)
            current_len += len(sent) + 1

        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunk_id = hashlib.md5(f"{len(chunks)}{chunk_text[:50]}".encode()).hexdigest()[:16]
            chunks.append({
                "id": chunk_id,
                "content": chunk_text,
                "start": 0,
                "end": len(chunk_text),
                "ends_mid_sentence": False,
                "parent_doc_id": parent_doc_id,
            })

        # Rule #4 verification: log if any chunk somehow split mid-sentence
        for c in chunks:
            if c.get("ends_mid_sentence"):
                logger.warning(
                    "Chunk %s (parent=%s) ends mid-sentence — verify chunk boundaries",
                    c["id"],
                    parent_doc_id,
                )

        return chunks

    def chunk_with_parent(self, content: str, parent_doc_id: str) -> list[dict]:
        """Convenience wrapper that ensures parent_doc_id is set (Rule #4)."""
        return self.chunk(content, parent_doc_id=parent_doc_id)