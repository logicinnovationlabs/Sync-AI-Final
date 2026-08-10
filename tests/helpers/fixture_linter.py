"""Z2 fixture-linter: verify cross-references inside /fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class LintIssue:
    file: str
    message: str
    reference: str
    severity: str = "error"


@dataclass
class LintReport:
    document_ids: int = 0
    principal_ids: int = 0
    group_ids: int = 0
    errors: List[LintIssue] = field(default_factory=list)
    warnings: List[LintIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def lint_fixtures(fixtures_path: Path) -> LintReport:
    fixtures: Dict[str, Any] = {}
    for file_path in Path(fixtures_path).glob("*.json"):
        if file_path.name == "MANIFEST.json":
            continue
        with open(file_path, encoding="utf-8") as f:
            fixtures[file_path.stem] = json.load(f)

    document_ids = {d["id"] for d in fixtures.get("documents", {}).get("documents", []) if "id" in d}
    principal_ids = {p["id"] for p in fixtures.get("principals", {}).get("principals", []) if "id" in p}
    group_ids = {g["id"] for g in fixtures.get("groups", {}).get("groups", []) if "id" in g}

    report = LintReport(
        document_ids=len(document_ids),
        principal_ids=len(principal_ids),
        group_ids=len(group_ids),
    )

    # MANIFEST check
    manifest_path = Path(fixtures_path) / "MANIFEST.json"
    if not manifest_path.exists():
        report.errors.append(LintIssue("MANIFEST.json", "Missing MANIFEST.json", "root"))
    else:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for name in manifest.get("fixtures", []):
            if name not in fixtures and name != "crawl_expectations":
                # Accept either <name>.json or a directory fixture (e.g. code_corpus/).
                json_path = Path(fixtures_path) / f"{name}.json"
                dir_path = Path(fixtures_path) / name
                if not json_path.exists() and not dir_path.is_dir():
                    report.errors.append(
                        LintIssue("MANIFEST.json", f"Listed fixture missing: {name}", name)
                    )

    for idx, label in enumerate(fixtures.get("relevance_labels", {}).get("labels", [])):
        doc_id = label.get("document_id")
        if doc_id and doc_id not in document_ids:
            report.errors.append(
                LintIssue("relevance_labels.json", f"Document ID '{doc_id}' not found", f"labels[{idx}]")
            )

    for idx, entry in enumerate(fixtures.get("acl_matrix", {}).get("entries", [])):
        pid = entry.get("principal_id")
        did = entry.get("document_id")
        if pid and pid not in principal_ids:
            report.errors.append(
                LintIssue("acl_matrix.json", f"Principal ID '{pid}' not found", f"entries[{idx}]")
            )
        if did and did not in document_ids:
            report.errors.append(
                LintIssue("acl_matrix.json", f"Document ID '{did}' not found", f"entries[{idx}]")
            )
        via = entry.get("via_group")
        if via and via not in group_ids:
            report.errors.append(
                LintIssue("acl_matrix.json", f"Group ID '{via}' not found", f"entries[{idx}]")
            )

    for idx, identity in enumerate(fixtures.get("multi_source_identities", {}).get("identities", [])):
        pid = identity.get("principal_id")
        if pid and pid not in principal_ids:
            report.errors.append(
                LintIssue(
                    "multi_source_identities.json",
                    f"Principal ID '{pid}' not found",
                    f"identities[{idx}]",
                )
            )

    known = document_ids | principal_ids | group_ids
    for idx, edge in enumerate(fixtures.get("graph_edges", {}).get("edges", [])):
        for key in ("source", "target"):
            ref = edge.get(key)
            if ref and ref not in known:
                report.errors.append(
                    LintIssue("graph_edges.json", f"Edge {key} '{ref}' unknown", f"edges[{idx}]")
                )

    for idx, group in enumerate(fixtures.get("groups", {}).get("groups", [])):
        for mid in group.get("members", []):
            if mid not in principal_ids:
                report.errors.append(
                    LintIssue("groups.json", f"Member '{mid}' unknown", f"groups[{idx}].members")
                )

    for idx, doc in enumerate(fixtures.get("documents", {}).get("documents", [])):
        for acl_ref in doc.get("acl", []):
            if acl_ref not in principal_ids and acl_ref not in group_ids:
                report.errors.append(
                    LintIssue("documents.json", f"ACL ref '{acl_ref}' unknown", f"documents[{idx}].acl")
                )
        owner = doc.get("owner_id")
        if owner and owner not in principal_ids:
            report.errors.append(
                LintIssue("documents.json", f"Owner '{owner}' unknown", f"documents[{idx}]")
            )

    for case in fixtures.get("acl_redteam_cases", {}).get("cases", []):
        pid = case.get("principal_id")
        if pid and pid not in principal_ids:
            report.errors.append(
                LintIssue("acl_redteam_cases.json", f"Principal '{pid}' unknown", case.get("case_id", "?"))
            )
        for forbidden in case.get("forbidden_document_ids", []):
            if forbidden not in document_ids:
                report.errors.append(
                    LintIssue(
                        "acl_redteam_cases.json",
                        f"Forbidden doc '{forbidden}' unknown",
                        case.get("case_id", "?"),
                    )
                )

    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Lint Block Z fixtures")
    parser.add_argument("--fixtures", default=None)
    args = parser.parse_args()
    path = Path(args.fixtures) if args.fixtures else Path(__file__).resolve().parents[2] / "fixtures"
    report = lint_fixtures(path)
    print(f"documents={report.document_ids} principals={report.principal_ids} groups={report.group_ids}")
    print(f"errors={len(report.errors)} warnings={len(report.warnings)}")
    for err in report.errors:
        print(f"ERROR {err.file}: {err.message} ({err.reference})")
    for warn in report.warnings:
        print(f"WARN {warn.file}: {warn.message} ({warn.reference})")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
