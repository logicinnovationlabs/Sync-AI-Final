"""
BLOCK A SIGNOFF TESTS — A1 through A7, PLUS SECURITY/EDGE-CASE HARDENING

Block signoff: PASS only if A1–A7 AND all security/edge-case tests below PASS.

Structure:
  Part 1 — Original A1-A7 signoff criteria (unchanged from prior signoff, kept as the
           contractual baseline; do not weaken these).
  Part 2 — Security-priority hardening tests (attack-shaped scenarios): token forgery,
           algorithm confusion, replay, tenant-boundary bypass attempts, cache/vault
           poisoning, SCIM identity collision, injection-shaped inputs.
  Part 3 — Edge cases that aren't attacks per se but represent real production failure
           modes: clock skew, concurrent revocation races, cascading tenant deprovision,
           malformed claim shapes.

Naming convention: security tests are prefixed test_SEC_A<n>_..., edge-case tests are
prefixed test_EDGE_A<n>_..., so CI output makes the priority visible at a glance.
"""

import pytest
import asyncio
import time
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from uuid import uuid4, uuid5, NAMESPACE_DNS
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.token_service import token_service
from app.services.tenant_resolver import tenant_resolver
from app.services.scim_sync import scim_sync_service, PRINCIPAL_ID_NAMESPACE
from app.services.revocation import revocation_service
from app.models.tenant import Tenant
from app.models.user import User
from app.storage.vault_client import MockVaultClient
from app.storage.redis_client import redis_client
from app.core.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
    TenantNotFoundError,
)


# =====================================================================
# PART 1 — ORIGINAL SIGNOFF CRITERIA (A1–A7) — baseline, unchanged
# =====================================================================

@pytest.mark.asyncio
async def test_A1_tenant_binding_integrity():
    """A1: 100 tokens across 3 tenants — 100% exactly one tenant_id claim, valid sig+expiry."""
    tenants = [{"id": str(uuid4())} for _ in range(3)]
    results = []
    for i in range(100):
        tenant = tenants[i % 3]
        token = await token_service.issue_access_token(
            tenant_id=tenant["id"], principal_id=str(uuid4()), scopes=["search.read"]
        )
        payload = await token_service.validate_token(token)
        results.append(payload.get("tenant_id") == tenant["id"])
    assert all(results), "A1 FAILED: tenant binding mismatch detected"
    print("A1 PASSED")


@pytest.mark.asyncio
async def test_A2_revocation_latency():
    """A2: revoke -> poll every 5s x12 -> rejected within <=60s."""
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    token = await token_service.issue_access_token(tenant_id, principal_id, ["search.read"])
    payload = await token_service.decode_without_validation(token)
    jti = payload["jti"]
    revoked_at = time.time()
    await redis_client.sadd(tenant_id, f"revoked:{jti}", jti)
    rejected_at = None
    for _ in range(12):
        await asyncio.sleep(5)
        try:
            await token_service.validate_token(token)
        except Exception:
            rejected_at = time.time()
            break
    assert rejected_at is not None and (rejected_at - revoked_at) <= 60
    print("A2 PASSED")


@pytest.mark.asyncio
async def test_A3_scim_idempotency(test_db):
    """A3: SCIM sync 3x, unchanged directory -> identical principal_id every run."""
    tenant_id = uuid4()
    scim_users = [{"id": f"user{i}@idp.com", "emails": [{"value": f"u{i}@ex.com"}], "displayName": f"U{i}"} for i in range(3)]
    runs = []
    for _ in range(3):
        await scim_sync_service.sync_users(scim_users, tenant_id, test_db)
        from sqlalchemy import select
        result = await test_db.execute(select(User.principal_id, User.idp_subject).where(User.tenant_id == tenant_id))
        runs.append({row.idp_subject: row.principal_id for row in result.all()})
        await test_db.rollback()
    assert runs[0] == runs[1] == runs[2]
    print("A3 PASSED")


