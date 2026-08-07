"""Z3 mock-to-real swap shape comparison."""

from __future__ import annotations

from typing import Any, Dict, List

VARIABLE_KEYS = {"request_id", "timestamp", "elapsed_ms", "trace_id", "span_id", "took_ms"}


def normalize_response_shape(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: normalize_response_shape(v)
            for k, v in data.items()
            if k not in VARIABLE_KEYS
        }
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return [normalize_response_shape(item) for item in data[:2]]
        return data[:5]
    if isinstance(data, (int, float)):
        return "<number>"
    if isinstance(data, str):
        return "<string>"
    if isinstance(data, bool):
        return "<bool>"
    if data is None:
        return None
    return type(data).__name__


def compare_shapes(mock_data: Dict, real_data: Dict, path: str = "") -> List[str]:
    differences: List[str] = []
    mock_norm = normalize_response_shape(mock_data)
    real_norm = normalize_response_shape(real_data)
    if type(mock_norm) != type(real_norm):
        return [f"{path or 'root'}: type {type(mock_norm).__name__} vs {type(real_norm).__name__}"]
    if isinstance(mock_norm, dict):
        mock_keys = set(mock_norm)
        real_keys = set(real_norm)
        if mock_keys != real_keys:
            differences.append(
                f"{path or 'root'}: keys +{real_keys - mock_keys} -{mock_keys - real_keys}"
            )
        for key in mock_keys & real_keys:
            differences.extend(
                compare_shapes(mock_norm[key], real_norm[key], f"{path}.{key}" if path else key)
            )
    elif isinstance(mock_norm, list):
        if mock_norm and real_norm:
            differences.extend(compare_shapes(mock_norm[0], real_norm[0], f"{path}[0]"))
    return differences
