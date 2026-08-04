"""
Verification script for min_tokens floor merge-into-parent logic per v7.0 §3.4.

Tests that small functions (<20 tokens) are merged into parent class chunks
instead of being dropped as standalone chunks.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker


def test_min_tokens_merge():
    """Test that small functions are merged into parent class chunks."""
    
    print("=" * 80)
    print("MIN_TOKENS FLOOR MERGE-INTO-PARENT VERIFICATION (v7.0 §3.4)")
    print("=" * 80)
    
    chunker = CodeChunker()
    
    # Fixture: A class with a very small function (<20 tokens)
    # This function should be merged into the class chunk, not emitted separately
    small_function_fixture = """
class MyClass:
    def __init__(self):
        self.x = 1
    
    def tiny(self):
        return 42
"""
    
    print("\n[1] Processing fixture with small function (<20 tokens)...")
    chunks = chunker.chunk(small_function_fixture, 'python')
    
    print(f"   Generated {len(chunks)} chunks")
    
    # Check for function_method chunks
    function_chunks = [c for c in chunks if c.chunk_type == 'function_method']
    class_chunks = [c for c in chunks if c.chunk_type == 'class_module']
    
    print(f"   Function chunks: {len(function_chunks)}")
    print(f"   Class chunks: {len(class_chunks)}")
    
    # The small function should NOT appear as a separate function_method chunk
    # It should be merged into the class chunk
    if len(function_chunks) == 0:
        print("   ✓ Small function was NOT emitted as separate chunk (merged into class)")
    else:
        print("   ✗ Small function was emitted as separate chunk (should be merged)")
        for chunk in function_chunks:
            print(f"     - {chunk.chunk_type}: {chunk.token_count} tokens, node_type={chunk.node_type}")
        return False
    
    # The class chunk should contain the merged function
    if len(class_chunks) > 0:
        class_chunk = class_chunks[0]
        print(f"   ✓ Class chunk exists with {class_chunk.token_count} tokens")
        print(f"   Class chunk text preview: '{class_chunk.text[:100]}...'")
        
        # Verify the class chunk contains the small function text
        if 'tiny' in class_chunk.text:
            print("   ✓ Class chunk contains merged small function")
        else:
            print("   ✗ Class chunk does NOT contain merged small function")
            return False
    else:
        print("   ✗ No class chunk found")
        return False
    
    # Fixture: A class with a normal function (>20 tokens)
    # This function should appear as a separate function_method chunk
    normal_function_fixture = """
class MyClass:
    def __init__(self):
        self.x = 1
    
    def normal_method(self, arg1, arg2, arg3):
        result = arg1 + arg2 + arg3
        if result > 100:
            return result * 2
        else:
            return result
"""
    
    print("\n[2] Processing fixture with normal function (>20 tokens)...")
    chunks = chunker.chunk(normal_function_fixture, 'python')
    
    print(f"   Generated {len(chunks)} chunks")
    
    function_chunks = [c for c in chunks if c.chunk_type == 'function_method']
    class_chunks = [c for c in chunks if c.chunk_type == 'class_module']
    
    print(f"   Function chunks: {len(function_chunks)}")
    print(f"   Class chunks: {len(class_chunks)}")
    
    # The normal function SHOULD appear as a separate function_method chunk
    if len(function_chunks) > 0:
        print("   ✓ Normal function was emitted as separate chunk")
        for chunk in function_chunks:
            print(f"     - {chunk.chunk_type}: {chunk.token_count} tokens, node_type={chunk.node_type}")
    else:
        print("   ✗ Normal function was NOT emitted as separate chunk")
        return False
    
    print("\n" + "=" * 80)
    print("MIN_TOKENS FLOOR MERGE-INTO-PARENT VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print("- Small function (<20 tokens) was merged into class chunk, not emitted separately")
    print("- Normal function (>20 tokens) was emitted as separate function_method chunk")
    print("- Class chunk text contains merged small function")
    
    return True


if __name__ == "__main__":
    try:
        success = test_min_tokens_merge()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