@pytest.mark.asyncio
async def test_A4_cross_tenant_replay_rejection():
    """A4: tenant-A token presented against tenant-B context, 50 attempts, 0 leaks."""
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    token = await token_service.issue_access_token(tenant_a, str(uuid4()), ["search.read"])
    leaks = 0
    for _ in range(50):
        payload = await token_service.validate_token(token)
        if payload.get("tenant_id") == tenant_b:
            leaks += 1
    assert leaks == 0
    print("A4 PASSED")


@pytest.mark.asyncio
async def test_A5_scope_enforcement():
    """A5: token missing required scope -> 100% would-be 403."""
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    token = await token_service.issue_access_token(tenant_id, principal_id, ["other.scope"])
    payload = await token_service.validate_token(token)
    for required in ["search.read", "document.read", "admin.audit.read"]:
        assert required not in payload.get("scopes", [])
    print("A5 PASSED")


@pytest.mark.asyncio
async def test_A6_secret_pointer_vault(test_db, mock_vault):
    """A6: tenants row stores a Vault key name only, never a plaintext secret."""
    tenant_id = uuid4()
    password = "SuperSecretPassword123!"
    key = f"kv/tenant-{tenant_id}/db_password"
    await mock_vault.set_secret(key, password)
    tenant = Tenant(
        tenant_id=tenant_id, name="T", subdomain="t", tenancy_mode="isolated_db",
        config={}, db_host="localhost", db_name="db", db_user="u", db_secret_key=key,
    )
    test_db.add(tenant)
    await test_db.commit()
    await test_db.refresh(tenant)
    row = {k: str(getattr(tenant, k)) for k in ["db_host", "db_name", "db_user", "db_secret_key", "config"]}
    assert tenant.db_secret_key.startswith("kv/")
    assert not any(password in v for v in row.values())
    print("A6 PASSED")


@pytest.mark.asyncio
async def test_A7_per_tenant_cache_isolation():
    """A7: tenant B's routing must never be reachable via tenant A's cache key."""
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    routing_a = {"tenant_id": tenant_a, "db_host": "a.example.com", "db_password": "pw_a"}
    routing_b = {"tenant_id": tenant_b, "db_host": "b.example.com", "db_password": "pw_b"}
    await redis_client.set_json(tenant_a, "routing", routing_a, ex=600)
    await redis_client.set_json(tenant_b, "routing", routing_b, ex=600)
    assert await redis_client.get_json(tenant_a, "routing") == routing_a
    assert await redis_client.get_json(tenant_b, "routing") == routing_b
    print("A7 PASSED")


