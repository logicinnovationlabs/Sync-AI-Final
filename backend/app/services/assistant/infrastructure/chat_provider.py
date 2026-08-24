"""Swappable chat LLM providers for Block L.

Mirrors EmbeddingProvider / GeminiEmbeddingProvider / FakeEmbeddingProvider:
a small Protocol, env-selected implementations, constructed from Settings.

``LLM_CHAT_PROVIDER`` is independent of ``LLM_PROVIDER`` (embeddings).
Values: ``fake`` (default for offline tests) | ``openrouter`` (OpenAI-compatible
client at OpenRouter, model from ``QWEN_MODEL``).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
QWEN_TIMEOUT_S = 90.0
MAX_SOURCE_CHARS = 900
MAX_CONTEXT_CHARS = 6000
MAX_HISTORY_TURNS = 6
TOP_K_SOURCES = 4
# Cosine / ANN similarity (Qdrant). Weak neighbors are noise.
MIN_COSINE_SCORE = 0.12
# Federator RRF uses k=60, so rank-1 is ~1/61 ≈ 0.016 — not cosine.
# The old 0.12 cutoff dropped every fused hit and the model always refused.
MIN_RRF_SCORE = 0.008

REFUSE_TEXT = (
    "I don't have enough information in the provided context to answer that accurately."
)

GREETING_TEXT = (
    "Hi — I can help with your indexed Drive, Gmail, and docs. "
    "Ask a specific question and I’ll answer from your sources."
)

GROUNDED_SYSTEM_PROMPT = """You are SynQ, a precise enterprise assistant. Answer only from the supplied context.

Voice (Claude-like):
- Be concise, clear, and warm. Prefer 2–5 short sentences or a tight bullet list.
- Lead with the direct answer. No preamble like "Here is what I found" or dump of every source.
- Skip filler, speculation, and unrelated documents.

Grounding rules (authoritative):
- Treat the retrieved sources as the only authoritative evidence. Do not use world knowledge.
- Users often omit dates, document names, or account names. Infer from the most relevant / most recent matching item in the sources when the default is obvious.
- Prior conversation is only for resolving references ("that one"). It is not evidence and must never override retrieved sources.
- If several sources conflict and you cannot tell which one they mean, ask one short clarification.
- If the question is about which email/account/mailbox the user is using, answer from Signed-in account and From/To headers in the sources.
- If nothing in the sources (or signed-in account, for mailbox identity only) is related to the question, reply with exactly: I don't have enough information in the provided context to answer that accurately.
- Never invent facts, citations, file names, numbers, policies, dates, or steps that are not in the sources.
- Cite important claims with source ids in square brackets, e.g. [1] or [1, p.3]. Use at most 2–3 citations.
- Prefer a precise, short answer over a dump of snippets."""

# Inspectable log of prompts actually sent to a chat provider. Tests (L1)
# assert restricted content never appears here. Entries never include API keys.
PROMPT_LOG: List[Dict[str, Any]] = []
_FAKE_PROVIDER_WARNED = False


def clear_prompt_log() -> None:
    PROMPT_LOG.clear()


def record_prompt(entry: Dict[str, Any]) -> None:
    PROMPT_LOG.append(entry)
    if len(PROMPT_LOG) > 500:
        del PROMPT_LOG[:250]


def redact_provider_error(exc: BaseException) -> str:
    """User-facing provider error with secrets stripped."""
    text = str(exc)
    text = re.sub(r"sk-[A-Za-z0-9_\-]+", "[redacted]", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)api[_-]?key['\"]?\s*[:=]\s*\S+", "api_key=[redacted]", text)
    if len(text) > 240:
        text = text[:240] + "…"
    return text


def is_refuse_answer(text: str) -> bool:
    normalized = (
        (text or "")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .strip()
        .lower()
    )
    return "don't have enough information in the provided context" in normalized


@dataclass
class ChatGeneration:
    """Minimal generate() result the graph node consumes."""

    text: str
    provider: str
    citations_meta: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    timings_ms: Dict[str, float] = field(default_factory=dict)


class ChatProvider(Protocol):
    """LlmProvider-shaped protocol. Swap implementations via config only."""

    name: str

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration: ...


def _hit_meta(hit: Dict[str, Any]) -> Dict[str, Any]:
    meta = hit.get("meta") if isinstance(hit.get("meta"), dict) else {}
    nested = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    extra = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}

    def first(*keys: str) -> Any:
        for key in keys:
            for src in (hit, meta, nested, extra):
                value = src.get(key)
                if value not in (None, ""):
                    return value
        return None

    return {
        "document_id": str(first("document_id", "id") or ""),
        "chunk_id": first("chunk_id", "chunkId"),
        "page": first("page", "page_number", "pageNumber"),
        "title": str(first("title") or ""),
        "source": first("source", "source_type", "repository"),
    }


def format_source_block(hit: Dict[str, Any], index: int) -> str:
    meta = _hit_meta(hit)
    snippet = str(hit.get("snippet") or hit.get("body") or "").strip()
    if len(snippet) > MAX_SOURCE_CHARS:
        snippet = snippet[:MAX_SOURCE_CHARS].rstrip() + "…"
    header_parts = [f"[{index}]", f"document_id={meta['document_id'] or 'unknown'}"]
    if meta["title"]:
        header_parts.append(f"title={meta['title']}")
    if meta["chunk_id"]:
        header_parts.append(f"chunk_id={meta['chunk_id']}")
    if meta["page"] not in (None, ""):
        header_parts.append(f"page={meta['page']}")
    if meta["source"]:
        header_parts.append(f"source={meta['source']}")
    return " ".join(header_parts) + "\n" + (snippet or "(empty snippet)")


def debug_source_chunks(ranked_hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact retrieval debug payload (ACL-filtered hits only; no secrets)."""
    chunks: List[Dict[str, Any]] = []
    for i, hit in enumerate(list(ranked_hits)[:TOP_K_SOURCES], start=1):
        meta = _hit_meta(hit)
        snippet = str(hit.get("snippet") or hit.get("body") or "").strip()
        chunks.append(
            {
                "source_id": f"[{i}]",
                "document_id": meta["document_id"] or None,
                "chunk_id": meta["chunk_id"],
                "page": meta["page"],
                "title": meta["title"] or None,
                "source": meta["source"],
                "score": hit.get("boosted_score", hit.get("score")),
                "base_score": hit.get("base_score"),
                "snippet": snippet[:500],
            }
        )
    return chunks


