"""
Debug script to examine JavaScript chunks and their boundaries.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker

chunker = CodeChunker()

# Test api_handler.js
filepath = r"D:\PROJECTS\Sync Ai Final\services\block-e-chunking\fixtures\code\javascript\api_handler.js"
with open(filepath, 'r', encoding='utf-8') as f:
    source = f.read()

chunks = chunker.chunk(source, 'javascript')

print(f"File: api_handler.js")
print(f"Total chunks: {len(chunks)}")
print()

for i, chunk in enumerate(chunks):
    print(f"Chunk {i}:")
    print(f"  Type: {chunk.chunk_type}")
    print(f"  Node type: {chunk.node_type}")
    print(f"  Start byte: {chunk.start_byte}")
    print(f"  End byte: {chunk.end_byte}")
    print(f"  First 100 chars: '{chunk.text[:100]}'")
    print()
