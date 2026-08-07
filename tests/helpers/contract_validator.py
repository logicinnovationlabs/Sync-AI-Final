"""Z1 contract validator helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def load_contract(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_contract_paths(contracts_dir: Path) -> List[Path]:
    return sorted(Path(contracts_dir).glob("*-contract.yaml"))


def validate_response_shape(data: Any, schema: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if not schema:
        return errors
    expected = schema.get("type")
    if expected == "object" and not isinstance(data, dict):
        errors.append(f"expected object, got {type(data).__name__}")
    elif expected == "array" and not isinstance(data, list):
        errors.append(f"expected array, got {type(data).__name__}")
    elif expected == "string" and not isinstance(data, str):
        errors.append(f"expected string, got {type(data).__name__}")
    elif expected == "integer" and not isinstance(data, int):
        errors.append(f"expected integer, got {type(data).__name__}")
    return errors


def endpoint_from_contract(contract: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for path, methods in (contract.get("paths") or {}).items():
        for method in methods:
            out.append((path, method.upper()))
    return out


def require_contracts(contracts_dir: Path) -> List[Path]:
    paths = list_contract_paths(contracts_dir)
    if not paths:
        raise FileNotFoundError(f"No *-contract.yaml found under {contracts_dir}")
    return paths
