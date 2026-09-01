"""Swappable chat LLM providers for Block L.

Mirrors EmbeddingProvider / GeminiEmbeddingProvider / FakeEmbeddingProvider:
a small Protocol, env-selected implementations, constructed from Settings.

``LLM_CHAT_PROVIDER`` is independent of ``LLM_PROVIDER`` (embeddings).
Values: ``fake`` (default for offline tests) | ``openrouter`` (OpenAI-compatible
client at OpenRouter, model from ``QWEN_MODEL``).
"""

from __future__ import annotations

import html
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence

from app.core.config import settings
from app.services.rag_debug_trace import get_tracer as _get_rag_tracer

logger = logging.getLogger(__name__)

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
QWEN_TIMEOUT_S = 90.0
# Increased limits for detailed document Q&A
MAX_SOURCE_CHARS = 4000  # Increased from 1500 for detailed content
MAX_CONTEXT_CHARS = 32000  # Increased from 12000 for longer documents  
MAX_HISTORY_TURNS = 6
TOP_K_SOURCES = 10  # Increased from 5 to retrieve more relevant chunks
# Cosine / ANN similarity (Qdrant). Keep a low floor — empty context is worse.
MIN_COSINE_SCORE = 0.02
# Federator RRF uses k=60, so rank-1 is ~1/61 ≈ 0.016 — not cosine.
MIN_RRF_SCORE = 0.001

REFUSE_TEXT = (
    "I don't have that information in the available documents."
)

GREETING_TEXT = (
    "Hi — I can help with your indexed Drive, Gmail, and docs. "
    "Ask a specific question and I’ll answer from your sources."
)

GROUNDED_SYSTEM_PROMPT = """You are SynQ AI, an intelligent business knowledge assistant.

CRITICAL RULES (Phase 1 quality bar):
- Answer ONLY using the document context provided below. Do NOT use your own knowledge.
- If the answer is in the documents, extract and present it clearly with specific details (names, numbers, dates, quotes).
- Cite sources inline as [1], [2], etc. matching the source numbers below (at most 2–3 citations).
- If the documents do not contain the answer, say exactly: I don't have that information in the available documents.
- For questions about which apps or accounts are connected to SynQ AI, use the CONNECTED INTEGRATIONS section (not the document list).
- For greetings (hello, hi, hey), respond warmly and mention you can help with their uploaded documents.
- Be direct, specific, and conversational. Do NOT dump raw document text.
- When the user asks for a brief / summary / story / lessons, use short bold section labels and bullets — still only from the sources.
- Source headers (title, from=, subject=) are evidence. For newsletters, From identifies the author; "3MM" means "3 Minute Monday".
- Answer in the same language as the question.
- Lead with the answer. No preamble like "Here is what I found" or "Based on the sources"."""

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
    return (
        "don't have enough information in the provided context" in normalized
        or "don't have that information in the available documents" in normalized
        or "dont have that information in the available documents" in normalized
    )


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
    structured = (
        nested.get("structured_metadata")
        if isinstance(nested.get("structured_metadata"), dict)
        else {}
    )
    if not structured and isinstance(extra.get("structured_metadata"), dict):
        structured = extra.get("structured_metadata") or {}

    def first(*keys: str) -> Any:
        for key in keys:
            for src in (hit, meta, nested, extra, structured):
                if not isinstance(src, dict):
                    continue
                value = src.get(key)
                if value not in (None, "", []):
                    return value
        return None

    from_raw = first("from_email", "from", "sender")
    return {
        "document_id": str(first("document_id", "id") or ""),
        "chunk_id": first("chunk_id", "chunkId"),
        "page": first("page", "page_number", "pageNumber"),
        "title": str(first("title", "subject") or ""),
        "source": first("source", "source_type", "repository"),
        "from_email": str(from_raw or ""),
        "subject": str(first("subject") or ""),
    }


def plain_source_text(text: str, *, limit: int = 0) -> str:
    """Strip HTML/CSS so Gmail bodies are readable evidence, not stylesheet junk."""
    raw = str(text or "")
    cleaned = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "…"
    return cleaned


