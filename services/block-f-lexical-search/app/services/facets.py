"""Facet aggregation helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

FACET_FIELDS = ("object_type", "source", "repository", "owner", "language", "tags")


def compute_facets(
    docs: Iterable[Dict[str, Any]],
    facet_fields: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute exact facet counts over an already ACL-filtered doc set.

    Tag fields are multi-valued; each tag increments independently.
    """
    fields = [f for f in facet_fields if f in FACET_FIELDS]
    counters: Dict[str, Counter] = {f: Counter() for f in fields}

    for doc in docs:
        for field in fields:
            value = doc.get(field)
            if value is None or value == "":
                continue
            if field == "tags":
                tags = value if isinstance(value, list) else [value]
                # Count each distinct tag once per document (matches OpenSearch terms agg).
                for tag in dict.fromkeys(str(t) for t in tags if t):
                    counters[field][tag] += 1
            else:
                counters[field][str(value)] += 1

    out: Dict[str, List[Dict[str, Any]]] = {}
    for field, counter in counters.items():
        out[field] = [
            {"value": value, "count": count}
            for value, count in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        ]
    return out
