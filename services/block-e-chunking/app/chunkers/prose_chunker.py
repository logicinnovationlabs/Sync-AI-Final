"""
Component 3: Prose Chunker
Sentence-boundary-preserving chunker for prose documents.
Does not split mid-sentence (E1 requirement).
Token-budgeted per target chunk size with overlap.
"""

import re
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a prose chunk per v7.0 §2.1."""
    text: str
    start_byte: int
    end_byte: int
    chunk_index: int
    token_count: int
    chunk_type: str  # prose_paragraph or prose_section per v7.0 §3.1


class ProseChunker:
    """
    Prose chunker that preserves sentence boundaries per v7.0 §3.1.
    
    Produces two chunk types:
    - prose_paragraph: Single paragraph, bounded at sentence boundaries
    - prose_section: Heading + constituent paragraphs, used when paragraph-level chunk would be below minimum token floor (20 tokens)
    
    Configuration:
    - max_tokens: Maximum tokens per chunk (default: 512)
    - min_tokens: Minimum token floor per v7.0 §3.4 (default: 20)
    - overlap_tokens: Number of tokens to overlap between chunks (default: 50)
    
    Justification for max_tokens=512:
    - OpenAI text-embedding-3-small has a context window of 8191 tokens
    - 512 tokens per chunk provides good semantic coherence while allowing
      for efficient embedding generation
    - This is a standard chunk size for RAG applications
    
    Overlap strategy:
    - 50 token overlap ensures context continuity between chunks
    - Helps prevent semantic breaks at chunk boundaries
    """
    
    def __init__(self, max_tokens: int = 512, min_tokens: int = 20, overlap_tokens: int = 50):
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens  # Per v7.0 §3.4 minimum token floor
        self.overlap_tokens = overlap_tokens
        # Simple sentence boundary regex (period, question mark, exclamation followed by space or end)
        self.sentence_boundary_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])$')
        # Heading pattern for prose_section detection
        self.heading_pattern = re.compile(r'^(#{1,6}\s|\*\*|==|--)', re.MULTILINE)
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using word-based approximation.
        Roughly 1 token ≈ 0.75 words for English text.
        This is a conservative estimate; actual tokenization depends on the model.
        """
        words = text.split()
        return int(len(words) / 0.75)
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences while preserving sentence boundaries.
        Returns list of sentences with their byte offsets.
        """
        sentences = []
        start = 0
        
        # Find all sentence boundaries
        for match in self.sentence_boundary_pattern.finditer(text):
            end = match.end()
            sentence = text[start:end].strip()
            if sentence:
                sentences.append({
                    'text': sentence,
                    'start': start,
                    'end': end
                })
            start = end
        
        # Add remaining text as last sentence
        if start < len(text):
            remaining = text[start:].strip()
            if remaining:
                sentences.append({
                    'text': remaining,
                    'start': start,
                    'end': len(text)
                })
        
        return sentences
    
    def chunk(self, text: str) -> List[Chunk]:
        """
        Chunk text while preserving sentence boundaries.
        
        Args:
            text: Input prose text
        
        Returns:
            List of Chunk objects with text, byte offsets, and token counts
        """
        sentences = self._split_into_sentences(text)
        chunks = []
        current_chunk_sentences = []
        current_tokens = 0
        chunk_index = 0
        chunk_start = 0
        
        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence['text'])
            
            # If adding this sentence would exceed max_tokens, finalize current chunk
            if current_tokens + sentence_tokens > self.max_tokens and current_chunk_sentences:
                # Create chunk from accumulated sentences
                chunk_text = ' '.join([s['text'] for s in current_chunk_sentences])
                chunk_end = current_chunk_sentences[-1]['end']
                
                # Determine chunk type based on token count per v7.0 §3.1
                chunk_type = 'prose_section' if current_tokens < self.min_tokens else 'prose_paragraph'
                
                chunks.append(Chunk(
                    text=chunk_text,
                    start_byte=chunk_start,
                    end_byte=chunk_end,
                    chunk_index=chunk_index,
                    token_count=current_tokens,
                    chunk_type=chunk_type
                ))
                
                chunk_index += 1
                
                # Calculate overlap for next chunk
                # Keep sentences from the end of current chunk for overlap
                overlap_sentences = []
                overlap_tokens = 0
                overlap_start = len(current_chunk_sentences) - 1
                
                while overlap_start >= 0 and overlap_tokens < self.overlap_tokens:
                    overlap_sentences.insert(0, current_chunk_sentences[overlap_start])
                    overlap_tokens += self._estimate_tokens(current_chunk_sentences[overlap_start]['text'])
                    overlap_start -= 1
                
                current_chunk_sentences = overlap_sentences
                current_tokens = overlap_tokens
                chunk_start = overlap_sentences[0]['start'] if overlap_sentences else sentence['start']
            
            # Add sentence to current chunk
            current_chunk_sentences.append(sentence)
            current_tokens += sentence_tokens
        
        # Add final chunk if there are remaining sentences
        if current_chunk_sentences:
            chunk_text = ' '.join([s['text'] for s in current_chunk_sentences])
            chunk_end = current_chunk_sentences[-1]['end']
            
            # Determine chunk type based on token count per v7.0 §3.1
            chunk_type = 'prose_section' if current_tokens < self.min_tokens else 'prose_paragraph'
            
            chunks.append(Chunk(
                text=chunk_text,
                start_byte=chunk_start,
                end_byte=chunk_end,
                chunk_index=chunk_index,
                token_count=current_tokens,
                chunk_type=chunk_type
            ))
        
        return chunks
    
    def chunk_with_metadata(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
        chunker_version: str,
        text: str
    ) -> List[Dict[str, Any]]:
        """
        Chunk text and return metadata for database insertion.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            document_version: Document version
            chunker_version: Chunker version
            text: Input prose text
        
        Returns:
            List of dictionaries with chunk metadata for database insertion
        """
        from app.chunkers.chunk_id_generator import ChunkIDGenerator
        from app.models.chunk_record import ChunkType
        
        chunks = self.chunk(text)
        id_generator = ChunkIDGenerator(chunker_version)
        
        chunk_records = []
        for chunk in chunks:
            content_hash = id_generator.compute_content_hash(chunk.text)
            chunk_id = id_generator.generate(
                tenant_id=tenant_id,
                document_id=document_id,
                document_version=document_version,
                chunk_type=ChunkType.FILE_SUMMARY.value,  # Prose uses file_summary type
                chunk_index=chunk.chunk_index,
                content_hash=content_hash
            )
            
            chunk_records.append({
                'chunk_id': chunk_id,
                'tenant_id': tenant_id,
                'document_id': document_id,
                'document_version': document_version,
                'chunk_type': chunk.chunk_type,
                'chunk_index': chunk.chunk_index,
                'chunk_text': chunk.text,
                'token_count': chunk.token_count,
                'start_byte': chunk.start_byte,
                'end_byte': chunk.end_byte,
                'node_type': None,
                'language': None,
                'content_hash': content_hash,
                'chunker_version': chunker_version
            })
        
        return chunk_records
