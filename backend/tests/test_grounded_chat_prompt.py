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
    assert "Answer ONLY using the document context" in GROUNDED_SYSTEM_PROMPT
    assert REFUSE_TEXT in GROUNDED_SYSTEM_PROMPT
    assert "Here is what I found" in GROUNDED_SYSTEM_PROMPT  # forbidden preamble called out
    assert "3 Minute Monday" in GROUNDED_SYSTEM_PROMPT or "3MM" in GROUNDED_SYSTEM_PROMPT


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
    assert "doc-leave-policy" in prompt or "Leave policy" in prompt
    assert "18 days" in prompt
    assert "Prior conversation" in prompt
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
    assert prompt.index("DOCUMENTS:") < prompt.index("Prior conversation")


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


def test_completion_text_reads_list_content_and_reasoning():
    class ChoiceList:
        message = type(
            "M",
            (),
            {"content": [{"type": "text", "text": "From [1]: unusual sign-in."}]},
        )()
        finish_reason = "stop"

    class RespList:
        choices = [ChoiceList()]
        error = None

    text, err = _completion_text(RespList())
    assert err is None
    assert "unusual sign-in" in text

    class ChoiceReasoning:
        message = type(
            "M",
            (),
            {"content": "", "reasoning": "Yes — Microsoft Entra flagged a new device [1]."},
        )()
        finish_reason = "stop"

    class RespReasoning:
        choices = [ChoiceReasoning()]
        error = None

    text, err = _completion_text(RespReasoning())
    assert err is None
    assert "Entra" in text


def test_completion_text_from_openrouter_dict():
    text, err = _completion_text(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": None,
                        "reasoning": "Microsoft Entra flagged a new sign-in [1].",
                    },
                }
            ]
        }
    )
    assert err is None
    assert "Entra" in text


def test_plain_source_text_strips_gmail_html():
    from app.services.assistant.infrastructure.chat_provider import (
        format_source_block,
        plain_source_text,
        source_text_is_usable,
    )

    html_mail = (
        "<style>.x{color:red}</style><p>Security alert: unusual sign-in</p>"
        "<div>Location: Mumbai</div>"
    )
    assert "Security alert" in plain_source_text(html_mail)
    assert ".x{" not in plain_source_text(html_mail)
    assert source_text_is_usable(html_mail)
    block = format_source_block(
        {"document_id": "mail-1", "title": "Alert", "snippet": html_mail},
        1,
    )
    assert "Security alert" in block
    assert "<style" not in block


def test_format_source_block_includes_from_email_for_newsletters():
    from app.services.assistant.infrastructure.chat_provider import (
        assemble_chat_messages,
        format_source_block,
    )

    hit = {
        "document_id": "gmail-3mm",
        "title": "3MM: Emotions, Millionaires & Rebels",
        "snippet": (
            "The world claims to love authenticity but runs away as soon as it sees it."
        ),
        "from_email": "Chris Williamson <chris@chriswillx.com>",
        "metadata": {
            "from_email": "Chris Williamson <chris@chriswillx.com>",
            "source_type": "google_gmail",
        },
        "boosted_score": 0.3,
    }
    block = format_source_block(hit, 1)
    assert "from=Chris Williamson <chris@chriswillx.com>" in block
    assert "3MM:" in block
    assert "authenticity" in block
    assert "[Source 1:" in block

    _messages, prompt = assemble_chat_messages(
        "3 MINUTE MONDAY what does Chris williamson says??",
        [hit],
    )
    assert "from=Chris Williamson" in prompt
    assert "QUESTION:" in prompt
    assert "DOCUMENTS:" in prompt


def test_payload_to_hit_keeps_sender_and_long_snippet():
    from app.api.v1.search.federated import _payload_to_hit

    body = ("Authenticity paragraph. " * 80).strip()
    hit = _payload_to_hit(
        {
            "id": "doc-1",
            "title": "3MM: Emotions, Millionaires & Rebels",
            "content": body,
            "source_type": "google_gmail",
            "structured_metadata": {
                "from_email": "Chris Williamson <chris@chriswillx.com>",
                "subject": "3MM: Emotions, Millionaires & Rebels",
            },
        },
        0.42,
    )
    assert hit["from_email"].startswith("Chris Williamson")
    assert hit["metadata"]["from_email"].startswith("Chris Williamson")
    assert len(hit["snippet"]) > 400
    assert len(hit["snippet"]) <= 6000


def test_openrouter_may_reason_only_for_thinking_models():
    from app.services.assistant.infrastructure.chat_provider import OpenRouterChatProvider

    assert OpenRouterChatProvider._may_reason("qwen/qwen3-32b")
    assert OpenRouterChatProvider._may_reason("qwen/qwq-32b-preview")
    assert not OpenRouterChatProvider._may_reason("qwen/qwen-2.5-72b-instruct")


@pytest.mark.asyncio
async def test_gemini_requests_output_dimensionality():
    calls = {}

    class FakeGenai:
        @staticmethod
        def configure(api_key):  # noqa: ARG001
            return None

        @staticmethod
        def embed_content(**kwargs):
            calls.update(kwargs)
            dim = int(kwargs.get("output_dimensionality") or 768)
            return {"embedding": [0.1] * dim}

    import app.services.embedding as emb_mod

    provider = emb_mod.GeminiEmbeddingProvider.__new__(emb_mod.GeminiEmbeddingProvider)
    provider.api_key = "test"
    provider.model = "models/gemini-embedding-001"
    provider.dimension = 384
    provider.genai = FakeGenai()

    vectors = await provider.embed_texts(["hello world"])
    assert calls.get("output_dimensionality") == 384
    assert calls.get("task_type") in (None, "retrieval_document", "retrieval_query")
    assert len(vectors[0]) == 384


@pytest.mark.asyncio
async def test_embed_query_uses_retrieval_query_task():
    calls = {}

    class FakeGenai:
        @staticmethod
        def configure(api_key):  # noqa: ARG001
            return None

        @staticmethod
        def embed_content(**kwargs):
            calls.update(kwargs)
            dim = int(kwargs.get("output_dimensionality") or 768)
            return {"embedding": [0.1] * dim}

    import app.services.embedding as emb_mod

    provider = emb_mod.GeminiEmbeddingProvider.__new__(emb_mod.GeminiEmbeddingProvider)
    provider.api_key = "test"
    provider.model = "models/gemini-embedding-001"
    provider.dimension = 3072
    provider.genai = FakeGenai()
    service = emb_mod.EmbeddingService.__new__(emb_mod.EmbeddingService)
    service.provider = provider

    vec = await service.embed_query("grasshopper and ant")
    assert calls.get("task_type") == "retrieval_query"
    assert len(vec) == 3072

    calls.clear()
    await service.embed_documents(["passage one"])
    assert calls.get("task_type") == "retrieval_document"
