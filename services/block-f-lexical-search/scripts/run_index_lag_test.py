from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.setdefault("PYTHONPATH", str(ROOT))
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SEARCH_BACKEND", os.environ.get("SEARCH_BACKEND", "mock"))
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_index_lag.py", "-v", "-s", "--tb=short"],
    capture_output=True, text=True,
)
print(result.stdout); print(result.stderr, file=sys.stderr); sys.exit(result.returncode)