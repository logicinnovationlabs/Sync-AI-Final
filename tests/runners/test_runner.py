"""Unified Block Z-O test runner."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from tests.runners.report_generator import generate_reports

ALL_BLOCKS = ["Z", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O"]
CRITERION_RE = re.compile(r"test_([a-z])(\d+)_", re.I)
RESULT_RE = re.compile(r"::(\S+)\s+(PASSED|FAILED|SKIPPED)")


def _criterion_from_nodeid(nodeid: str) -> str:
    name = nodeid.split("::")[-1]
    m = CRITERION_RE.search(name)
    if not m:
        return name
    return f"{m.group(1).upper()}{m.group(2)}"


def _block_from_nodeid(nodeid: str) -> str:
    normalized = nodeid.replace(chr(92), "/")
    for part in normalized.split("/"):
        if part.startswith("test_block_") and part.endswith(".py"):
            return part.replace("test_block_", "").replace(".py", "").upper()
    if "TestBlock" in nodeid:
        return nodeid.split("TestBlock")[-1].split("::")[0].upper()
    return "?"


def run(blocks: List[str], phase: str, output_dir: Path, fmt: str) -> int:
    repo = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["TEST_PHASE"] = phase
    env.setdefault("USE_INPROCESS_MOCKS", "true")
    paths = [str(repo / "tests" / "test_blocks" / f"test_block_{b.lower()}.py") for b in blocks]
    cmd = [sys.executable, "-m", "pytest", *paths, "-v", "--tb=short"]
    proc = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    results: Dict[str, List[dict]] = {b: [] for b in blocks}
    for line in proc.stdout.splitlines():
        if "::" not in line:
            continue
        m = RESULT_RE.search(line)
        if not m:
            continue
        test_name = m.group(1)
        outcome = m.group(2).lower()
        block = _block_from_nodeid(line)
        if block == "?":
            for b in blocks:
                marker = f"test_block_{b.lower()}.py"
                if marker in line.replace(chr(92), "/"):
                    block = b
                    break
        if block not in results:
            results[block] = []
        results[block].append(
            {
                "criterion": _criterion_from_nodeid(test_name),
                "outcome": outcome,
                "message": outcome,
                "nodeid": test_name,
            }
        )

    report = generate_reports(results, output_dir, fmt=fmt)
    summary = report["summary"]
    print(
        f"Runner summary: passed={summary['passed']} failed={summary['failed']} "
        f"skipped={summary['skipped']} (skipped!=pass)"
    )
    if summary["failed"] > 0 or summary["passed"] == 0:
        return 1
    return 0 if proc.returncode == 0 else proc.returncode


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified Block Z-O verification runner")
    parser.add_argument("--blocks", nargs="+", default=ALL_BLOCKS, help="Blocks to run, e.g. Z A B")
    parser.add_argument(
        "--phase",
        default=os.environ.get("TEST_PHASE", "provisional"),
        choices=["provisional", "integration"],
    )
    parser.add_argument("--format", default="json", help="json, html, markdown, or comma-separated/all")
    parser.add_argument("--output-dir", default="./test-results")
    args = parser.parse_args(argv)
    blocks = [b.upper() for b in args.blocks]
    for b in blocks:
        if b not in ALL_BLOCKS:
            parser.error(f"Unknown block {b}")
    return run(blocks, args.phase, Path(args.output_dir), args.format)


if __name__ == "__main__":
    raise SystemExit(main())
