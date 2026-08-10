from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.setdefault("PYTHONPATH", str(ROOT))
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SEARCH_BACKEND", os.environ.get("SEARCH_BACKEND", "mock"))
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)
out = EVIDENCE / "test_output_f1.txt"
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_latency.py", "-v", "-s", "--tb=short"],
    capture_output=True, text=True,
)
out.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
print(result.stdout); print(result.stderr, file=sys.stderr); sys.exit(result.returncode)