def _hit_numeric_score(hit: Mapping[str, Any]) -> Optional[float]:
    meta = hit.get("meta") if isinstance(hit.get("meta"), dict) else {}
    for key in ("boosted_score", "score", "base_score", "fusion_score", "vector_score"):
        for src in (hit, meta):
            if not isinstance(src, dict) or key not in src:
                continue
            raw = src.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _is_rrf_score(score: float) -> bool:
    """RRF(k=60) tops out well below typical cosine similarity."""
    return 0.0 < score < 0.05


def filter_relevant_hits(
    ranked_hits: Sequence[Dict[str, Any]],
    *,
    min_score: float = MIN_COSINE_SCORE,
    limit: int = TOP_K_SOURCES,
) -> List[Dict[str, Any]]:
    """Keep hits strong enough to ground an answer (cosine or RRF)."""
    kept: List[Dict[str, Any]] = []
    for hit in ranked_hits:
        sources = hit.get("sources") or []
        if "document_reader" in sources or "document_reader_fallback" in sources:
            kept.append(dict(hit))
            if len(kept) >= limit:
                break
            continue

        score_f = _hit_numeric_score(hit)
        snippet = str(hit.get("snippet") or hit.get("body") or "").strip()
        if score_f is None:
            if snippet:
                kept.append(dict(hit))
            if len(kept) >= limit:
                break
            continue

        if _is_rrf_score(score_f):
            if score_f < MIN_RRF_SCORE:
                continue
        elif score_f < min_score:
            continue

        kept.append(dict(hit))
        if len(kept) >= limit:
            break
    return kept[:limit]


