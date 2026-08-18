"""Swappable chat LLM providers for Block L.

Mirrors EmbeddingProvider / GeminiEmbeddingProvider / FakeEmbeddingProvider:
a small Protocol, env-selected implementations, constructed from Settings.

``LLM_CHAT_PROVIDER`` is independent of ``LLM_PROVIDER`` (embeddings).
Values: ``fake`` (default, no network) | ``openrouter`` (OpenAI-compatible
client at OpenRouter, model from ``QWEN_MODEL``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from app.core.config import settings

OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Inspectable log of prompts actually sent to a chat provider. Tests (L1)
# assert restricted content never appears here. Entries never include API keys.
PROMPT_LOG: List[Dict[str, Any]] = []


def clear_prompt_log() -> None:
    PROMPT_LOG.clear()


def record_prompt(entry: Dict[str, Any]) -> None:
    PROMPT_LOG.append(entry)
    if len(PROMPT_LOG) > 500:
        del PROMPT_LOG[:250]


@dataclass
class ChatGeneration:
    """Minimal generate() result the graph node consumes."""

    text: str
    provider: str
    citations_meta: List[Dict[str, Any]] = field(default_factory=list)


class ChatProvider(Protocol):
    """LlmProvider-shaped protocol. Swap implementations via config only."""

    name: str

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration: ...


def assemble_chat_messages(
    user_prompt: str,
    ranked_hits: List[Dict[str, Any]],
) -> tuple[List[Dict[str, str]], str]:
    """Build chat messages from the user prompt + already-ACL-filtered hits.

    Retrieval (federator / document reader) is assumed to have filtered by
    the requesting principal before this runs. This function does not fetch
    extra corpus content.
    """
    source_blocks: List[str] = []
    for i, hit in enumerate(ranked_hits[:8], start=1):
        doc_id = str(hit.get("document_id") or "")
        title = str(hit.get("title") or doc_id)
        snippet = str(hit.get("snippet") or "").strip()
        source_blocks.append(
            f"[{i}] document_id={doc_id} title={title}\n{snippet}"
        )
    sources_text = (
        "\n\n".join(source_blocks) if source_blocks else "(no authorized sources)"
    )
    system = (
        "You are a tenant-scoped assistant. Answer only from the authorized "
        "retrieved sources. If they are insufficient, say so. Refer to sources "
        "by document_id. Do not invent documents or quote material that is not "
        "in the sources."
    )
    user = f"Question:\n{user_prompt}\n\nAuthorized retrieved sources:\n{sources_text}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    prompt_text = f"{system}\n\n{user}"
    return messages, prompt_text


class FakeChatProvider:
    """Deterministic synthesizer — keeps tests offline. Same shape as OpenRouter."""

    name = "fake"

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ChatGeneration:
        user = ""
        for msg in messages:
            if msg.get("role") == "user":
                user = msg.get("content") or ""
        hits_meta = kwargs.get("ranked_hits") or []
        if not hits_meta:
            if "(no authorized sources)" in user or not user:
                text = "I could not find accessible documents for that request."
            else:
                text = (
                    "I can search your tenant corpus, open a specific document, "
                    "or answer with citations from retrieved sources. "
                    "Ask me to find something or open a document."
                )
            return ChatGeneration(text=text, provider=self.name)

        lines = []
        for i, hit in enumerate(hits_meta[:5], start=1):
            snippet = str(hit.get("snippet") or "").strip().replace("\n", " ")
            title = hit.get("title") or hit.get("document_id")
            lines.append(f"{i}. {title}: {snippet[:240]}")
        prefix = "Here is what I found"
        if kwargs.get("used_document_reader"):
            prefix += " (including a deep document read)"
        text = prefix + ":\n" + "\n".join(lines)
        return ChatGeneration(text=text, provider=self.name)


class OpenRouterChatProvider:
    """OpenAI-compatible client pointed at OpenRouter (Qwen via QWEN_MODEL)."""

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = OPENROUTER_DEFAULT_BASE_URL,
    ) -> None:
        # Import here so fake/unit tests do not require the openai package.
        from openai import AsyncOpenAI

        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        max_tokens = int(kwargs.get("max_tokens") or 256)
        temperature = float(kwargs.get("temperature") or 0.2)
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0].message if response.choices else None
        text = (choice.content if choice else None) or ""
        return ChatGeneration(text=text.strip(), provider=self.name)


def create_chat_provider(name: Optional[str] = None) -> ChatProvider:
    """Factory: config change selects the implementation (L4)."""
    provider_name = (name or getattr(settings, "llm_chat_provider", None) or "fake")
    provider_name = str(provider_name).strip().lower()
    if provider_name in ("fake", "template"):
        return FakeChatProvider()
    if provider_name in ("openrouter", "qwen"):
        return OpenRouterChatProvider.from_settings(settings)
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
