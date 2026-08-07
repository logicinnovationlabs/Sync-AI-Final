"""PASS/FAIL criterion reporting in JSON, HTML, and Markdown."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _collect(results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    blocks = {}
    total = passed = failed = skipped = 0
    for block, items in results.items():
        b_pass = sum(1 for i in items if i.get("outcome") == "passed")
        b_fail = sum(1 for i in items if i.get("outcome") == "failed")
        b_skip = sum(1 for i in items if i.get("outcome") == "skipped")
        total += len(items)
        passed += b_pass
        failed += b_fail
        skipped += b_skip
        blocks[block] = {
            "results": items,
            "passed": b_fail == 0 and b_pass > 0,
            "counts": {"passed": b_pass, "failed": b_fail, "skipped": b_skip},
        }
    return {
        "timestamp": datetime.now().isoformat(),
        "blocks": blocks,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            # Skipped is NOT treated as pass
            "all_passed": failed == 0 and passed > 0 and skipped == 0,
            "all_executed_passed": failed == 0 and passed > 0,
        },
    }


def write_json(report: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    lines = ["# Block Z-O Verification Report", "", f"Generated: {report['timestamp']}", ""]
    s = report["summary"]
    lines.append(
        f"**Summary:** {s['passed']} passed, {s['failed']} failed, {s['skipped']} skipped "
        f"(skipped does not count as pass)"
    )
    lines.append("")
    for block, data in report["blocks"].items():
        status = "PASS" if data["passed"] else "FAIL"
        lines.append(f"## Block {block} — {status}")
        lines.append("")
        lines.append("| Criterion | Result | Message |")
        lines.append("|-----------|--------|---------|")
        for item in data["results"]:
            lines.append(
                f"| {item.get('criterion','?')} | {item.get('outcome','?').upper()} | {item.get('message','')} |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(report: Dict[str, Any], path: Path) -> None:
    s = report["summary"]
    rows = []
    for block, data in report["blocks"].items():
        for item in data["results"]:
            color = {"passed": "#0a7", "failed": "#c33", "skipped": "#a80"}.get(item.get("outcome"), "#333")
            rows.append(
                f"<tr><td>{block}</td><td>{item.get('criterion')}</td>"
                f"<td style='color:{color}'>{item.get('outcome')}</td>"
                f"<td>{item.get('message','')}</td></tr>"
            )
    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Z-O Verification</title>
<style>body{{font-family:Segoe UI,sans-serif;margin:2rem}} table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ddd;padding:.5rem;text-align:left}} th{{background:#f4f4f4}}</style>
</head><body>
<h1>Block Z-O Verification Report</h1>
<p>{s['passed']} passed / {s['failed']} failed / {s['skipped']} skipped — skipped is not pass</p>
<table><thead><tr><th>Block</th><th>Criterion</th><th>Result</th><th>Message</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
</body></html>
"""
    path.write_text(html, encoding="utf-8")


def generate_reports(results: Dict[str, List[Dict[str, Any]]], output_dir: Path, fmt: str = "json") -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _collect(results)
    formats = [f.strip() for f in fmt.split(",")] if fmt != "all" else ["json", "html", "markdown"]
    if "json" in formats:
        write_json(report, output_dir / "report.json")
    if "markdown" in formats or "md" in formats:
        write_markdown(report, output_dir / "report.md")
    if "html" in formats:
        write_html(report, output_dir / "report.html")
    return report
