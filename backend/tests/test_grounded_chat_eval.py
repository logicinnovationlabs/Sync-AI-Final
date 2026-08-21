"""Offline grounded-chat evaluation through the same orchestrator pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from eval_grounded_chat import load_fixture, run_eval  # noqa: E402
from app.services.assistant.infrastructure.chat_provider import is_refuse_answer

pytestmark = pytest.mark.block_l


@pytest.mark.asyncio
async def test_grounded_eval_suite_offline():
    report = await run_eval(live=False, include_live_only=False)
    assert report["total"] >= 4
    assert report["provider"] == "fake"
    failed = [c for c in report["cases"] if not c["passed"]]
    assert not failed, failed
    refuse = next(c for c in report["cases"] if c["id"] == "refuse-missing-from-context")
    assert refuse["refused"]
    assert is_refuse_answer(refuse["answer"])
    assert report["unsupported_answer_rate"] == 0.0


def test_eval_fixture_defines_accuracy_and_refuse_case():
    data = load_fixture()
    assert "evidence-based" in (data.get("accuracy_definition") or "")
    ids = {c["id"] for c in data["cases"]}
    assert "refuse-missing-from-context" in ids
    refuse = next(c for c in data["cases"] if c["id"] == "refuse-missing-from-context")
    assert refuse["expect_refuse"] is True
