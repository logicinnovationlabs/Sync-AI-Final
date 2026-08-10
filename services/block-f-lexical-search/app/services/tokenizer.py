"""Code-aware tokenization: camelCase, PascalCase, snake_case, kebab-case."""

from __future__ import annotations

import re
from typing import List

# Split on camelCase / PascalCase boundaries and underscores / hyphens
_CAMEL = re.compile(r"([A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+)")
_SPLITTERS = re.compile(r"[_\-\s./\\]+")
_NON_ALNUM = re.compile(r"[^a-zA-Z0-9_]+")


def tokenize(text: str) -> List[str]:
    """
    Tokenize text with code-aware splitting.

    Examples:
      getUserInfo  -> ["get", "user", "info"]
      user_info    -> ["user", "info"]
      UserInfo     -> ["user", "info"]
      get-user-info -> ["get", "user", "info"]
    """
    if not text:
        return []
    tokens: List[str] = []
    for part in _SPLITTERS.split(text):
        if not part:
            continue
        # Further split camelCase / PascalCase
        chunks = _CAMEL.findall(part)
        if not chunks:
            cleaned = _NON_ALNUM.sub("", part).lower()
            if cleaned:
                tokens.append(cleaned)
            continue
        for chunk in chunks:
            cleaned = chunk.lower()
            if cleaned:
                tokens.append(cleaned)
    return tokens


def tokenize_query(query: str) -> List[str]:
    """Tokenize a user query (same analyzer as indexed fields)."""
    return tokenize(query)
