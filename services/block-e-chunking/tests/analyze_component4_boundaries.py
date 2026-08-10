"""
Component 4 Boundary Analysis
Performs byte-offset diff analysis on flagged chunks to determine if warnings are genuine E1 violations or false positives.
"""

import sys
import os
import glob

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker


def analyze_boundaries():
    """Analyze boundary warnings with byte-offset diffs."""
    
    print("=" * 80)
    print("COMPONENT 4 BOUNDARY ANALYSIS: Byte-Offset Diff")
    print("=" * 80)
    
    # Create code chunker
    print("\n[1] Creating CodeChunker...")
    chunker = CodeChunker()
    
    # Load code fixtures
    print("\n[2] Loading code fixtures...")
    fixtures_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "code"
    )
    
    # Sample files to analyze
    samples = [
        ('python', 'api_client.py'),  # Python class
        ('python', 'database.py'),   # Python class
        ('javascript', 'api_handler.js'),  # JS function
    ]
    
    for language, filename in samples:
        print(f"\n[3] Analyzing {language}/{filename}...")
        filepath = os.path.join(fixtures_dir, language, filename)
        
        if not os.path.exists(filepath):
            print(f"   File not found: {filepath}")
            continue
        
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        
        print(f"   Source length: {len(source)} bytes")
        
        # Chunk the file
        chunks = chunker.chunk(source, language)
        print(f"   Generated {len(chunks)} chunks")
        
        # Find class/function chunks
        for chunk in chunks:
            if chunk.chunk_type in ['class_module', 'function_method']:
                print(f"\n   --- Chunk Type: {chunk.chunk_type} ---")
                print(f"   Chunk index: {chunk.chunk_index}")
                print(f"   Start byte: {chunk.start_byte}")
                print(f"   End byte: {chunk.end_byte}")
                print(f"   Length: {chunk.end_byte - chunk.start_byte} bytes")
                print(f"   Node type: {chunk.node_type}")
                
                # Extract actual bytes from source at this range
                extracted = source[chunk.start_byte:chunk.end_byte]
                print(f"\n   Extracted text (first 100 chars):")
                print(f"   '{extracted[:100]}'")
                
                # Check if starts with expected keyword
                first_100 = extracted[:100].lower()
                if chunk.chunk_type == 'class_module':
                    if 'class ' in first_100 or 'module ' in first_100 or 'struct ' in first_100:
                        print(f"   ✓ Starts with class/module keyword")
                    else:
                        print(f"   ⚠ Does NOT start with class/module keyword")
                        print(f"   This may be a genuine E1 violation or false positive")
                        print(f"   Full first 200 chars:")
                        print(f"   '{extracted[:200]}'")
                elif chunk.chunk_type == 'function_method':
                    if 'def ' in first_100 or 'function ' in first_100 or 'func ' in first_100:
                        print(f"   ✓ Starts with function/method keyword")
                    else:
                        print(f"   ⚠ Does NOT start with function/method keyword")
                        print(f"   This may be a genuine E1 violation or false positive")
                        print(f"   Full first 200 chars:")
                        print(f"   '{extracted[:200]}'")
                
                # Show what comes before the chunk in the source
                if chunk.start_byte > 0:
                    before = source[max(0, chunk.start_byte - 50):chunk.start_byte]
                    print(f"\n   50 bytes before chunk:")
                    print(f"   '{before}'")
                
                # Show what comes after the chunk
                if chunk.end_byte < len(source):
                    after = source[chunk.end_byte:min(len(source), chunk.end_byte + 50)]
                    print(f"\n   50 bytes after chunk:")
                    print(f"   '{after}'")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    try:
        analyze_boundaries()
    except Exception as e:
        print(f"\n✗ Analysis failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
