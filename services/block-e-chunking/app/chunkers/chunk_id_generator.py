"""
Component 2: Deterministic chunk ID scheme
chunk_id = sha256(tenant_id | document_id | document_version | chunker_version | chunk_type | chunk_index | content_hash)
"""

import hashlib
from typing import Optional


class ChunkIDGenerator:
    """
    Generates deterministic chunk IDs using SHA256.
    
    chunk_id = sha256(tenant_id | document_id | document_version | chunker_version | chunk_type | chunk_index | content_hash)
    
    This ensures:
    - Identical chunk_ids across reprocessing runs (E4)
    - Chunk ID changes if and only if content changes
    - No random UUIDs or auto-increment IDs
    """
    
    def __init__(self, chunker_version: str = "1.0.0"):
        self.chunker_version = chunker_version
    
    def generate(
        self,
        tenant_id: str,
        document_id: str,
        document_version: int,
        chunk_type: str,
        chunk_index: int,
        content_hash: str
    ) -> str:
        """
        Generate a deterministic chunk ID.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            document_version: Document version number
            chunk_type: Type of chunk (from ChunkType enum)
            chunk_index: Index of chunk within document
            content_hash: SHA256 hash of chunk content text
        
        Returns:
            SHA256 hash encoded as hex string (64 characters)
        """
        # Concatenate all components with a delimiter that won't appear in values
        delimiter = "|"
        payload = delimiter.join([
            str(tenant_id),
            str(document_id),
            str(document_version),
            self.chunker_version,
            str(chunk_type),
            str(chunk_index),
            str(content_hash)
        ])
        
        # Generate SHA256 hash
        hash_obj = hashlib.sha256(payload.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def compute_content_hash(self, content_text: str) -> str:
        """
        Compute SHA256 hash of chunk content text.
        
        Args:
            content_text: The exact extracted text of the chunk
        
        Returns:
            SHA256 hash encoded as hex string (64 characters)
        """
        hash_obj = hashlib.sha256(content_text.encode('utf-8'))
        return hash_obj.hexdigest()
