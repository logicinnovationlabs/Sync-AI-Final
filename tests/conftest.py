"""Shared configuration and fixtures for Block Z-O verification suite."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FIXTURES = _REPO_ROOT / "fixtures"
_DEFAULT_CONTRACTS = _REPO_ROOT / "contracts"
_DEFAULT_RESULTS = _REPO_ROOT / "test-results"


class TestConfig:
    """Central configuration for all test blocks."""

    FIXTURES_PATH = os.environ.get("FIXTURES_PATH", str(_DEFAULT_FIXTURES))
    CONTRACTS_PATH = os.environ.get("CONTRACTS_PATH", str(_DEFAULT_CONTRACTS))
    FIXTURES_VERSION = os.environ.get("FIXTURES_VERSION", "v2")
    MOCK_BASE_PORT = int(os.environ.get("MOCK_BASE_PORT", "10000"))
    REAL_BASE_PORT = int(os.environ.get("REAL_BASE_PORT", "8000"))
    # USE_REAL_SERVICES=1 (or true) forces integration phase (real deps).
    # TEST_PHASE=integration is the legacy/alternate switch.
    _USE_REAL = os.environ.get("USE_REAL_SERVICES", "").lower() in ("1", "true", "yes")
    PHASE = (
        "integration"
        if _USE_REAL
        else os.environ.get("TEST_PHASE", "provisional")
    )
    RUN_ALL_BLOCKS = os.environ.get("RUN_ALL_BLOCKS", "true").lower() == "true"
    RESULTS_DIR = Path(os.environ.get("TEST_RESULTS_DIR", str(_DEFAULT_RESULTS)))
    USE_INPROCESS_MOCKS = os.environ.get("USE_INPROCESS_MOCKS", "true").lower() == "true"
    JWT_SECRET = os.environ.get("JWT_TEST_SECRET", "test-suite-hs256-secret-32b-min!!")
    USE_REAL_SERVICES = _USE_REAL or PHASE == "integration"

    PORT_OFFSET = {
        "Z": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7,
        "H": 8, "I": 9, "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15,
    }

    BLOCK_DEPENDENCIES = {
        "Z": [], "A": ["Z"], "B": ["A", "D"], "C": ["B"], "D": [],
        "E": ["C"], "F": ["C", "D"], "G": ["A", "C", "D"], "H": ["C"],
        "I": ["C"], "J": ["F", "G", "H", "I"], "K": ["C", "D"],
        "L": ["J", "K"], "M": ["A", "L"],
        "N": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"],
        "O": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"],
    }

    @classmethod
    def get_service_url(cls, block: str, mock: bool = True) -> str:
        host = os.environ.get("TEST_SERVICE_HOST", "127.0.0.1")
        if not mock or os.environ.get("UNIFIED_BACKEND", "true").lower() == "true":
            # For real integration testing, all consolidated endpoints (A-G) are on REAL_BASE_PORT
            if not mock:
                return f"http://{host}:{cls.REAL_BASE_PORT}"
        base_port = cls.MOCK_BASE_PORT if mock else cls.REAL_BASE_PORT
        port = base_port + cls.PORT_OFFSET.get(block.upper(), 0)
        return f"http://{host}:{port}"


    @classmethod
    def using_mocks(cls) -> bool:
        return not cls.USE_REAL_SERVICES and cls.PHASE == "provisional"

    @classmethod
    def using_real(cls) -> bool:
        return cls.USE_REAL_SERVICES or cls.PHASE == "integration"


@dataclass
class TestResult:
    block: str
    criterion: str
    passed: bool
    message: str
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BlockSignoff:
    block: str
    phase: str
    results: List[TestResult]
    passed: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def summary(self) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": (passed / total) if total else 0.0,
            "all_passed": passed == total,
        }


class FixtureLoader:
    """Load and cache Block Z fixtures."""

    def __init__(self, fixtures_path: Path):
        self.fixtures_path = Path(fixtures_path)
        self.cache: Dict[str, Any] = {}

    def load(self, name: str) -> Dict[str, Any]:
        if name in self.cache:
            return self.cache[name]
        file_path = self.fixtures_path / f"{name}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture not found: {file_path}")
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        self.cache[name] = data
        return data

    def get_documents(self) -> List[Dict]:
        return self.load("documents").get("documents", [])

    def get_principals(self) -> List[Dict]:
        return self.load("principals").get("principals", [])

    def get_groups(self) -> List[Dict]:
        return self.load("groups").get("groups", [])

    def get_acl_matrix(self) -> Dict:
        return self.load("acl_matrix")

    def get_relevance_labels(self) -> List[Dict]:
        return self.load("relevance_labels").get("labels", [])

    def get_red_team_cases(self) -> List[Dict]:
        return self.load("acl_redteam_cases").get("cases", [])

    def get_graph_edges(self) -> List[Dict]:
        return self.load("graph_edges").get("edges", [])

    def get_multi_source_identities(self) -> List[Dict]:
        return self.load("multi_source_identities").get("identities", [])

    def get_baselines(self) -> Dict[str, float]:
        return self.load("performance_baselines").get("baselines", {})

    def principal_can_access(self, principal_id: str, document_id: str) -> bool:
        entries = self.get_acl_matrix().get("entries", [])
        return any(
            e.get("principal_id") == principal_id and e.get("document_id") == document_id
            for e in entries
        )

    def docs_for_principal(self, principal_id: str) -> List[Dict]:
        allowed = {
            e["document_id"]
            for e in self.get_acl_matrix().get("entries", [])
            if e.get("principal_id") == principal_id
        }
        return [d for d in self.get_documents() if d["id"] in allowed]


class TestClient:
    """HTTP client used by block tests."""

    __test__ = False  # prevent pytest collection

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        start = time.time()
        response = self.session.request(method, url, **kwargs)
        response._duration_ms = (time.time() - start) * 1000  # type: ignore[attr-defined]
        return response

    def get(self, path: str, **kwargs) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self._request("DELETE", path, **kwargs)


class PerformanceTracker:
    def __init__(self) -> None:
        self.measurements: Dict[str, List[float]] = {}
        self._start_time: Optional[float] = None
        self._current_label: Optional[str] = None

    def start(self, label: str) -> None:
        self._current_label = label
        self._start_time = time.time()

    def stop(self) -> float:
        if self._start_time is None:
            raise ValueError("No measurement started")
        duration_ms = (time.time() - self._start_time) * 1000
        label = self._current_label or "unnamed"
        self.measurements.setdefault(label, []).append(duration_ms)
        self._start_time = None
        self._current_label = None
        return duration_ms

    def record(self, label: str, duration_ms: float) -> None:
        self.measurements.setdefault(label, []).append(duration_ms)

    def get_percentile(self, label: str, percentile: float) -> float:
        values = sorted(self.measurements.get(label, []))
        if not values:
            return 0.0
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]

    def get_p95(self, label: str) -> float:
        return self.get_percentile(label, 95)

    def get_p99(self, label: str) -> float:
        return self.get_percentile(label, 99)

    def get_avg(self, label: str) -> float:
        values = self.measurements.get(label, [])
        return (sum(values) / len(values)) if values else 0.0

    def reset(self) -> None:
        self.measurements.clear()


perf_tracker = PerformanceTracker()


def load_fixture(name: str) -> Dict[str, Any]:
    return FixtureLoader(Path(TestConfig.FIXTURES_PATH)).load(name)


def generate_signoff_report(block_results: Dict[str, List[TestResult]]) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "phase": TestConfig.PHASE,
        "fixtures_version": TestConfig.FIXTURES_VERSION,
        "blocks": {},
    }
    for block, results in block_results.items():
        report["blocks"][block] = {
            "results": [
                {
                    "criterion": r.criterion,
                    "passed": r.passed,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ],
            "passed": all(r.passed for r in results),
        }
    report["overall_passed"] = (
        all(b["passed"] for b in report["blocks"].values()) if report["blocks"] else False
    )
    return report


def provisional_only(test_func):
    test_func._provisional_only = True
    return test_func


def integration_only(test_func):
    test_func._integration_only = True
    return test_func


def both_phases(test_func):
    test_func._both_phases = True
    return test_func


def _block_from_request(request) -> str:
    name = getattr(request, "node", None)
    block = "A"
    if name and hasattr(name, "cls") and name.cls and name.cls.__name__.startswith("TestBlock"):
        block = name.cls.__name__.replace("TestBlock", "")
    return block


@pytest.fixture(scope="session")
def fixture_loader() -> FixtureLoader:
    return FixtureLoader(Path(TestConfig.FIXTURES_PATH))


@pytest.fixture(scope="session")
def contracts_path() -> Path:
    return Path(TestConfig.CONTRACTS_PATH)


@pytest.fixture(scope="session")
def inprocess_mock_server():
    """Start a single in-process mock covering all block ports via one shared server."""
    if not TestConfig.USE_INPROCESS_MOCKS or not TestConfig.using_mocks():
        yield None
        return
    from tests.mocks.contract_mock_server import start_inprocess_server

    # Auth block A uses MOCK_BASE_PORT + 1; mock serves all routes on that port.
    # Also bind a unified alias used by tests that hit MOCK_BASE_PORT + offset via rewrite.
    port = TestConfig.MOCK_BASE_PORT + 1
    server = start_inprocess_server(port=port)
    yield server
    server.shutdown()


@pytest.fixture(scope="function")
def use_mocks() -> bool:
    return TestConfig.using_mocks()


@pytest.fixture(scope="function")
def mock_url(request, inprocess_mock_server) -> str:
    # All provisional HTTP traffic goes to the in-process mock (A port).
    if TestConfig.USE_INPROCESS_MOCKS and inprocess_mock_server is not None:
        return f"http://127.0.0.1:{TestConfig.MOCK_BASE_PORT + 1}"
    return TestConfig.get_service_url(_block_from_request(request), mock=True)


@pytest.fixture(scope="function")
def real_url(request) -> str:
    return TestConfig.get_service_url(_block_from_request(request), mock=False)


@pytest.fixture(scope="function")
def block_client(request, use_mocks, inprocess_mock_server):
    if use_mocks and TestConfig.USE_INPROCESS_MOCKS and inprocess_mock_server is not None:
        base = f"http://127.0.0.1:{TestConfig.MOCK_BASE_PORT + 1}"
    else:
        base = TestConfig.get_service_url(_block_from_request(request), mock=use_mocks)
    return TestClient(base)


__all__ = [
    "TestConfig",
    "TestResult",
    "BlockSignoff",
    "FixtureLoader",
    "TestClient",
    "PerformanceTracker",
    "perf_tracker",
    "load_fixture",
    "generate_signoff_report",
    "provisional_only",
    "integration_only",
    "both_phases",
    "hashlib",
    "uuid",
    "timedelta",
    "datetime",
]
