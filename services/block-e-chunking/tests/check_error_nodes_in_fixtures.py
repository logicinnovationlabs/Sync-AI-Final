"""
Check if any real fixture files contain ERROR nodes (parse failures).
This verifies the malformed snippet from dump_js_node_types.py is unique to that script.
"""

import sys
import os
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.chunkers.code_chunker import CodeChunker

def check_error_nodes():
    """Check all fixture files for ERROR nodes."""
    
    print("=" * 80)
    print("CHECKING FIXTURE FILES FOR ERROR NODES")
    print("=" * 80)
    
    chunker = CodeChunker()
    
    fixtures_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "fixtures",
        "code"
    )
    
    python_files = glob.glob(os.path.join(fixtures_dir, "python", "*.py"))
    javascript_files = glob.glob(os.path.join(fixtures_dir, "javascript", "*.js"))
    go_files = glob.glob(os.path.join(fixtures_dir, "go", "*.go"))
    
    all_files = python_files + javascript_files + go_files
    
    print(f"\nTotal files to check: {len(all_files)}")
    print(f"  Python: {len(python_files)}")
    print(f"  JavaScript: {len(javascript_files)}")
    print(f"  Go: {len(go_files)}")
    
    files_with_errors = []
    
    for filepath in all_files:
        language = os.path.basename(os.path.dirname(filepath))
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            
            # Parse and check for ERROR nodes using the chunker's internal method
            parser = chunker._get_parser(language)
            if not parser:
                print(f"\n⚠ Unsupported language: {language} in {os.path.basename(filepath)}")
                continue
            
            tree = parser.parse(bytes(source, 'utf8'))
            
            if tree:
                error_nodes = []
                chunker._find_nodes_by_type(tree.root_node, ['ERROR'], error_nodes)
                
                if error_nodes:
                    files_with_errors.append({
                        'path': filepath,
                        'language': language,
                        'error_count': len(error_nodes),
                        'error_nodes': error_nodes
                    })
                    print(f"\n✗ ERROR nodes found in {os.path.basename(filepath)} ({language}): {len(error_nodes)}")
                    for i, node in enumerate(error_nodes[:3]):  # Show first 3
                        print(f"   ERROR {i+1}: byte range {node.start_byte}-{node.end_byte}")
                        snippet = source[node.start_byte:min(node.end_byte, node.start_byte + 100)]
                        print(f"   Snippet: {snippet[:80]}...")
        except Exception as e:
            print(f"\n✗ Parse error in {os.path.basename(filepath)}: {e}")
            files_with_errors.append({
                'path': filepath,
                'language': language,
                'error': str(e)
            })
    
    print("\n" + "=" * 80)
    if files_with_errors:
        print(f"RESULT: {len(files_with_errors)} files with parse errors detected")
        print("\nFiles with errors:")
        for f in files_with_errors:
            print(f"  - {os.path.basename(f['path'])} ({f['language']})")
    else:
        print("RESULT: No ERROR nodes found in any fixture files")
        print("All fixtures parse cleanly.")
    
    print("=" * 80)
    
    return len(files_with_errors) == 0

if __name__ == "__main__":
    success = check_error_nodes()
    sys.exit(0 if success else 1)