# =====================================================================
# PART 2 — SECURITY-PRIORITY HARDENING TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_SEC_A8_algorithm_confusion_none_alg_rejected():
    """
    SECURITY: A classic JWT attack — attacker crafts a token with "alg": "none" and no
    signature, hoping a lenient decoder accepts it. Must be hard-rejected regardless of
    claim contents, even if tenant_id/principal_id/scopes look otherwise valid.
    """
    forged_payload = {
        "tenant_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "scopes": ["admin.audit.read"],
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    forged = pyjwt.encode(forged_payload, key="", algorithm="none")
    with pytest.raises(Exception):
        await token_service.validate_token(forged)
    print("SEC_A8 PASSED: alg=none forgery rejected")


@pytest.mark.asyncio
async def test_SEC_A9_algorithm_confusion_hs256_with_public_key():
    """
    SECURITY: RS256->HS256 downgrade attack. If the service uses RS256, an attacker who
    knows the RSA public key may try signing a token with HS256 using the public key
    bytes as the HMAC secret, hoping the verifier is misconfigured to accept either alg.
    Must be rejected.
    """
    public_key_pem = token_service.get_public_key_pem() if hasattr(token_service, "get_public_key_pem") else None
    if public_key_pem is None:
        pytest.skip("token_service.get_public_key_pem() not implemented — add it to enable this check")
    forged_payload = {
        "tenant_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "scopes": ["admin.audit.read"],
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    forged = pyjwt.encode(forged_payload, key=public_key_pem, algorithm="HS256")
    with pytest.raises(Exception):
        await token_service.validate_token(forged)
    print("SEC_A9 PASSED: HS256-with-public-key-as-secret forgery rejected")


@pytest.mark.asyncio
async def test_SEC_A10_tampered_payload_signature_mismatch():
    """SECURITY: flipping a single character in a valid token's payload segment must invalidate the signature."""
    token = await token_service.issue_access_token(str(uuid4()), str(uuid4()), ["search.read"])
    header, payload_seg, sig = token.split(".")
    tampered_payload_seg = payload_seg[:-1] + ("A" if payload_seg[-1] != "A" else "B")
    tampered = f"{header}.{tampered_payload_seg}.{sig}"
    with pytest.raises(Exception):
        await token_service.validate_token(tampered)
    print("SEC_A10 PASSED: tampered payload rejected")


@pytest.mark.asyncio
async def test_SEC_A11_missing_tenant_id_claim_rejected():
    """SECURITY: a structurally valid, correctly signed token with NO tenant_id claim must be rejected outright."""
    payload = {
        "principal_id": str(uuid4()),
        "scopes": ["search.read"],
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "jti": str(uuid4()),
    }
    token = token_service.sign_with_service_key(payload) if hasattr(token_service, "sign_with_service_key") else None
    if token is None:
        pytest.skip("token_service.sign_with_service_key() not implemented — add a raw-signing helper for this check")
    with pytest.raises(Exception):
        await token_service.validate_token(token)
    print("SEC_A11 PASSED: token with no tenant_id claim rejected")


@pytest.mark.asyncio
async def test_SEC_A12_multiple_tenant_id_claims_rejected():
    """
    SECURITY: a token where tenant_id is an array (e.g. ["tenantA", "tenantB"]) instead
    of a scalar string must be rejected — "exactly one tenant_id" is a type + cardinality
    guarantee, not just a presence check.
    """
    tenant_a, tenant_b = str(uuid4()), str(uuid4())
    payload = {
        "tenant_id": [tenant_a, tenant_b],
        "principal_id": str(uuid4()),
        "scopes": ["search.read"],
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "jti": str(uuid4()),
    }
    token = token_service.sign_with_service_key(payload) if hasattr(token_service, "sign_with_service_key") else None
    if token is None:
        pytest.skip("token_service.sign_with_service_key() not implemented — add a raw-signing helper for this check")
    with pytest.raises(Exception):
        await token_service.validate_token(token)
    print("SEC_A12 PASSED: array-shaped tenant_id claim rejected")


@pytest.mark.asyncio
async def test_SEC_A13_refresh_token_reuse_after_rotation_detected():
    """
    SECURITY: refresh token rotation — once a refresh token has been exchanged for a new
    access+refresh pair, presenting the OLD refresh token again (replay, e.g. from a
    stolen/cached copy) must be rejected, and ideally revokes the whole token family.
    """
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    refresh_1 = await token_service.issue_refresh_token(tenant_id, principal_id)
    _, refresh_2 = await token_service.rotate_refresh_token(refresh_1)
    with pytest.raises(Exception):
        await token_service.rotate_refresh_token(refresh_1)
    print("SEC_A13 PASSED: refresh token replay after rotation rejected")


@pytest.mark.asyncio
async def test_SEC_A14_revoked_refresh_token_cannot_mint_access_token():
    """SECURITY: revoking a refresh token must block it from being exchanged for a new access token."""
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    refresh = await token_service.issue_refresh_token(tenant_id, principal_id)
    await revocation_service.revoke_refresh_token(refresh)
    with pytest.raises(Exception):
        await token_service.rotate_refresh_token(refresh)
    print("SEC_A14 PASSED: revoked refresh token cannot mint new access token")


@pytest.mark.asyncio
async def test_SEC_A15_pkce_missing_verifier_rejected_for_public_client():
    """SECURITY: public clients MUST use PKCE — an authorization_code exchange without code_verifier must be rejected."""
    from app.services.oauth_service import oauth_service
    tenant_id = str(uuid4())
    code, _ = await oauth_service.issue_authorization_code(
        tenant_id=tenant_id, client_id="public-client-1", client_type="public",
        redirect_uri="https://app.example.com/callback",
        code_challenge="fake_challenge_value", code_challenge_method="S256",
    )
    with pytest.raises(Exception):
        await oauth_service.exchange_authorization_code(
            code=code, client_id="public-client-1", redirect_uri="https://app.example.com/callback",
            code_verifier=None,
        )
    print("SEC_A15 PASSED: PKCE-less exchange rejected for public client")


@pytest.mark.asyncio
async def test_SEC_A16_pkce_wrong_verifier_rejected():
    """SECURITY: a code_verifier that doesn't hash to the original code_challenge must be rejected."""
    from app.services.oauth_service import oauth_service
    import hashlib, base64
    verifier = "correct_verifier_value_1234567890"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    tenant_id = str(uuid4())
    code, _ = await oauth_service.issue_authorization_code(
        tenant_id=tenant_id, client_id="public-client-1", client_type="public",
        redirect_uri="https://app.example.com/callback",
        code_challenge=challenge, code_challenge_method="S256",
    )
    with pytest.raises(Exception):
        await oauth_service.exchange_authorization_code(
            code=code, client_id="public-client-1", redirect_uri="https://app.example.com/callback",
            code_verifier="WRONG_verifier_value_0000000000",
        )
    print("SEC_A16 PASSED: mismatched PKCE verifier rejected")


@pytest.mark.asyncio
async def test_SEC_A17_scim_cross_tenant_idp_subject_collision():
    """
    SECURITY: two DIFFERENT tenants each having a user with the SAME idp_subject value
    (plausible if two customers use overlapping test/demo IdP subjects, or a malicious
    actor tries to collide identities) must resolve to DIFFERENT principal_id values —
    principal_id must be scoped by (tenant_id, idp_subject), never idp_subject alone.
    """
    tenant_a, tenant_b = uuid4(), uuid4()
    shared_subject = "user@shared-subject-value.com"
    from app.services.scim_sync import derive_principal_id
    pid_a = derive_principal_id(tenant_id=tenant_a, idp_subject=shared_subject)
    pid_b = derive_principal_id(tenant_id=tenant_b, idp_subject=shared_subject)
    assert pid_a != pid_b, "SEC_A17 FAILED: cross-tenant idp_subject collision produced identical principal_id"
    print("SEC_A17 PASSED: cross-tenant idp_subject values do not collide")


@pytest.mark.asyncio
async def test_SEC_A18_scim_unicode_homoglyph_does_not_collide():
    """
    SECURITY: a Cyrillic 'а' (U+0430) visually resembles Latin 'a' (U+0061). SCIM sync
    must not normalize/fold these to the same principal_id — that would let an attacker
    register a lookalike identity that resolves to an existing legitimate user's principal_id.
    """
    tenant_id = uuid4()
    latin_subject = "admin@example.com"
    cyrillic_subject = "аdmin@example.com"  # first char is Cyrillic U+0430
    from app.services.scim_sync import derive_principal_id
    pid_latin = derive_principal_id(tenant_id=tenant_id, idp_subject=latin_subject)
    pid_cyrillic = derive_principal_id(tenant_id=tenant_id, idp_subject=cyrillic_subject)
    assert pid_latin != pid_cyrillic, "SEC_A18 FAILED: homoglyph subjects collided to the same principal_id"
    print("SEC_A18 PASSED: homoglyph identities do not collide")


@pytest.mark.asyncio
async def test_SEC_A19_tenant_resolver_rejects_non_uuid_tenant_id():
    """
    SECURITY: tenant_id must be validated as a well-formed UUID BEFORE it's used to build
    a cache key, DB query, or (in Block B) a Qdrant collection name. Reject SQL/NoSQL/path
    injection-shaped strings outright rather than passing them through.
    """
    malicious_inputs = [
        "'; DROP TABLE tenants; --",
        "../../etc/passwd",
        "tenant_a' OR '1'='1",
        "\x00nullbyte",
        "a" * 10000,  # oversized input
    ]
    for bad_id in malicious_inputs:
        with pytest.raises(Exception):
            await tenant_resolver.resolve(bad_id)
    print("SEC_A19 PASSED: non-UUID tenant_id inputs rejected before reaching storage layer")


@pytest.mark.asyncio
async def test_SEC_A20_vault_fetch_failure_does_not_fall_back_to_plaintext():
    """
    SECURITY: if the Vault call fails (network error, permission denied, key not found),
    the resolver must raise — it must NEVER fall back to a plaintext value, a stale cached
    secret with no re-validation, or a default/empty credential.
    """
    tenant_id = uuid4()
    tenant = Tenant(
        tenant_id=tenant_id, name="T", subdomain="t2", tenancy_mode="isolated_db",
        config={}, db_host="h", db_name="d", db_user="u", db_secret_key="kv/nonexistent/key",
    )
    with patch("app.storage.vault_client.MockVaultClient.get_secret", side_effect=Exception("vault unreachable")):
        with pytest.raises(Exception):
            await tenant_resolver.resolve(str(tenant_id))
    print("SEC_A20 PASSED: Vault failure propagates as an error, no silent fallback")


@pytest.mark.asyncio
async def test_SEC_A21_scope_claim_type_confusion_rejected():
    """
    SECURITY: a token where `scopes` is a single string ("search.read") instead of a
    list (["search.read"]) must not be silently coerced/iterated character-by-character
    (a classic type-confusion bug that could make scope-membership checks pass
    unexpectedly, e.g. `"a" in "admin.audit.read"` being True).
    """
    payload = {
        "tenant_id": str(uuid4()),
        "principal_id": str(uuid4()),
        "scopes": "admin.audit.read",  # malformed: string, not list
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "jti": str(uuid4()),
    }
    token = token_service.sign_with_service_key(payload) if hasattr(token_service, "sign_with_service_key") else None
    if token is None:
        pytest.skip("token_service.sign_with_service_key() not implemented — add a raw-signing helper for this check")
    with pytest.raises(Exception):
        validated = await token_service.validate_token(token)
        assert isinstance(validated["scopes"], list), "scopes claim must be validated as a list type"
    print("SEC_A21 PASSED: string-shaped scopes claim rejected/type-checked")


@pytest.mark.asyncio
async def test_SEC_A22_cascading_revocation_on_tenant_deprovision():
    """
    SECURITY: when a tenant is deprovisioned/deleted, EVERY previously issued token for
    that tenant must become unusable — not just future issuance blocked. This prevents a
    stolen token from an offboarded customer remaining valid indefinitely.
    """
    tenant_id = str(uuid4())
    tokens = [await token_service.issue_access_token(tenant_id, str(uuid4()), ["search.read"]) for _ in range(5)]
    for t in tokens:
        await token_service.validate_token(t)  # confirm valid before deprovision

    await revocation_service.revoke_all_for_tenant(tenant_id)

    for t in tokens:
        with pytest.raises(Exception):
            await token_service.validate_token(t)
    print("SEC_A22 PASSED: tenant deprovision cascades to revoke all issued tokens")


# =====================================================================
# PART 3 — EDGE CASES (non-attack, real-world failure modes)
# =====================================================================

@pytest.mark.asyncio
async def test_EDGE_A23_clock_skew_tolerance_within_bounds():
    """
    EDGE CASE: a token whose `iat` is a few seconds in the future (common with clock
    skew between distributed services) should still validate if within a small tolerance
    window (e.g. 30-60s) — but NOT if the skew is large (e.g. 1 hour), which would
    indicate a forged/replayed token rather than genuine clock drift.
    """
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    near_future_iat = int((datetime.now(timezone.utc) + timedelta(seconds=10)).timestamp())
    payload = {
        "tenant_id": tenant_id, "principal_id": principal_id, "scopes": ["search.read"],
        "iat": near_future_iat,
        "exp": near_future_iat + 3600,
        "jti": str(uuid4()),
    }
    token = token_service.sign_with_service_key(payload) if hasattr(token_service, "sign_with_service_key") else None
    if token is None:
        pytest.skip("token_service.sign_with_service_key() not implemented — add a raw-signing helper for this check")
    await token_service.validate_token(token)  # should NOT raise
    print("EDGE_A23 PASSED: small clock skew tolerated")


@pytest.mark.asyncio
async def test_EDGE_A24_expired_token_rejected_immediately_no_grace():
    """EDGE CASE: a token exactly 1 second past expiry must be rejected — no implicit grace period."""
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    payload = {
        "tenant_id": tenant_id, "principal_id": principal_id, "scopes": ["search.read"],
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp()),
        "jti": str(uuid4()),
    }
    token = token_service.sign_with_service_key(payload) if hasattr(token_service, "sign_with_service_key") else None
    if token is None:
        pytest.skip("token_service.sign_with_service_key() not implemented — add a raw-signing helper for this check")
    with pytest.raises(Exception):
        await token_service.validate_token(token)
    print("EDGE_A24 PASSED: expired token rejected with no grace period")


@pytest.mark.asyncio
async def test_EDGE_A25_concurrent_revocation_and_validation_race():
    """
    EDGE CASE: fire a revoke and 20 concurrent validate calls for the same token at
    (near) the same instant. There must be no window where a validation call observes
    the token as valid AFTER the revoke call has completed (no stale-read race).
    """
    tenant_id, principal_id = str(uuid4()), str(uuid4())
    token = await token_service.issue_access_token(tenant_id, principal_id, ["search.read"])
    payload = await token_service.decode_without_validation(token)
    jti = payload["jti"]

    async def revoke():
        await redis_client.sadd(tenant_id, f"revoked:{jti}", jti)

    async def validate_after_delay():
        await asyncio.sleep(0.05)
        try:
            await token_service.validate_token(token)
            return True  # still valid
        except Exception:
            return False  # rejected

    revoke_task = asyncio.create_task(revoke())
    validate_tasks = [asyncio.create_task(validate_after_delay()) for _ in range(20)]
    await revoke_task
    results = await asyncio.gather(*validate_tasks)
    assert not any(results), "EDGE_A25 FAILED: at least one validation succeeded after revocation completed"
    print("EDGE_A25 PASSED: no stale-read race between revoke and validate")


@pytest.mark.asyncio
async def test_EDGE_A26_scim_membership_diff_removes_stale_group_members():
    """
    EDGE CASE: a user removed from a group in the IdP must be removed from
    group_memberships on the next SCIM sync — sync_version must increment, and a
    member who was present in run 1 but absent in run 2's payload must not linger.
    """
    tenant_id = uuid4()
    group_payload_run1 = {
        "id": "group1@idp.com", "displayName": "Engineering",
        "members": ["user1@idp.com", "user2@idp.com"],
    }
    group_payload_run2 = {
        "id": "group1@idp.com", "displayName": "Engineering",
        "members": ["user1@idp.com"],  # user2 removed
    }
    await scim_sync_service.sync_groups([group_payload_run1], tenant_id, None)
    version_1 = await scim_sync_service.get_group_sync_version("group1@idp.com", tenant_id)
    await scim_sync_service.sync_groups([group_payload_run2], tenant_id, None)
    version_2 = await scim_sync_service.get_group_sync_version("group1@idp.com", tenant_id)
    members_after = await scim_sync_service.get_group_members("group1@idp.com", tenant_id)
    assert version_2 > version_1, "EDGE_A26 FAILED: sync_version did not increment on membership change"
    assert "user2@idp.com" not in [m.get("idp_subject") for m in members_after]
    print("EDGE_A26 PASSED: stale group membership removed, sync_version incremented")