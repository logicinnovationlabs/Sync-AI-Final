"""Snippet generation with sentence boundaries, highlighting, and redaction."""

from __future__ import annotations

import re
from typing import List, Optional, Set

from app.services.tokenizer import tokenize

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _highlight(text: str, terms: Set[str]) -> str:
    """Wrap exact term hits with <em> tags (case-insensitive whole-word-ish)."""
    if not text or not terms:
        return text

    # Prefer longer terms first to avoid partial overlaps
    ordered = sorted(terms, key=len, reverse=True)

    def replacer(match: re.Match) -> str:
        return f"<em>{match.group(0)}</em>"

    out = text
    for term in ordered:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        out = pattern.sub(replacer, out)
    return out


def generate_snippet(
    title: str,
    body_text: str,
    comments_text: str,
    query: str,
    *,
    max_chars: int = 240,
    redact_fields: Optional[List[str]] = None,
) -> str:
    """
    Snippet pipeline (§11.3):
      1. Identify best matching spans
      2. Preserve sentence boundaries
      3. Redact hidden fields
      4. Annotate exact term hits with <em>
    """
    redact = set(redact_fields or [])
    parts: List[str] = []
    if "title" not in redact and title:
        parts.append(title)
    if "body_text" not in redact and body_text:
        parts.append(body_text)
    if "comments_text" not in redact and comments_text:
        parts.append(comments_text)

    corpus = " ".join(parts).strip()
    if not corpus:
        return ""

    query_terms = set(tokenize(query))
    sents = _sentences(corpus) or [corpus]

    # Score sentences by query-term overlap
    best_idx = 0
    best_score = -1
    for i, sent in enumerate(sents):
        tokens = set(tokenize(sent))
        score = len(tokens & query_terms)
        if score > best_score:
            best_score = score
            best_idx = i

    # Expand to neighboring sentences while under max_chars
    chosen = [sents[best_idx]]
    left, right = best_idx - 1, best_idx + 1
    while True:
        current = " ".join(chosen)
        grew = False
        if left >= 0:
            candidate = sents[left] + " " + current
            if len(candidate) <= max_chars:
                chosen.insert(0, sents[left])
                left -= 1
                grew = True
                current = " ".join(chosen)
        if right < len(sents):
            candidate = current + " " + sents[right]
            if len(candidate) <= max_chars:
                chosen.append(sents[right])
                right += 1
                grew = True
        if not grew:
            break

    snippet = " ".join(chosen)
    if len(snippet) > max_chars:
        # Truncate at last space before limit, never mid-word if possible
        cut = snippet[:max_chars].rsplit(" ", 1)[0]
        snippet = cut + "…" if cut else snippet[:max_chars] + "…"

    return _highlight(snippet, query_terms)