def source_text_is_usable(text: str, *, min_chars: int = 40) -> bool:
    return len(plain_source_text(text)) >= min_chars


def format_source_block(hit: Dict[str, Any], index: int) -> str:
    """Phase 1 style: [Source N: title] then body text (with from= when known)."""
    meta = _hit_meta(hit)
    snippet = plain_source_text(str(hit.get("snippet") or hit.get("body") or "").strip())
    if len(snippet) > MAX_SOURCE_CHARS:
        snippet = snippet[:MAX_SOURCE_CHARS].rstrip() + "…"
    title = meta["title"] or meta["document_id"] or f"Document {index}"
    header = f"[Source {index}: {title}]"
    extras: List[str] = []
    if meta["from_email"]:
        extras.append(f"from={meta['from_email']}")
    if meta["subject"] and meta["subject"] != meta["title"]:
        extras.append(f"subject={meta['subject']}")
    if meta["source"]:
        extras.append(f"source={meta['source']}")
    if extras:
        header = header + " (" + "; ".join(extras) + ")"
    return header + "\n" + (snippet or "(empty snippet)")


def debug_source_chunks(ranked_hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact retrieval debug payload (ACL-filtered hits only; no secrets)."""
    chunks: List[Dict[str, Any]] = []
    for i, hit in enumerate(list(ranked_hits)[:TOP_K_SOURCES], start=1):
        meta = _hit_meta(hit)
        snippet = plain_source_text(str(hit.get("snippet") or hit.get("body") or "").strip())
        chunks.append(
            {
                "source_id": f"[{i}]",
                "document_id": meta["document_id"] or None,
                "chunk_id": meta["chunk_id"],
                "page": meta["page"],
                "title": meta["title"] or None,
                "from_email": meta["from_email"] or None,
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
    """Keep top federator hits for grounding (federator already ranked)."""
    kept: List[Dict[str, Any]] = []
    for hit in ranked_hits:
        sources = hit.get("sources") or []
        if "document_reader" in sources or "document_reader_fallback" in sources:
            kept.append(dict(hit))
            if len(kept) >= limit:
                break
            continue

        snippet = str(
            hit.get("snippet") or hit.get("body") or hit.get("title") or ""
        ).strip()
        if not snippet and not hit.get("document_id"):
            continue

        score_f = _hit_numeric_score(hit)
        if score_f is not None:
            floor = MIN_RRF_SCORE if _is_rrf_score(score_f) else min_score
            # Always allow the first few federator hits through even if weak.
            if score_f < floor and len(kept) >= 2:
                continue

        kept.append(dict(hit))
        if len(kept) >= limit:
            break

    if not kept and ranked_hits:
        for hit in list(ranked_hits)[:limit]:
            if hit.get("document_id") or str(hit.get("snippet") or "").strip():
                kept.append(dict(hit))
    return kept[:limit]


async def enrich_hits_with_full_bodies(
    hits: Sequence[Dict[str, Any]],
    tenant_id: str,
    *,
    min_chars: int = 600,
    max_chars: int = 6000,
    limit: int = TOP_K_SOURCES,
) -> List[Dict[str, Any]]:
    """Expand thin vector chunks with full stored document bodies (Phase 1 parity)."""
    if not hits or not (tenant_id or "").strip():
        return list(hits)
    try:
        from app.services.document_reader.store import get_shared_document_store

        store = get_shared_document_store()
    except Exception:  # noqa: BLE001
        return list(hits)

    enriched: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for hit in list(hits)[:limit]:
        row = dict(hit)
        doc_id = str(row.get("document_id") or "")
        snippet = plain_source_text(str(row.get("snippet") or row.get("body") or ""))
        if (
            doc_id
            and doc_id not in seen
            and len(snippet) < min_chars
            and hasattr(store, "get_metadata")
        ):
            try:
                meta = await store.get_metadata(tenant_id, doc_id)
                object_key = (meta or {}).get("object_key") if meta else None
                body_text = ""
                if object_key and hasattr(store, "get_body"):
                    raw = await store.get_body(str(object_key))
                    body_text = (
                        raw.decode("utf-8", errors="ignore")
                        if isinstance(raw, (bytes, bytearray))
                        else str(raw or "")
                    )
                body_text = plain_source_text(body_text)
                if len(body_text) > len(snippet):
                    row["snippet"] = body_text[:max_chars]
                    if meta and meta.get("title") and not row.get("title"):
                        row["title"] = meta.get("title")
                if hasattr(store, "get_structured_metadata"):
                    sm = await store.get_structured_metadata(tenant_id, doc_id)
                    if isinstance(sm, dict) and sm:
                        merged = dict(row.get("metadata") or {})
                        merged.update(
                            {k: v for k, v in sm.items() if v not in (None, "", [])}
                        )
                        row["metadata"] = merged
                        if sm.get("from_email"):
                            row["from_email"] = sm["from_email"]
                seen.add(doc_id)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "full-body enrich skipped doc_id=%s", doc_id, exc_info=True
                )
        enriched.append(row)
    return enriched


def assemble_chat_messages(
    user_prompt: str,
    ranked_hits: List[Dict[str, Any]],
    *,
    conversation_history: Optional[Sequence[Dict[str, Any]]] = None,
    account_email: Optional[str] = None,
    connector_summary: Optional[str] = None,
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
    integrations_text = (connector_summary or "").strip() or "(no connector summary)"
    user = (
        "CONNECTED INTEGRATIONS:\n"
        f"{integrations_text}\n\n"
        "DOCUMENTS:\n"
        f"{sources_text}\n\n"
        f"{account_line}"
        "Prior conversation (not evidence; sources above win if they conflict):\n"
        f"{history_text}\n\n"
        f"QUESTION: {user_prompt}\n\n"
        "Answer based on CONNECTED INTEGRATIONS for connection/account questions, "
        "and on DOCUMENTS for content questions. "
        "If a From header or title abbreviation matches the person/topic asked about, "
        "use that source — do not refuse just because the display name is missing from the body."
    )
    messages = [
        {"role": "system", "content": GROUNDED_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    prompt_text = f"{GROUNDED_SYSTEM_PROMPT}\n\n{user}"

    # --- Rule #2, Stage 8: final assembled context ---
    tracer = _get_rag_tracer()
    # Approximate token count: ~4 chars per token for English
    approx_tokens = len(prompt_text) // 4
    tracer.log_final_context(prompt_text, approx_tokens)

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
        if "QUESTION:" in prompt:
            question = prompt.rsplit("QUESTION:", 1)[-1].strip()
        elif "Question:\n" in prompt:
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
        meta = _hit_meta(top)
        snippet = plain_source_text(str(top.get("snippet") or "")).replace("\n", " ")
        title = str(meta.get("title") or top.get("title") or top.get("document_id") or "your document").strip()
        sender = str(meta.get("from_email") or "").strip()
        if len(snippet) > 280:
            snippet = snippet[:280].rstrip() + "…"
        if sender:
            # Prefer display name before <email> when present.
            display = sender
            if "<" in sender:
                display = sender.split("<", 1)[0].strip().strip('"') or sender
            text = f"From **{display}** ({title}): {snippet} [1]"
        else:
            text = f"From **{title}**: {snippet} [1]"
        elapsed = (time.perf_counter() - started) * 1000.0
        return ChatGeneration(
            text=text,
            provider=self.name,
            timings_ms={"qwen_first_token_ms": 0.0, "qwen_completed_ms": elapsed},
        )


def _text_from_value(value: Any) -> str:
    """Coerce OpenAI/OpenRouter content (string, list, or part objects) to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(
                    str(
                        getattr(item, "text", None)
                        or getattr(item, "content", None)
                        or ""
                    )
                )
        return "".join(parts).strip()
    return str(value).strip()


def _message_fields(message: Any) -> Dict[str, Any]:
    if message is None:
        return {}
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        try:
            data = dump(exclude_none=True)
            if isinstance(data, dict):
                extra = data.get("model_extra") if isinstance(data.get("model_extra"), dict) else {}
                merged = dict(data)
                if extra:
                    merged.update(extra)
                return merged
        except Exception:  # noqa: BLE001
            pass
    fields: Dict[str, Any] = {}
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        fields.update(extra)
    for key in ("content", "reasoning", "reasoning_content", "reasoning_details", "refusal"):
        val = getattr(message, key, None)
        if val is not None:
            fields[key] = val
    return fields


def _as_mapping(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            data = dump()
            return data if isinstance(data, dict) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _choice_mapping(choice: Any) -> Dict[str, Any]:
    data = _as_mapping(choice)
    if data is not None:
        return data
    message = getattr(choice, "message", None) or getattr(choice, "delta", None)
    fields = _message_fields(message)
    return {
        "finish_reason": getattr(choice, "finish_reason", None)
        or getattr(choice, "native_finish_reason", None),
        "message": fields,
        "delta": fields,
    }


def _completion_text(response: Any) -> tuple[str, Optional[str]]:
    """Extract assistant text from a non-stream OpenAI-compatible payload."""
    data = _as_mapping(response)
    if data is None:
        error = getattr(response, "error", None)
        choices = getattr(response, "choices", None) or []
        data = {"error": error, "choices": choices}
    error = data.get("error")
    if error:
        return "", f"provider_error:{error}"
    choices = data.get("choices")
    if not choices:
        return "", "empty_choices"
    choice = _choice_mapping(choices[0])
    message = choice.get("message") or choice.get("delta") or {}
    if not isinstance(message, dict):
        message = _message_fields(message)
    text = _text_from_value(message.get("content"))
    if not text:
        text = _text_from_value(message.get("reasoning") or message.get("reasoning_content"))
    if not text:
        details = message.get("reasoning_details")
        if isinstance(details, list):
            text = _text_from_value(
                [item.get("text") if isinstance(item, dict) else item for item in details]
            )
    finish = choice.get("finish_reason") or choice.get("native_finish_reason")
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
        *,
        http_referer: Optional[str] = None,
    ) -> None:
        # Import here so fake/unit tests do not require the openai package.
        import httpx
        from openai import AsyncOpenAI

        self.model = model
        referer = (http_referer or getattr(settings, "frontend_url", None) or "").strip()
        if not referer:
            referer = "https://synq.app"
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)),
            default_headers={
                "HTTP-Referer": referer,
                "X-Title": "SynQ",
            },
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
        return cls(
            api_key=str(api_key),
            model=str(model),
            base_url=str(base_url),
            http_referer=str(getattr(cfg, "frontend_url", "") or ""),
        )

    @staticmethod
    def _may_reason(model: str) -> bool:
        lowered = (model or "").lower()
        return any(token in lowered for token in ("qwen3", "qwq", "thinking", "reason"))

    async def _create_completion(self, **kwargs: Any) -> Any:
        """Prefer raw JSON so OpenRouter `reasoning` fields are not dropped."""
        raw_api = getattr(self._client.chat.completions, "with_raw_response", None)
        if raw_api is not None:
            raw = await raw_api.create(**kwargs)
            http_resp = getattr(raw, "http_response", None)
            if http_resp is not None:
                try:
                    payload = http_resp.json()
                    if isinstance(payload, dict):
                        return payload
                except Exception:  # noqa: BLE001
                    pass
            parse = getattr(raw, "parse", None)
            if callable(parse):
                return parse()
        return await self._client.chat.completions.create(**kwargs)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration:
        started = time.perf_counter()
        max_tokens = kwargs.get("max_tokens")
        if max_tokens is None:
            max_tokens = getattr(settings, "llm_chat_max_tokens", 1500) or 1500
        # Reasoning models spend budget on hidden thinking; keep a healthy floor
        # so finish_reason=length does not yield empty content.
        token_floor = 2048 if self._may_reason(self.model) else 1024
        token_budget = max(int(max_tokens), token_floor)
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = getattr(settings, "llm_chat_temperature", 0.3)
        try:
            # Phase 1 used 0.3 — allow up to 0.4 for natural prose.
            temperature = min(0.4, max(0.0, float(temperature)))
        except (TypeError, ValueError):
            temperature = 0.3

        logger.info(
            "[assistant.pipeline] Qwen request started model=%s max_tokens=%s temperature=%s stream=false",
            self.model,
            token_budget,
            temperature,
        )

        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": token_budget,
            "temperature": temperature,
            "stream": False,
        }
        # Only send reasoning controls to models that support them (Qwen3/thinking).
        # Qwen 2.5 instruct can fail or return empty when this extra_body is present.
        if self._may_reason(self.model):
            create_kwargs["extra_body"] = {
                "reasoning": {"effort": "none", "exclude": True},
            }

        try:
            completion = await self._create_completion(**create_kwargs)
        except Exception as first_exc:  # noqa: BLE001
            # Some models reject the reasoning extra_body; retry once without it.
            logger.warning(
                "[assistant.pipeline] Qwen first request failed; retrying without reasoning extras error=%s",
                redact_provider_error(first_exc),
            )
            try:
                create_kwargs.pop("extra_body", None)
                completion = await self._create_completion(**create_kwargs)
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

        text, err = _completion_text(completion)
        data = _as_mapping(completion) or {}
        finish = None
        choices = data.get("choices") or getattr(completion, "choices", None) or []
        if choices:
            c0 = choices[0]
            if isinstance(c0, dict):
                finish = c0.get("finish_reason") or c0.get("native_finish_reason")
            else:
                finish = getattr(c0, "finish_reason", None)
        usage = data.get("usage") or getattr(completion, "usage", None)
        usage_bits = ""
        if isinstance(usage, dict):
            usage_bits = (
                f" prompt={usage.get('prompt_tokens')}"
                f" completion={usage.get('completion_tokens')}"
            )
        elif usage is not None:
            usage_bits = (
                f" prompt={getattr(usage, 'prompt_tokens', None)}"
                f" completion={getattr(usage, 'completion_tokens', None)}"
            )

        if not text:
            logger.warning(
                "[assistant.pipeline] Qwen empty payload; retrying once with more tokens finish=%s error=%s",
                finish,
                err,
            )
            try:
                retry_kwargs = dict(create_kwargs)
                retry_kwargs["max_tokens"] = max(token_budget, 2048)
                # Do not re-introduce reasoning extras on empty-content retry.
                retry_kwargs.pop("extra_body", None)
                completion = await self._create_completion(**retry_kwargs)
                text, err = _completion_text(completion)
                data = _as_mapping(completion) or {}
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    finish = choices[0].get("finish_reason") or finish
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[assistant.pipeline] Qwen retry failed error=%s",
                    redact_provider_error(exc),
                )

        elapsed = (time.perf_counter() - started) * 1000.0
        if not text:
            logger.warning(
                "[assistant.pipeline] Qwen returned empty payload ms=%.1f error=%s finish=%s%s",
                elapsed,
                err or "empty_content",
                finish,
                usage_bits,
            )
            return ChatGeneration(
                text="",
                provider=self.name,
                error=err or "empty_content",
                timings_ms={
                    "qwen_first_token_ms": elapsed,
                    "qwen_completed_ms": elapsed,
                },
            )
        logger.info(
            "[assistant.pipeline] Qwen response completed ms=%.1f chars=%s finish=%s%s",
            elapsed,
            len(text),
            finish,
            usage_bits,
        )

        # --- Rule #2, Stage 9: raw Qwen response ---
        tracer = _get_rag_tracer()
        tracer.log_raw_response(text)

        return ChatGeneration(
            text=text,
            provider=self.name,
            timings_ms={
                "qwen_first_token_ms": elapsed,
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
