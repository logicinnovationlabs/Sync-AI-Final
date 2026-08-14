"""Prose chunker – splits text at sentence boundaries."""

import re
import hashlib

class ProseChunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, content: str) -> list[dict]:
        """Split prose into chunks of ~chunk_size characters, preserving sentences."""
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
            })

        return chunks