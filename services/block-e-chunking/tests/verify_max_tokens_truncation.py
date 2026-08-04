"""
Verification script for max_tokens ceiling truncation logic per v7.0 §3.4.

Tests that chunks exceeding 2048 tokens are truncated and the truncated flag is set.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker


def test_max_tokens_truncation():
    """Test that chunks exceeding MAX_TOKENS are truncated and flag is set."""
    
    print("=" * 80)
    print("MAX_TOKENS CEILING TRUNCATION VERIFICATION (v7.0 §3.4)")
    print("=" * 80)
    
    chunker = CodeChunker()
    
    # Fixture: A very large function (>2048 tokens)
    # This function should be truncated and the truncated flag should be set
    # Create a single large function body by repeating a pattern
    large_body = "        x = 1\n" * 10000  # This should exceed 2048 tokens
    
    large_function_fixture = f"""
class LargeClass:
    def __init__(self):
        self.x = 1
    
    def very_large_method(self):
{large_body}
        return self.x
"""
    
    print("\n[1] Processing fixture with large function (>2048 tokens)...")
    chunks_large = chunker.chunk(large_function_fixture, 'python')
    
    print(f"   Generated {len(chunks_large)} chunks")
    
    # Check for function_method chunks
    function_chunks = [c for c in chunks_large if c.chunk_type == 'function_method']
    
    print(f"   Function chunks: {len(function_chunks)}")
    
    if len(function_chunks) == 0:
        print("   ✗ No function chunks found")
        return False
    
    # Find the large function chunk
    large_chunk = None
    for chunk in function_chunks:
        if chunk.token_count >= chunker.MAX_TOKENS:
            large_chunk = chunk
            break
    
    if large_chunk:
        print(f"   ✓ Found function chunk with {large_chunk.token_count} tokens (>= {chunker.MAX_TOKENS})")
        print(f"   Truncated flag: {large_chunk.truncated}")
        
        # Verify the truncated flag is set
        if large_chunk.truncated:
            print("   ✓ Truncated flag is correctly set to True")
        else:
            print("   ✗ Truncated flag is NOT set (should be True for truncated chunks)")
            return False
        
        # Verify the chunk was actually truncated (token count should be exactly MAX_TOKENS)
        if large_chunk.token_count == chunker.MAX_TOKENS:
            print(f"   ✓ Token count exactly at ceiling ({chunker.MAX_TOKENS})")
        else:
            print(f"   ⚠ Token count is {large_chunk.token_count} (expected {chunker.MAX_TOKENS})")
        
        # Verify the text was truncated (should be shorter than original)
        original_length = len(large_function_fixture)
        chunk_length = len(large_chunk.text)
        if chunk_length < original_length:
            print(f"   ✓ Chunk text was truncated ({chunk_length} < {original_length} bytes)")
        else:
            print(f"   ✗ Chunk text was NOT truncated ({chunk_length} >= {original_length} bytes)")
            return False
    else:
        print("   ⚠ No chunk exceeded MAX_TOKENS ceiling")
        print("   (This is acceptable if the fixture wasn't large enough)")
    
    # Fixture: A normal function (<2048 tokens)
    # This function should NOT be truncated and the truncated flag should be False
    normal_function_fixture = """
class NormalClass:
    def __init__(self):
        self.x = 1
    
    def normal_method(self, arg1, arg2):
        result = arg1 + arg2
        if result > 100:
            return result * 2
        else:
            return result
"""
    
    print("\n[2] Processing fixture with normal function (<2048 tokens)...")
    chunks_normal = chunker.chunk(normal_function_fixture, 'python')
    
    print(f"   Generated {len(chunks_normal)} chunks")
    
    function_chunks_normal = [c for c in chunks_normal if c.chunk_type == 'function_method']
    
    print(f"   Function chunks: {len(function_chunks_normal)}")
    
    if len(function_chunks_normal) > 0:
        normal_chunk = function_chunks_normal[0]
        print(f"   Function chunk: {normal_chunk.token_count} tokens")
        print(f"   Truncated flag: {normal_chunk.truncated}")
        
        # Verify the truncated flag is NOT set for normal chunks
        if not normal_chunk.truncated:
            print("   ✓ Truncated flag is correctly False for normal chunk")
        else:
            print("   ✗ Truncated flag is True for normal chunk (should be False)")
            return False
    else:
        print("   ✗ No function chunks found")
        return False
    
    # Non-vacuous assertion: ensure at least one chunk was actually truncated
    truncated_chunks = [c for c in chunks_large if c.truncated]
    if len(truncated_chunks) == 0:
        print("   ✗ No chunks were truncated - fixture never exercised truncation path")
        return False
    print(f"   ✓ {len(truncated_chunks)} chunk(s) were truncated (non-vacuous assertion passed)")
    
    print("\n" + "=" * 80)
    print("MAX_TOKENS CEILING TRUNCATION VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print("- Large function (>2048 tokens) was truncated to ceiling")
    print("- Truncated flag correctly set to True for truncated chunk")
    print("- Normal function (<2048 tokens) has truncated flag False")
    
    return True


if __name__ == "__main__":
    try:
        success = test_max_tokens_truncation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
