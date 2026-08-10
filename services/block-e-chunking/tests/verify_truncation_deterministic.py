"""
Verification script for deterministic truncation fixture.
Per Phase 1.3: Run chunking test against the deterministic oversized fixture
and show the resulting chunk record with truncated=True set.
"""

import sys
sys.path.insert(0, '.')

from app.chunkers.code_chunker import CodeChunker

def main():
    print("[VERIFICATION] Testing deterministic truncation fixture...")
    print()
    
    # Read the fixture file
    fixture_path = "fixtures/test_oversized_function_deterministic.py"
    with open(fixture_path, 'r') as f:
        fixture_text = f.read()
    
    print(f"[VERIFICATION] Fixture path: {fixture_path}")
    print(f"[VERIFICATION] Fixture size: {len(fixture_text)} characters")
    print()
    
    # Initialize chunker
    chunker = CodeChunker()
    
    # Measure token count with real tokenizer
    token_count = chunker._estimate_tokens(fixture_text)
    print(f"[VERIFICATION] Token count (real tokenizer): {token_count}")
    print(f"[VERIFICATION] MAX_TOKENS threshold: {chunker.MAX_TOKENS}")
    print(f"[VERIFICATION] Exceeds threshold by: {token_count - chunker.MAX_TOKENS}")
    print()
    
    # Chunk the fixture
    print("[VERIFICATION] Chunking fixture...")
    chunks = chunker.chunk(fixture_text, language='python')
    
    print(f"[VERIFICATION] Total chunks generated: {len(chunks)}")
    print()
    
    # Find the truncated chunk (truncation reduces token count TO the ceiling)
    truncated_chunk = None
    for chunk in chunks:
        if chunk.truncated:
            truncated_chunk = chunk
            break
    
    if truncated_chunk:
        print("[VERIFICATION] ✓ Truncated chunk found")
        print(f"[VERIFICATION] Chunk type: {truncated_chunk.chunk_type}")
        print(f"[VERIFICATION] Token count: {truncated_chunk.token_count}")
        print(f"[VERIFICATION] Truncated flag: {truncated_chunk.truncated}")
        print(f"[VERIFICATION] Chunk size (bytes): {len(truncated_chunk.text)}")
        print()
        
        if truncated_chunk.truncated:
            print("[VERIFICATION] ✓ SUCCESS: truncated=True is set correctly")
            print("[VERIFICATION] Truncation logic is working with real tokenizer")
            return True
        else:
            print("[VERIFICATION] ✗ FAILURE: truncated=False but should be True")
            print("[VERIFICATION] Truncation logic is NOT working")
            return False
    else:
        print("[VERIFICATION] ✗ FAILURE: No truncated chunk found")
        print("[VERIFICATION] All chunks:")
        for i, chunk in enumerate(chunks):
            print(f"  Chunk {i}: type={chunk.chunk_type}, tokens={chunk.token_count}, truncated={chunk.truncated}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
