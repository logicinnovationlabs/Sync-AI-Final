"""
Generator script for deterministic oversized fixture.
Per Phase 1.3: Build one function body by programmatically appending simple lines
until the function body's own length (measured with real tokenizer) clears the 2048
threshold with margin (target ~2200+ to avoid boundary flake).
"""

import tiktoken

# Initialize tiktoken with cl100k_base encoding (matches Azure OpenAI text-embedding-3-large)
tokenizer = tiktoken.get_encoding("cl100k_base")

MAX_TOKENS = 2048
TARGET_TOKENS = 2200  # Target ~2200+ to avoid boundary flake

def generate_oversized_function():
    """Generate a Python function with enough tokens to exceed truncation threshold."""
    
    # Start with a simple function signature
    function_lines = [
        "def oversized_function():",
        "    \"\"\"This function is intentionally oversized to test truncation at ceiling.\"\"\"",
    ]
    
    # Build function body with simple assignment lines
    # Each line like "    aN = N" is simple and predictable
    i = 0
    while True:
        line = f"    a{i} = {i}"
        function_lines.append(line)
        
        # Measure current token count
        function_text = "\n".join(function_lines) + "\n"
        token_count = len(tokenizer.encode(function_text))
        
        i += 1
        
        # Check if we've exceeded target with margin
        if token_count >= TARGET_TOKENS:
            print(f"[GENERATOR] Target reached at iteration {i}")
            print(f"[GENERATOR] Final token count: {token_count}")
            print(f"[GENERATOR] Target was: {TARGET_TOKENS}")
            print(f"[GENERATOR] Exceeds MAX_TOKENS ({MAX_TOKENS}) by: {token_count - MAX_TOKENS}")
            break
        
        # Safety check to prevent infinite loop
        if i > 100000:
            raise RuntimeError(f"Failed to reach target {TARGET_TOKENS} tokens after {i} iterations")
    
    # Add a return statement at the end
    function_lines.append("    return True")
    
    function_text = "\n".join(function_lines) + "\n"
    final_token_count = len(tokenizer.encode(function_text))
    
    print(f"[GENERATOR] Final function token count (with return): {final_token_count}")
    
    return function_text, final_token_count

if __name__ == "__main__":
    print("[GENERATOR] Starting oversized fixture generation...")
    print(f"[GENERATOR] Using tiktoken cl100k_base encoding")
    print(f"[GENERATOR] Target token count: {TARGET_TOKENS}")
    print(f"[GENERATOR] MAX_TOKENS threshold: {MAX_TOKENS}")
    print()
    
    function_text, token_count = generate_oversized_function()
    
    # Save to fixture file
    fixture_path = "fixtures/test_oversized_function_deterministic.py"
    with open(fixture_path, "w") as f:
        f.write(function_text)
    
    print()
    print(f"[GENERATOR] Fixture saved to: {fixture_path}")
    print(f"[GENERATOR] Final token count: {token_count}")
    print(f"[GENERATOR] This fixture should trigger truncation (truncated=True)")
