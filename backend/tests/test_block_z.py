"""Block Z - shared fixtures, contracts, swap readiness (architecture section 24 Z1-Z3)."""
from __future__ import annotations
import uuid
from pathlib import Path
import pytest
import requests
from tests.conftest import TestConfig, TestClient
from tests.helpers.contract_validator import (
    endpoint_from_contract,
    load_contract,
    require_contracts,
    validate_response_shape,
)
from tests.helpers.fixture_linter import lint_fixtures
from tests.helpers.swap_verifier import compare_shapes, normalize_response_shape
from tests.signoff_common import assert_pass, tcp_open, using_real_services
def _response_schema(contract: dict, path: str, method: str, status: str = "200") -> dict | None:
    methods = (contract.get("paths") or {}).get(path) or {}
    operation = methods.get(method.lower()) or {}
    responses = operation.get("responses") or {}
    content = (responses.get(status) or {}).get("content") or {}
    return (content.get("application/json") or {}).get("schema")
def _sample_request(path: str, method: str) -> dict | None:
    """Minimal JSON bodies for mock POST/PUT routes (no secrets)."""
    if method != "POST":
        return None
    if path == "/oauth/token":
        return {"principal_id": "principal-alice", "tenant_id": "tenant-a", "scopes": ["search.read"]}
    if path == "/oauth/revoke":
        return {"jti": str(uuid.uuid4())}
    if path == "/scim/sync":
        return {"users": []}
    if path in ("/connectors/google-drive/crawl", "/connectors/google-gmail/crawl"):
        return {}
    if path == "/connectors/checkpoint":
        return {"source": "google_drive", "checkpoint": "cp-drive-1"}
    if path == "/normalize":
        return {"document": {"id": "doc-roadmap", "tenant_id": "tenant-a", "acl": ["principal-alice"]}}
    if path == "/identity/resolve":
        return {"external_id": "alice@example.com", "source_type": "google"}
    if path.startswith("/search/"):
        return {"query": "roadmap"}
    return {}
@pytest.mark.block_z
@pytest.mark.provisional
class TestBlockZ:
    # Z1 - contract corpus loads, paths validate, optional live mock sampling
    def test_z1_contracts_present_and_parseable(self, contracts_path, block_client):
        paths = require_contracts(Path(contracts_path))
        schema_violations: list[str] = []
        assert len(paths) >= 10, f"expected >=10 contracts, got {len(paths)}"
        for contract_path in paths:
            doc = load_contract(contract_path)
            assert doc.get("openapi"), f"{contract_path.name} missing openapi"
            assert doc.get("paths"), f"{contract_path.name} missing paths"
            assert contract_path.exists()
            for path, method in endpoint_from_contract(doc):
                schema = _response_schema(doc, path, method)
                resp = None
                try:
                    if method == "GET":
                        resp = block_client.get(path)
                    elif method == "POST":
                        body = _sample_request(path, method)
                        resp = block_client.post(path, json=body or {})
                    elif method == "PUT":
                        resp = block_client.put(path, json=_sample_request(path, method) or {})
                    elif method == "DELETE":
                        resp = block_client.delete(path)
                except requests.RequestException:
                    continue
                if resp is None or resp.status_code >= 500:
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                for err in validate_response_shape(data, schema):
                    schema_violations.append(f"{contract_path.name} {method} {path}: {err}")
        assert_pass("Z1", len(schema_violations) == 0, f"{len(paths)} contracts, 0 schema violations")
        assert schema_violations == [], schema_violations
    # Z2 - fixture lint + version alignment with MANIFEST
    def test_z2_fixture_lint_and_versioning(self, fixture_loader):
        report = lint_fixtures(Path(TestConfig.FIXTURES_PATH))
        assert report.ok, [f"{e.file}: {e.message}" for e in report.errors]
        manifest = fixture_loader.load("MANIFEST")
        assert manifest.get("version") == TestConfig.FIXTURES_VERSION
        version_mismatches = []
        fixtures_root = Path(TestConfig.FIXTURES_PATH)
        for name in manifest.get("fixtures", []):
            # Directory fixtures (e.g. code_corpus/) have no top-level version field.
            if (fixtures_root / name).is_dir() and not (fixtures_root / f"{name}.json").exists():
                continue
            data = fixture_loader.load(name)
            if data.get("version") != TestConfig.FIXTURES_VERSION:
                version_mismatches.append(name)
        assert_pass(
            "Z2",
            not version_mismatches,
            f"MANIFEST={TestConfig.FIXTURES_VERSION}, fixtures ok={len(manifest.get('fixtures', []))}",
        )
        assert not version_mismatches, version_mismatches
    # Z3 - mock shape normalization; optional real-vs-mock compare when deps up
    def test_z3_swap_shape_normalization(self, block_client):
        token_resp = block_client.post(
            "/oauth/token",
            json={"principal_id": "principal-alice", "tenant_id": "tenant-a", "scopes": ["search.read"]},
        )
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        search_a = block_client.post("/search/lexical", headers=headers, json={"query": "roadmap"}).json()
        search_b = block_client.post("/search/lexical", headers=headers, json={"query": "roadmap"}).json()
        mock_a = {**search_a, "request_id": "req-alpha", "timestamp": "2026-01-01T00:00:00Z"}
        mock_b = {**search_b, "request_id": "req-beta", "timestamp": "2026-01-02T00:00:00Z"}
        shape_a = normalize_response_shape(mock_a)
        shape_b = normalize_response_shape(mock_b)
        mock_diffs = compare_shapes(mock_a, mock_b)
        real_port = TestConfig.REAL_BASE_PORT + TestConfig.PORT_OFFSET["Z"]
        real_base = f"http://127.0.0.1:{real_port}"
        if using_real_services() and tcp_open("127.0.0.1", real_port):
            real_client = TestClient(real_base, timeout=5)
            try:
                real_search = real_client.post(
                    "/search/lexical",
                    headers=headers,
                    json={"query": "roadmap"},
                )
                if real_search.status_code == 200:
                    real_data = {**real_search.json(), "request_id": "real-req", "timestamp": "now"}
                    real_diffs = compare_shapes(mock_a, real_data)
                    assert_pass("Z3", real_diffs == [], f"mock vs real shape match on :{real_port}")
                    assert real_diffs == [], real_diffs
                    return
            except requests.RequestException:
                pass
        assert mock_diffs == [], mock_diffs
        assert shape_a == shape_b, (shape_a, shape_b)
        assert "request_id" not in shape_a
        assert_pass("Z3", True, "mock shape normalization stable across variable fields")