def assemble_chat_messages(
    user_prompt: str,
    ranked_hits: List[Dict[str, Any]],
    *,
    conversation_history: Optional[Sequence[Dict[str, Any]]] = None,
    account_email: Optional[str] = None,
) -> tuple[List[Dict[str, str]], str]:
    """Build chat messages from the user prompt + already-ACL-filtered hits.

    Retrieval (federator / document reader) is assumed to have filtered by
    the requesting principal before this runs. This function does not fetch
    extra corpus content. Conversation history is included only as a
    non-authoritative reference resolver.
    """
    relevant = filter_relevant_hits(ranked_hits)
    source_blocks: List[str] = []
    used = 0
    for i, hit in enumerate(relevant[:TOP_K_SOURCES], start=1):
        block = format_source_block(hit, i)
        if used + len(block) > MAX_CONTEXT_CHARS:
            break
        source_blocks.append(block)
        used += len(block) + 2
    sources_text = (
        "\n\n".join(source_blocks) if source_blocks else "(no authorized sources)"
    )

    history_lines: List[str] = []
    prior = list(conversation_history or [])
    if prior and prior[-1].get("role") == "user":
        prior = prior[:-1]
    for turn in prior[-MAX_HISTORY_TURNS:]:
        role = str(turn.get("role") or "user")
        if role not in ("user", "assistant"):
            continue
        content = str(turn.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        history_lines.append(f"{role}: {content[:400]}")
    history_text = (
        "\n".join(history_lines)
        if history_lines
        else "(none)"
    )

    account_line = (
        f"Signed-in account: {account_email.strip().lower()}\n"
        if (account_email or "").strip()
        else "Signed-in account: (not provided)\n"
    )
    user = (
        "Authoritative retrieved sources (the only allowed evidence):\n"
        f"{sources_text}\n\n"
        f"{account_line}"
        "Prior conversation (not evidence; do not invent facts from it; "
        "sources above win if they conflict):\n"
        f"{history_text}\n\n"
        "Answer the question directly and briefly. Do not summarize every source. "
        "Use only sources that actually answer the question. "
        "Ask a clarifying question only if the sources conflict or do not cover the topic.\n\n"
        f"Question:\n{user_prompt}"
    )
    messages = [
        {"role": "system", "content": GROUNDED_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    prompt_text = f"{GROUNDED_SYSTEM_PROMPT}\n\n{user}"
    return messages, prompt_text


class FakeChatProvider:
    """Deterministic synthesizer — keeps tests offline. Same shape as OpenRouter.

    Does not invent facts: with no sources it refuses; with sources it answers
    concisely from the top hit only (never dumps a numbered corpus list).
    """

    name = "fake"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration:
        started = time.perf_counter()
        prompt = ""
        for msg in reversed(list(messages or [])):
            if msg.get("role") == "user":
                prompt = str(msg.get("content") or "")
                break
        question = ""
        if "Question:\n" in prompt:
            question = prompt.rsplit("Question:\n", 1)[-1].strip()
        else:
            question = prompt.strip()
        from app.services.assistant.core.intent_router import is_greeting_or_chitchat

        if is_greeting_or_chitchat(question):
            elapsed = (time.perf_counter() - started) * 1000.0
            return ChatGeneration(
                text=GREETING_TEXT,
                provider=self.name,
                timings_ms={"qwen_first_token_ms": 0.0, "qwen_completed_ms": elapsed},
            )

        hits_meta = filter_relevant_hits(list(kwargs.get("ranked_hits") or []))
        if not hits_meta:
            return ChatGeneration(
                text=REFUSE_TEXT,
                provider=self.name,
                timings_ms={
                    "qwen_first_token_ms": 0.0,
                    "qwen_completed_ms": (time.perf_counter() - started) * 1000.0,
                },
            )

        top = hits_meta[0]
        snippet = str(top.get("snippet") or "").strip().replace("\n", " ")
        title = str(top.get("title") or top.get("document_id") or "your document").strip()
        if len(snippet) > 280:
            snippet = snippet[:280].rstrip() + "…"
        text = f"From **{title}**: {snippet} [1]"
        elapsed = (time.perf_counter() - started) * 1000.0
        return ChatGeneration(
            text=text,
            provider=self.name,
            timings_ms={"qwen_first_token_ms": 0.0, "qwen_completed_ms": elapsed},
        )


def _completion_text(response: Any) -> tuple[str, Optional[str]]:
    """Extract assistant text from a non-stream OpenAI-compatible payload."""
    choices = getattr(response, "choices", None)
    if not choices:
        return "", "empty_choices"
    choice = choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        content = "".join(parts)
    text = (content or "").strip()
    finish = getattr(choice, "finish_reason", None)
    if not text:
        return "", f"empty_content:{finish or 'unknown'}"
    return text, None


class OpenRouterChatProvider:
    """OpenAI-compatible client pointed at OpenRouter (Qwen via QWEN_MODEL)."""

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = OPENROUTER_DEFAULT_BASE_URL,
        timeout_s: float = QWEN_TIMEOUT_S,
    ) -> None:
        # Import here so fake/unit tests do not require the openai package.
        from openai import AsyncOpenAI

        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_s,
        )

    @classmethod
    def from_settings(cls, cfg: Any = None) -> "OpenRouterChatProvider":
        cfg = cfg or settings
        api_key = getattr(cfg, "openrouter_api_key", None)
        model = getattr(cfg, "qwen_model", None)
        base_url = (
            getattr(cfg, "openrouter_base_url", None) or OPENROUTER_DEFAULT_BASE_URL
        )
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")
        if not model:
            raise ValueError("QWEN_MODEL not configured")
        return cls(api_key=str(api_key), model=str(model), base_url=str(base_url))

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration:
        started = time.perf_counter()
        max_tokens = kwargs.get("max_tokens")
        if max_tokens is None:
            max_tokens = getattr(settings, "llm_chat_max_tokens", 1024) or 1024
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = getattr(settings, "llm_chat_temperature", 0.1)
        try:
            temperature = min(0.2, max(0.0, float(temperature)))
        except (TypeError, ValueError):
            temperature = 0.1

        logger.info(
            "[assistant.pipeline] Qwen request started model=%s max_tokens=%s temperature=%s",
            self.model,
            int(max_tokens),
            temperature,
        )
        first_token_ms: Optional[float] = None
        parts: List[str] = []
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=int(max_tokens),
                temperature=temperature,
                stream=True,
            )
            async for event in stream:
                choices = getattr(event, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if not content:
                    continue
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1000.0
                    logger.info(
                        "[assistant.pipeline] first token received ms=%.1f",
                        first_token_ms,
                    )
                parts.append(content)
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000.0
            err = redact_provider_error(exc)
            logger.warning(
                "[assistant.pipeline] Qwen request failed ms=%.1f error=%s",
                elapsed,
                err,
            )
            return ChatGeneration(
                text="",
                provider=self.name,
                error=f"provider_error:{err}",
                timings_ms={"qwen_completed_ms": elapsed},
            )

        text = "".join(parts).strip()
        elapsed = (time.perf_counter() - started) * 1000.0
        if not text:
            logger.warning(
                "[assistant.pipeline] Qwen returned empty payload ms=%.1f", elapsed
            )
            return ChatGeneration(
                text="",
                provider=self.name,
                error="empty_content",
                timings_ms={
                    "qwen_first_token_ms": first_token_ms or elapsed,
                    "qwen_completed_ms": elapsed,
                },
            )
        logger.info(
            "[assistant.pipeline] Qwen response completed ms=%.1f chars=%s",
            elapsed,
            len(text),
        )
        return ChatGeneration(
            text=text,
            provider=self.name,
            timings_ms={
                "qwen_first_token_ms": first_token_ms if first_token_ms is not None else elapsed,
                "qwen_completed_ms": elapsed,
            },
        )


def create_chat_provider(name: Optional[str] = None) -> ChatProvider:
    """Factory: config change selects the implementation (L4)."""
    provider_name = (name or getattr(settings, "llm_chat_provider", None) or "fake")
    provider_name = str(provider_name).strip().lower()
    has_openrouter = bool(
        getattr(settings, "openrouter_api_key", None)
        and getattr(settings, "qwen_model", None)
    )
    # Prefer real Qwen whenever credentials exist, even if env still says fake.
    if provider_name in ("openrouter", "qwen") or (
        provider_name in ("fake", "template", "auto") and has_openrouter
    ):
        if provider_name in ("fake", "template") and has_openrouter:
            logger.info(
                "[assistant.pipeline] OpenRouter/Qwen credentials detected — using real chat model"
            )
        try:
            return OpenRouterChatProvider.from_settings(settings)
        except ValueError as exc:
            logger.warning(
                "[assistant.pipeline] Falling back to fake chat provider: %s", exc
            )
            return FakeChatProvider()
    if provider_name in ("fake", "template", "auto"):
        global _FAKE_PROVIDER_WARNED
        if not _FAKE_PROVIDER_WARNED:
            _FAKE_PROVIDER_WARNED = True
            logger.warning(
                "[assistant.pipeline] LLM_CHAT_PROVIDER=%s with no OPENROUTER_API_KEY/QWEN_MODEL — "
                "using offline fake synthesizer. Set both to call Qwen via OpenRouter.",
                provider_name,
            )
        return FakeChatProvider()
    raise ValueError(f"Unknown chat provider: {provider_name}")


class ChatService:
    """Facade over ChatProvider. Re-reads settings unless a provider is pinned."""

    def __init__(self, provider: Optional[ChatProvider] = None) -> None:
        self._pinned = provider

    @property
    def provider(self) -> ChatProvider:
        return self._pinned or create_chat_provider()

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration:
        return await self.provider.generate(messages, **kwargs)
