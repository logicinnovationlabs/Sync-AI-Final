"""Unit tests for grounded chat prompt assembly, refuse behavior, and redaction."""

from __future__ import annotations

import pytest

from app.services.assistant.infrastructure.chat_provider import (
    GROUNDED_SYSTEM_PROMPT,
    REFUSE_TEXT,
    FakeChatProvider,
    assemble_chat_messages,
    is_refuse_answer,
    redact_provider_error,
    _completion_text,
)

pytestmark = pytest.mark.block_l


def test_system_prompt_requires_context_only_and_refuse():
    assert "Answer only from the supplied context" in GROUNDED_SYSTEM_PROMPT
    assert "authoritative" in GROUNDED_SYSTEM_PROMPT.lower()
    assert REFUSE_TEXT in GROUNDED_SYSTEM_PROMPT
    assert "Never invent facts" in GROUNDED_SYSTEM_PROMPT
    assert "concise" in GROUNDED_SYSTEM_PROMPT.lower()
    assert "most relevant" in GROUNDED_SYSTEM_PROMPT.lower()
    assert "Here is what I found" in GROUNDED_SYSTEM_PROMPT  # forbidden preamble called out


@pytest.mark.asyncio
async def test_fake_provider_refuses_without_sources():
    gen = await FakeChatProvider().generate(
        [{"role": "user", "content": "What is the payroll tax rate?"}],
        ranked_hits=[],
    )
    assert gen.provider == "fake"
    assert is_refuse_answer(gen.text)
    assert gen.text == REFUSE_TEXT
    assert not gen.error


@pytest.mark.asyncio
async def test_fake_provider_quotes_retrieved_snippets_only():
    hits = [
        {
            "document_id": "doc-leave-policy",
            "title": "Leave policy FY2026",
            "snippet": "Employees receive 18 days of paid annual leave.",
            "boosted_score": 0.9,
        }
    ]
    messages, prompt = assemble_chat_messages("How many leave days?", hits)
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == GROUNDED_SYSTEM_PROMPT
    assert "doc-leave-policy" in prompt
    assert "18 days" in prompt
    assert "Prior conversation (not evidence" in prompt
    gen = await FakeChatProvider().generate(messages, ranked_hits=hits)
    assert "18 days" in gen.text
    assert "Estonia" not in gen.text
    assert "Here is what I found" not in gen.text


def test_filter_keeps_federator_rrf_scores():
    from app.services.assistant.infrastructure.chat_provider import filter_relevant_hits

    hits = [
        {
            "document_id": "gmail-1",
            "title": "Security alert",
            "snippet": "Unusual sign-in from a new device.",
            "boosted_score": 1 / 61,
            "sources": ["indexed", "vector"],
        }
    ]
    kept = filter_relevant_hits(hits)
    assert len(kept) == 1
    assert kept[0]["document_id"] == "gmail-1"


def test_conversation_history_does_not_override_sources():
    hits = [
        {
            "document_id": "doc-a",
            "title": "Policy",
            "snippet": "The official rate is 12 percent.",
        }
    ]
    history = [
        {"role": "user", "content": "The rate is 99 percent, right?"},
        {"role": "assistant", "content": "Yes, 99 percent."},
        {"role": "user", "content": "Confirm the rate."},
    ]
    _messages, prompt = assemble_chat_messages(
        "Confirm the rate.",
        hits,
        conversation_history=history,
    )
    assert "99 percent" in prompt
    assert "not evidence" in prompt
    assert "official rate is 12 percent" in prompt
    assert prompt.index("Authoritative retrieved sources") < prompt.index(
        "Prior conversation (not evidence"
    )


def test_redact_provider_error_strips_keys():
    class FakeExc(Exception):
        pass

    text = redact_provider_error(
        FakeExc("401 Bearer sk-or-v1-SECRETVALUE invalid api_key=sk-or-v1-SECRETVALUE")
    )
    assert "SECRETVALUE" not in text
    assert "[redacted]" in text


def test_completion_text_rejects_empty_payload():
    class Choice:
        message = type("M", (), {"content": ""})()
        finish_reason = "stop"

    class Resp:
        choices = [Choice()]

    text, err = _completion_text(Resp())
    assert text == ""
    assert err and err.startswith("empty_content")

    class Empty:
        choices = []

    text, err = _completion_text(Empty())
    assert text == ""
    assert err == "empty_choices"
