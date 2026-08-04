"""
CI enforcement check for chunker_version per v7.0 §7.

This script verifies that if any file under app/chunkers/*.py is modified,
the CHUNKER_VERSION constant in app/chunkers/__init__.py must also be modified.
A PR that touches chunker logic but leaves the version string unchanged is rejected.

Usage in CI:
    python tests/check_chunker_version_ci.py --base-ref origin/main --head-ref HEAD

Exit codes:
    0: Check passed (either no chunker changes, or version was bumped)
    1: Check failed (chunker changed but version not bumped)
"""

import sys
import os
import re
import subprocess
from typing import List, Set

def get_changed_files(base_ref: str, head_ref: str) -> List[str]:
    """Get list of changed files between two refs using git diff."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', f'{base_ref}...{head_ref}'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(f"Error running git diff: {e}")
        sys.exit(1)

def get_chunker_files() -> Set[str]:
    """Get all chunker source files that should trigger version bump."""
    chunker_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'chunkers')
    chunker_files = set()
    
    for filename in os.listdir(chunker_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            # Normalize to forward slashes for git diff comparison
            chunker_files.add('app/chunkers/' + filename)
            chunker_files.add('services/block-e-chunking/app/chunkers/' + filename)
    
    return chunker_files

def get_current_chunker_version() -> str:
    """Extract current CHUNKER_VERSION from __init__.py."""
    init_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'chunkers', '__init__.py')
    
    with open(init_path, 'r') as f:
        content = f.read()
    
    match = re.search(r'CHUNKER_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        print("ERROR: CHUNKER_VERSION constant not found in app/chunkers/__init__.py")
        sys.exit(1)
    
    return match.group(1)

def _git_show_chunker_init(ref: str) -> str:
    """Return __init__.py content from ref, trying monorepo and service-root paths."""
    candidates = [
        f'{ref}:services/block-e-chunking/app/chunkers/__init__.py',
        f'{ref}:app/chunkers/__init__.py',
    ]
    last_err = None
    for spec in candidates:
        result = subprocess.run(
            ['git', 'show', spec],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        last_err = result.stderr
    raise FileNotFoundError(last_err or f'__init__.py not found in {ref}')


def get_chunker_version_at_ref(ref: str) -> str:
    """Extract CHUNKER_VERSION from a git ref."""
    content = _git_show_chunker_init(ref)
    match = re.search(r'CHUNKER_VERSION\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        return "0.0.0"
    return match.group(1)


def get_base_chunker_version(base_ref: str, chunker_files_changed: bool) -> str:
    """Extract CHUNKER_VERSION from base ref.
    
    If __init__.py doesn't exist in base ref and chunker files changed,
    this is an ambiguous state - fail closed rather than falling back to 0.0.0.
    """
    try:
        return get_chunker_version_at_ref(base_ref)
    except FileNotFoundError:
        if chunker_files_changed:
            print("\n" + "=" * 80)
            print("CHECK FAILED")
            print("=" * 80)
            print("Chunker files changed but app/chunkers/__init__.py doesn't exist in base ref.")
            print(f"Base ref: {base_ref}")
            print("This is an ambiguous state - cannot determine if CHUNKER_VERSION was bumped.")
            print("Per v7.0 section 7: This requires manual verification to ensure version was bumped.")
            print("\nTo resolve: Ensure __init__.py exists in base ref, or manually verify version bump.")
            sys.exit(1)
        return "0.0.0"

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='CI check for chunker_version enforcement')
    parser.add_argument('--base-ref', default='origin/main', help='Base git ref to compare against')
    parser.add_argument('--head-ref', default='HEAD', help='Head git ref (current changes)')
    args = parser.parse_args()
    
    print("=" * 80)
    print("CHUNKER_VERSION CI ENFORCEMENT CHECK (v7.0 §7)")
    print("=" * 80)
    
    # Get changed files
    changed_files = get_changed_files(args.base_ref, args.head_ref)
    # Normalize to forward slashes for comparison
    changed_files = [f.replace('\\', '/') for f in changed_files]
    print(f"\nChanged files: {len(changed_files)}")
    
    # Check if any chunker files changed
    chunker_files = get_chunker_files()
    changed_chunker_files = [f for f in changed_files if f in chunker_files]
    
    print(f"Chunker files changed: {len(changed_chunker_files)}")
    if changed_chunker_files:
        for f in changed_chunker_files:
            print(f"  - {f}")
    
    # If no chunker files changed, check passes
    if not changed_chunker_files:
        print("\n✓ No chunker files changed - check passes")
        sys.exit(0)
    
    # Chunker files changed - verify version was bumped (compare versions at both refs)
    try:
        current_version = get_chunker_version_at_ref(args.head_ref)
    except FileNotFoundError:
        current_version = get_current_chunker_version()
    base_version = get_base_chunker_version(args.base_ref, chunker_files_changed=True)
    
    print(f"\nCurrent CHUNKER_VERSION ({args.head_ref}): {current_version}")
    print(f"Base CHUNKER_VERSION ({args.base_ref}): {base_version}")
    
    if current_version == base_version:
        print("\n" + "=" * 80)
        print("CHECK FAILED")
        print("=" * 80)
        print("Chunker logic was modified but CHUNKER_VERSION was not bumped.")
        print("Per v7.0 section 7: A change to chunking logic without a corresponding version")
        print("bump means old chunks silently coexist with new ones under an identical")
        print("version tag, defeating the re-chunk/re-embed detection.")
        print("\nTo fix: Bump CHUNKER_VERSION in app/chunkers/__init__.py")
        sys.exit(1)
    else:
        print("\nCHUNKER_VERSION was bumped - check passes")
        sys.exit(0)

if __name__ == "__main__":
    main()
