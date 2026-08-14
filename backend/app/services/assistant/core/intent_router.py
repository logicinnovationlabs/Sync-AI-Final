"""Intent classification for the orchestrator state machine."""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable


class Intent(str, Enum):
    SEARCH = "search"
    READ = "read"
    CHAT = "chat"


_READ_RE = re.compile(
    r"\b(read|open|show\s+(me\s+)?(the\s+)?(full|entire)|document\s+#?\w+|blob[:/])\b",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(find|search|look\s+up|where\s+is|who\s+knows|docs?\s+about|related\s+to)\b",
    re.IGNORECASE,
)


def classify_intent(prompt: str, *, attachment_ids: Iterable[str] | None = None) -> Intent:
    """
    Classify into search / read / chat.

    Heuristic only — does not inspect ACL. Attachment presence biases toward read.
    """
    text = (prompt or "").strip()
    attachments = list(attachment_ids or [])
    if attachments and _READ_RE.search(text):
        return Intent.READ
    if attachments and re.search(r"\b(this|attached|file)\b", text, re.IGNORECASE):
        return Intent.READ
    if _READ_RE.search(text):
        return Intent.READ
    if _SEARCH_RE.search(text) or ("?" in text and len(text.split()) <= 24):
        return Intent.SEARCH
    if len(text.split()) <= 2:
        return Intent.CHAT
    # Default: treat substantive prompts as search so retrieval runs.
    if len(text.split()) >= 3:
        return Intent.SEARCH
    return Intent.CHAT
