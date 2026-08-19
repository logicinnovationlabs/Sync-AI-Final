"""P0 security helpers — no full-app TestClient (avoids Qdrant/lifespan flakes)."""

from app.acl.filter import acl_terms_from_jwt, is_fail_closed
from app.api.v1.admin.tenant import _bootstrap_token_ok
from app.connectors.google.webhooks import gmail_verification_ok
from app.core.config import settings


def test_p0_jwt_acl_strips_star_bypass():
    terms = acl_terms_from_jwt({"sub": "alice", "acl_terms": ["*"]})
    assert "*" not in terms
    assert "user:alice" in terms
    assert not is_fail_closed(terms)


def test_p0_bootstrap_token_required(monkeypatch):
    monkeypatch.setattr(settings, "tenant_bootstrap_token", "setup-secret")
    assert _bootstrap_token_ok(None) is False
    assert _bootstrap_token_ok("") is False
    assert _bootstrap_token_ok("wrong") is False
    assert _bootstrap_token_ok("setup-secret") is True
    assert _bootstrap_token_ok("short") is False


def test_p0_bootstrap_rejects_when_token_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "tenant_bootstrap_token", None)
    assert _bootstrap_token_ok("anything") is False
    monkeypatch.setattr(settings, "tenant_bootstrap_token", "")
    assert _bootstrap_token_ok("anything") is False


def test_p0_gmail_verification_fail_closed():
    assert gmail_verification_ok(None, "x") is False
    assert gmail_verification_ok("", "x") is False
    assert gmail_verification_ok("secret", None) is False
    assert gmail_verification_ok("secret", "") is False
    assert gmail_verification_ok("secret", "wrong") is False
    assert gmail_verification_ok("secret", "secret") is True
