"""Block Z fixture loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tests.conftest import FixtureLoader, TestConfig


def default_loader() -> FixtureLoader:
    return FixtureLoader(Path(TestConfig.FIXTURES_PATH))


def load(name: str) -> Dict[str, Any]:
    return default_loader().load(name)


def documents() -> List[Dict]:
    return default_loader().get_documents()


def principals() -> List[Dict]:
    return default_loader().get_principals()
