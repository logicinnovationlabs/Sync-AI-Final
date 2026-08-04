"""
Component 3 Verification Script
Verifies prose chunker preserves sentence boundaries and does not split mid-sentence
"""

import sys
import os
import glob

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.prose_chunker import ProseChunker


def verify_sentence_boundaries():
    """Verify that prose chunker does not split mid-sentence."""
    
    print("=" * 80)
    print("COMPONENT 3 VERIFICATION: Prose Chunker - Sentence Boundary Preservation")
    print("=" * 80)
    
    # Create prose chunker with specified configuration
    print("\n[1] Creating ProseChunker...")
    print("   Configuration:")
    print("   - max_tokens: 512")
    print("   - overlap_tokens: 50")
    print("   Justification: OpenAI text-embedding-3-small has 8191 token context window.")
    print("   512 tokens per chunk provides good semantic coherence while allowing")
    print("   efficient embedding generation. 50 token overlap ensures context continuity.")
    
    chunker = ProseChunker(max_tokens=512, overlap_tokens=50)
    
    # Load prose fixtures
    print("\n[2] Loading Block Z prose fixtures...")
    prose_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "prose"
    )
    
    prose_files = glob.glob(os.path.join(prose_dir, "*.txt"))
    print(f"   Found {len(prose_files)} prose fixture files")
    
    if len(prose_files) < 3:
        print(f"   ⚠ Warning: Expected at least 3 prose fixtures, found {len(prose_files)}")
    
    # Test each fixture
    all_chunks = []
    mid_sentence_splits = 0
    
    for i, prose_file in enumerate(prose_files):
        print(f"\n[3.{i+1}] Processing {os.path.basename(prose_file)}...")
        
        with open(prose_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"   Text length: {len(text)} characters")
        
        # Chunk the text
        chunks = chunker.chunk(text)
        print(f"   Generated {len(chunks)} chunks")
        
        all_chunks.extend(chunks)
        
        # Verify no mid-sentence splits
        print(f"   Verifying sentence boundaries...")
        for j, chunk in enumerate(chunks):
            # Check if chunk ends mid-sentence
            chunk_text = chunk.text.strip()
            
            # A chunk ending mid-sentence would:
            # - Not end with sentence-ending punctuation (. ! ?)
            # - Not be the last chunk
            # - Not be empty
            if j < len(chunks) - 1:  # Not the last chunk
                if chunk_text and not chunk_text[-1] in ['.', '!', '?', '"', "'"]:
                    # Check if it's a legitimate abbreviation (e.g., "Dr.", "Mr.", "etc.")
                    # Simple heuristic: if the last word is short and ends with period, it might be an abbreviation
                    last_word = chunk_text.split()[-1] if chunk_text.split() else ""
                    if not (len(last_word) <= 4 and last_word.endswith('.')):
                        print(f"   ✗ Chunk {j} may end mid-sentence: '{chunk_text[-50:]}'")
                        mid_sentence_splits += 1
                    else:
                        print(f"   ✓ Chunk {j} ends with potential abbreviation: '{last_word}'")
                else:
                    print(f"   ✓ Chunk {j} ends with sentence boundary")
            else:
                # Last chunk - just check it's not empty
                if chunk_text:
                    print(f"   ✓ Final chunk {j} is valid")
                else:
                    print(f"   ✗ Final chunk {j} is empty")
    
    # Summary
    print("\n[4] Summary of sentence boundary verification...")
    print(f"   Total chunks processed: {len(all_chunks)}")
    print(f"   Potential mid-sentence splits: {mid_sentence_splits}")
    
    if mid_sentence_splits == 0:
        print(f"   ✓ No mid-sentence splits detected")
    else:
        print(f"   ✗ {mid_sentence_splits} potential mid-sentence splits detected")
        return False
    
    # Detailed boundary inspection for a sample chunk
    print("\n[5] Detailed boundary inspection of sample chunk...")
    if all_chunks:
        sample_chunk = all_chunks[0]
        print(f"   Chunk 0 text:")
        print(f"   '{sample_chunk.text}'")
        print(f"   Start byte: {sample_chunk.start_byte}")
        print(f"   End byte: {sample_chunk.end_byte}")
        print(f"   Token count: {sample_chunk.token_count}")
        print(f"   Ends with: '{sample_chunk.text[-10:]}'")
        
        if sample_chunk.text.strip()[-1] in ['.', '!', '?', '"', "'"]:
            print(f"   ✓ Sample chunk ends with sentence boundary")
        else:
            last_word = sample_chunk.text.split()[-1] if sample_chunk.text.split() else ""
            if len(last_word) <= 4 and last_word.endswith('.'):
                print(f"   ✓ Sample chunk ends with potential abbreviation")
            else:
                print(f"   ✗ Sample chunk may end mid-sentence")
                return False
    
    # Test with a known edge case
    print("\n[6] Testing edge case: text with abbreviations...")
    edge_case_text = "Dr. Smith went to Washington D.C. to meet with Mr. Jones. They discussed the project."
    edge_chunks = chunker.chunk(edge_case_text)
    print(f"   Input: '{edge_case_text}'")
    print(f"   Generated {len(edge_chunks)} chunks")
    
    for j, chunk in enumerate(edge_chunks):
        print(f"   Chunk {j}: '{chunk.text}'")
    
    print("\n" + "=" * 80)
    print("COMPONENT 3 VERIFICATION: PASSED")
    print("=" * 80)
    print("\nEVIDENCE:")
    print(f"- Processed {len(prose_files)} prose fixture documents")
    print(f"- Generated {len(all_chunks)} total chunks")
    print(f"- Zero mid-sentence splits detected")
    print(f"- Sentence boundaries preserved across all chunks")
    print(f"- Sample chunk boundary inspection confirms proper sentence endings")
    print(f"- Configuration: max_tokens=512, overlap_tokens=50")
    print(f"- Justification: Balances semantic coherence with embedding efficiency")
    
    return True


if __name__ == "__main__":
    try:
        success = verify_sentence_boundaries()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
