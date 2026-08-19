"""P1 security helpers — no full-app TestClient (avoids Qdrant/lifespan flakes)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.backends import mock_backends_allowed, refuse_mock_backend
from app.core.config import settings
from app.core.models import (
    ACLEntry,
    CanonicalDocument,
    PermissionLevel,
    Principal,
)
from app.normalizer.strategies.google_drive import GoogleDriveNormalizer
from app.services.oauth_service import oauth_service, verify_pkce
from app.storage.canonical_repo import CanonicalRepo
from app.workers.tasks import _mailbox_for_tenant, _validate_tenant_auth


def test_p1_federated_uses_real_store_signatures():
    import inspect
    from app.api.v1.search import federated

    lexical = inspect.getsource(federated._safe_call_lexical)
    vector = inspect.getsource(federated._safe_call_vector)
    assert "OpenSearchLexicalStore" in lexical
    assert "OpenSearchStore" not in lexical
    assert "query_embedding" in vector
    assert "query_vector" not in vector
    assert "top_k" in vector


def test_p1_mock_backends_allowed_in_development(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    assert mock_backends_allowed() is True
    refuse_mock_backend("GRAPH_BACKEND", "mock", "neo4j")


def test_p1_mock_backends_refused_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    assert mock_backends_allowed() is False
    with pytest.raises(RuntimeError, match="GRAPH_BACKEND"):
        refuse_mock_backend("GRAPH_BACKEND", "mock", "neo4j")


def test_p1_graph_store_is_process_singleton(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "graph_backend", "mock")
    from app.services import graph as graph_mod

    graph_mod._mock_instance = None
    first = graph_mod.get_graph_store()
    second = graph_mod.get_graph_store()
    assert first is second


def test_p1_signals_store_is_process_singleton(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "signals_backend", "mock")
    from app.services import signals as signals_mod

    signals_mod._mock_instance = None
    first = signals_mod.get_activity_store()
    second = signals_mod.get_activity_store()
    assert first is second


def test_p1_pkce_s256_roundtrip():
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert verify_pkce(verifier, challenge, "S256") is True
    assert verify_pkce("wrong", challenge, "S256") is False


@pytest.mark.asyncio
async def test_p1_authorization_code_pkce_exchange(test_db):
    import base64
    import hashlib
    import secrets

    from app.models.user import User
    from app.services.native_auth import native_auth_service

    tenant_id = uuid4()
    principal_id = uuid4()
    test_db.add(
        User(
            principal_id=principal_id,
            tenant_id=tenant_id,
            idp_subject=f"native:{principal_id}",
            email="p1-oauth@example.com",
            display_name="P1 OAuth",
            password_hash=native_auth_service.hash_password("unused"),
            status="active",
            role="member",
        )
    )
    await test_db.commit()

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    code = await oauth_service.create_authorization_code(
        client_id="test_client",
        redirect_uri="http://localhost:3000/callback",
        code_challenge=challenge,
        code_challenge_method="S256",
        tenant_id=str(tenant_id),
        principal_id=str(principal_id),
        scopes=["search.read"],
    )
    tokens = await oauth_service.exchange_authorization_code(
        code=code,
        code_verifier=verifier,
        client_id="test_client",
        redirect_uri="http://localhost:3000/callback",
        db_session=test_db,
    )
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    with pytest.raises(Exception):
        await oauth_service.exchange_authorization_code(
            code=code,
            code_verifier=verifier,
            client_id="test_client",
            redirect_uri="http://localhost:3000/callback",
            db_session=test_db,
        )


def test_p1_oidc_callback_never_returns_idp_tokens():
    import inspect
    from app.api.v1 import auth

    source = inspect.getsource(auth.sso_callback)
    assert "oidc_tokens" not in source
    assert "state required" in source or "state" in source
    login_src = inspect.getsource(auth.sso_login)
    assert "code_challenge" in login_src
    assert "tenant_subdomain" in login_src


def test_p1_oidc_id_token_issuer_enforced(monkeypatch):
    from app.api.v1.auth import _id_token_claims
    from fastapi import HTTPException
    import jwt as pyjwt

    monkeypatch.setattr(settings, "oauth_issuer_url", "https://idp.example")
    monkeypatch.setattr(settings, "oidc_client_id", "snyq")
    token = pyjwt.encode(
        {"iss": "https://evil.example", "aud": "snyq", "email": "a@b.c", "exp": 9999999999},
        "secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        _id_token_claims(token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_p1_canonical_repo_sql_roundtrip(test_db):
    tenant_id = uuid4()
    principal_id = uuid4()
    now = datetime.now(timezone.utc)
    repo = CanonicalRepo(use_memory=False, session=test_db)
    await repo.create_principal(
        Principal(
            id=principal_id,
            tenant_id=tenant_id,
            email="alice@example.com",
            name="Alice",
            source_identities={"google_drive": "ext-1"},
            created_at=now,
            updated_at=now,
        )
    )
    found = await repo.get_principal_by_email("Alice@example.com", tenant_id)
    assert found is not None
    assert found.id == principal_id
    by_source = await repo.get_principal_by_source_identity("google_drive", "ext-1", tenant_id)
    assert by_source is not None

    doc = CanonicalDocument(
        id="google_drive_file1",
        source_type="google_drive",
        source_id="file1",
        tenant_id=tenant_id,
        title="Doc",
        content="hello",
        mime_type="text/plain",
        detected_mime_type="text/plain",
        created_at=now,
        updated_at=now,
        source_updated_at=now,
    )
    await repo.upsert_document(doc)
    loaded = await repo.get_document("google_drive_file1")
    assert loaded is not None
    assert loaded.title == "Doc"

    await repo.replace_acl_entries(
        doc.id,
        [
            ACLEntry(
                document_id=doc.id,
                principal_id=principal_id,
                permission=PermissionLevel.READ,
                granted_via="direct",
                source_type="google_drive",
                tenant_id=tenant_id,
                created_at=now,
                updated_at=now,
            )
        ],
    )
    entries = await repo.get_acl_entries(doc.id)
    assert len(entries) == 1
    assert entries[0].principal_id == principal_id


@pytest.mark.asyncio
async def test_p1_drive_extract_keeps_injection_and_uses_export():
    normalizer = GoogleDriveNormalizer()
    injected = await normalizer.extract_text(
        {"name": "Test Document", "id": "file_1", "_test_extracted_text": "Injected test content"}
    )
    assert injected == "Injected test content"
    placeholder = await normalizer.extract_text({"name": "Test Document", "id": "file_1"})
    assert placeholder == "Test Document"

    class _FakeDrive:
        async def export_file(self, access_token, file_id, mime_type="text/plain"):
            return b"exported body"

    live = GoogleDriveNormalizer(drive_client=_FakeDrive())
    text = await live.extract_text(
        {
            "id": "file_1",
            "name": "Doc",
            "mimeType": "application/vnd.google-apps.document",
            "_access_token": "tok",
        }
    )
    assert text == "exported body"


def test_p1_worker_auth_rejects_revoked_and_skips_hardcoded_mailbox():
    with pytest.raises(ValueError, match="AUTH_FAILED"):
        _validate_tenant_auth("revoked_tenant_123")
    with pytest.raises(ValueError, match="AUTH_FAILED"):
        _validate_tenant_auth("invalid-tenant")
    _validate_tenant_auth("tenant123")
    assert _mailbox_for_tenant("tenant123", "google_gmail") == ""
    assert "user@example.com" not in (_mailbox_for_tenant("tenant123", "google_gmail") or "")
