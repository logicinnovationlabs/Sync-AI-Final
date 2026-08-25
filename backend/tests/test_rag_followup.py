"""Rule #6 — Follow-up question correctness.

Verify that follow-up questions (e.g. "what about their reporting line?")
resolve correctly against the same document after a single-query fix.
Follow-up questions frequently fail even after a single-query fix because
query rewriting/context carry-over is a separate mechanism from
single-turn retrieval.

Uses FakeChatProvider and in-memory stores — no external dependencies.
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_history(
    turns: List[tuple[str, str]],
) -> List[Dict[str, str]]:
    """Build conversation history from (user, assistant) turn pairs."""
    history = []
    for user_msg, assistant_msg in turns:
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
    return history


def _make_ranked_hits(
    documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create ranked hit dicts from document dicts."""
    hits = []
    for i, doc in enumerate(documents):
        hits.append({
            "document_id": doc.get("id", f"doc-{i}"),
            "title": doc.get("title", "Test Document"),
            "snippet": doc.get("content", ""),
            "score": 0.9 - (i * 0.1),
            "boosted_score": 0.9 - (i * 0.1),
            "base_score": 0.9 - (i * 0.1),
            "sources": ["vector"],
            "meta": doc.get("meta", {}),
        })
    return hits


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFollowUpQuestionCorrectness:
    """Rule #6: follow-up questions must resolve correctly."""

    def test_single_turn_produces_grounded_answer(self):
        """A single-turn query with sources should produce a grounded answer,
        not a refusal."""
        from app.services.assistant.infrastructure.chat_provider import (
            FakeChatProvider,
            assemble_chat_messages,
            REFUSE_TEXT,
        )

        provider = FakeChatProvider()
        doc_content = (
            "The project manager is responsible for planning, scheduling, "
            "risk management, and stakeholder communication. "
            "They report directly to the VP of Engineering."
        )
        hits = _make_ranked_hits([
            {"id": "pm-roles-doc", "title": "PM Role Description", "content": doc_content},
        ])

        messages, prompt_text = assemble_chat_messages(
            "What are the responsibilities of the project manager?",
            hits,
        )

        result = asyncio.get_event_loop().run_until_complete(
            provider.generate(messages, ranked_hits=hits)
        )

        # Should NOT refuse — sources are present
        assert REFUSE_TEXT not in result.text
        assert result.text.strip()
        assert "PM Role Description" in result.text or "project manager" in result.text.lower()

    def test_followup_gets_same_sources(self):
        """A follow-up question referencing the same document should still
        see the correct sources in the assembled prompt, NOT just history."""
        from app.services.assistant.infrastructure.chat_provider import (
            assemble_chat_messages,
        )

        doc_content = (
            "The project manager is responsible for planning, scheduling, "
            "risk management, and stakeholder communication. "
            "They report directly to the VP of Engineering."
        )
        hits = _make_ranked_hits([
            {"id": "pm-roles-doc", "title": "PM Role Description", "content": doc_content},
        ])

        # Simulate a follow-up with conversation history
        history = _make_session_history([
            (
                "What are the responsibilities of the project manager?",
                "The project manager is responsible for planning, scheduling, "
                "risk management, and stakeholder communication. [1]",
            ),
        ])

        messages, prompt_text = assemble_chat_messages(
            "What about their reporting line?",
            hits,
            conversation_history=history,
        )

        # The retrieved sources MUST be in the prompt (not just history)
        assert "VP of Engineering" in prompt_text
        assert "PM Role Description" in prompt_text

    def test_history_is_not_evidence(self):
        """Conversation history must NOT be treated as authoritative evidence.
        The prompt should clearly label history as non-evidence."""
        from app.services.assistant.infrastructure.chat_provider import (
            assemble_chat_messages,
        )

        hits = _make_ranked_hits([
            {
                "id": "doc-1",
                "title": "Real Source",
                "content": "The budget for 2025 is $5 million.",
            },
        ])

        # History contains a DIFFERENT claim that should not override sources
        history = _make_session_history([
            ("What is the budget?", "The budget is $10 million."),
        ])

        messages, prompt_text = assemble_chat_messages(
            "Can you confirm the budget amount?",
            hits,
            conversation_history=history,
        )

        # The prompt must contain the "not evidence" disclaimer for history
        assert "not evidence" in prompt_text.lower() or "not authoritative" in prompt_text.lower()
        # The real source data must be present
        assert "$5 million" in prompt_text

    def test_followup_with_empty_sources_refuses(self):
        """A follow-up with no matching sources must refuse, even if
        history has content."""
        from app.services.assistant.infrastructure.chat_provider import (
            FakeChatProvider,
            assemble_chat_messages,
            REFUSE_TEXT,
        )

        provider = FakeChatProvider()

        # No relevant hits for the follow-up
        hits: List[Dict[str, Any]] = []

        history = _make_session_history([
            (
                "Tell me about project alpha.",
                "Project Alpha involves building a new CRM system. [1]",
            ),
        ])

        messages, prompt_text = assemble_chat_messages(
            "What's the timeline for that?",
            hits,
            conversation_history=history,
        )

        result = asyncio.get_event_loop().run_until_complete(
            provider.generate(messages, ranked_hits=hits)
        )

        # Should refuse — no sources available for the follow-up
        assert REFUSE_TEXT in result.text

    def test_assembled_context_has_source_blocks(self):
        """Rule #6 + Rule #2 Stage 8: the assembled context must contain
        actual source blocks, not just the question."""
        from app.services.assistant.infrastructure.chat_provider import (
            assemble_chat_messages,
        )

        hits = _make_ranked_hits([
            {
                "id": "handbook-section",
                "title": "Employee Handbook",
                "content": "All employees must complete safety training within 30 days of hire.",
            },
        ])

        messages, prompt_text = assemble_chat_messages(
            "What is the deadline for safety training?",
            hits,
        )

        # Source block must be present with the document ID and content
        assert "handbook-section" in prompt_text
        assert "safety training" in prompt_text
        assert "30 days" in prompt_text
        # Must have the source block format
        assert "[1]" in prompt_text
