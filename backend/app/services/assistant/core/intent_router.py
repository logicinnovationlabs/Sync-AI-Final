"""Intent classification for the orchestrator state machine."""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable


class Intent(str, Enum):
    SEARCH = "search"
    READ = "read"
    CHAT = "chat"
    GREETING = "greeting"


_READ_RE = re.compile(
    r"\b(read|open|show\s+(me\s+)?(the\s+)?(full|entire)|document\s+#?\w+|blob[:/])\b",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(find|search|look\s+up|where\s+is|who\s+knows|docs?\s+about|related\s+to)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(
    r"^\s*("
    r"hi|hello|hey|hiya|yo|sup|howdy|"
    r"good\s+(morning|afternoon|evening)|"
    r"thanks|thank\s+you|thx|ty|"
    r"ok|okay|cool|great|nice|got\s+it|"
    r"bye|goodbye|see\s+ya"
    r")[\s!.?]*$",
    re.IGNORECASE,
)


def is_greeting_or_chitchat(prompt: str) -> bool:
    """True for greetings / acknowledgements that must not trigger corpus dump."""
    text = (prompt or "").strip()
    if not text:
        return True
    if _GREETING_RE.match(text):
        return True
    words = text.split()
    if (
        len(words) <= 2
        and "?" not in text
        and not _SEARCH_RE.search(text)
        and not _READ_RE.search(text)
    ):
        return True
    return False


def classify_intent(prompt: str, *, attachment_ids: Iterable[str] | None = None) -> Intent:
    """
    Classify into greeting / search / read / chat.

    Heuristic only — does not inspect ACL. Attachment presence biases toward read.
    """
    text = (prompt or "").strip()
    attachments = list(attachment_ids or [])
    if is_greeting_or_chitchat(text) and not attachments:
        return Intent.GREETING
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
    if len(text.split()) >= 3:
        return Intent.SEARCH
    return Intent.CHAT
