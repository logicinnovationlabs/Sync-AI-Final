"""Ask the live Block L assistant from the terminal (same pipeline as the UI).

Usage (from backend/, or inside snyq_app):
  python scripts/ask_assistant.py "what is my mail"
  python scripts/ask_assistant.py "which mail we are using" --debug

Does not print API keys. Truncates retrieved snippets in debug output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

DEFAULT_BASE = os.getenv("ASK_API_BASE", "http://127.0.0.1:8000")
DEFAULT_EMAIL = os.getenv("ASK_EMAIL", "admin@synq.dev")
DEFAULT_PASSWORD = os.getenv("ASK_PASSWORD", "AlphaAdmin123!")
DEFAULT_TENANT = os.getenv("ASK_TENANT", "alpha")


def _login(client: httpx.Client, base: str) -> str:
    resp = client.post(
        urljoin(base.rstrip("/") + "/", "auth/login"),
        json={
            "email": DEFAULT_EMAIL,
            "password": DEFAULT_PASSWORD,
            "tenant_subdomain": DEFAULT_TENANT,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise SystemExit("login succeeded but no access_token")
    return str(token)


def _parse_ndjson(text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query the live grounded assistant")
    parser.add_argument("prompt", help="User question")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--session-id", default="")
    args = parser.parse_args(argv)

    session_id = args.session_id or f"cli-{uuid.uuid4().hex[:10]}"
    started = time.perf_counter()
    with httpx.Client(timeout=120.0) as client:
        token = _login(client, args.base)
        resp = client.post(
            urljoin(args.base.rstrip("/") + "/", "assistant/orchestrator/chat"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": args.prompt,
                "session_id": session_id,
                "debug": True,
            },
        )
        if resp.status_code != 200:
            print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
            return 1
        events = _parse_ndjson(resp.text)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    meta = next((e for e in events if e.get("type") == "meta"), {})
    final = next((e for e in events if e.get("type") == "final"), {})
    if not final:
        print("No final event from assistant.", file=sys.stderr)
        return 1

    provider = final.get("chat_provider_name") or meta.get("chat_provider_name") or "?"
    answer = final.get("response_text") or ""
    print(f"provider: {provider}")
    print(f"latency_ms: {final.get('timings_ms', {}).get('total_ms') or meta.get('latency_ms') or elapsed_ms:.1f}")
    print(f"generation_error: {final.get('generation_error') or '(none)'}")
    print("--- answer ---")
    print(answer)
    print("--- citations ---")
    for c in final.get("citations") or []:
        doc = c.get("document_id") or "?"
        src = c.get("source_id") or ""
        quote = str(c.get("quote") or "").replace("\n", " ")[:160]
        print(f"  {src} {doc}: {quote}")
    chunks = final.get("debug_retrieval") or []
    if args.debug or chunks:
        print("--- retrieved chunks ---")
        for ch in chunks:
            snippet = str(ch.get("snippet") or "").replace("\n", " ")[:160]
            print(
                f"  {ch.get('source_id')} id={ch.get('document_id')} "
                f"score={ch.get('score')} {snippet}"
            )
    if provider == "fake":
        print(
            "\nWARNING: chat_provider=fake — Qwen was not called. "
            "Set LLM_CHAT_PROVIDER=openrouter and recreate the app container.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
