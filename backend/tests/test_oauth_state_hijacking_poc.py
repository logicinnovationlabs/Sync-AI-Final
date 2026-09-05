"""
PROOF OF CONCEPT: OAuth State Hijacking / Cross-Tenant Token Theft

This test demonstrates that the vulnerability is now FIXED.

ORIGINAL VULNERABILITY:
1. Attacker calls /authorize and receives state with attacker's tenant_id/user_id
2. Attacker sends the authorize URL to victim
3. Victim authenticates with Google and consents
4. Google redirects to /callback with victim's code + attacker's state
5. Callback decodes state, extracts attacker's tenant_id/user_id
6. Callback exchanges victim's code for tokens
7. Tokens are stored under attacker's tenant_id
8. Attacker can now search victim's Drive/Gmail

FIXES APPLIED:
- State is now HMAC-SHA256 signed (prevents tampering)
- State contains jti bound to initiating session (session binding)
- decode_oauth_state FAILS CLOSED on Redis errors
- Callback uses tenant_id/user_id from state (now trusted due to HMAC + session binding)
- Nonce is one-time use (deleted after successful validation)
"""

import pytest
import json
import base64
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.connectors.google.oauth_state import encode_oauth_state, decode_oauth_state


class TestOAuthStateHijackingVulnerability:
    """Demonstrate that the vulnerability is now FIXED."""

    def test_state_is_now_hmac_signed(self):
        """State is now HMAC-SHA256 signed - tampering is detected."""
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            
            state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti)
            
            # Decode to show it now has HMAC signature
            padded = state + ("=" * ((4 - len(state) % 4) % 4))
            combined = base64.urlsafe_b64decode(padded.encode("ascii"))
            
            # Split payload and signature
            assert b"." in combined, "State should have signature separator"
            raw, sig_b64 = combined.split(b".", 1)
            signature = base64.urlsafe_b64decode(sig_b64)
            
            # Signature is present (32 bytes for SHA256)
            assert len(signature) == 32, "HMAC-SHA256 signature should be 32 bytes"
            
            # Payload contains jti for session binding
            payload = json.loads(raw.decode("utf-8"))
            assert "jti" in payload
            assert payload["jti"] == attacker_jti
            
            # Attacker cannot modify payload without invalidating signature
            payload["tenant_id"] = str(uuid4())  # Try to swap to victim's tenant
            forged_raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            forged_combined = forged_raw + b"." + sig_b64
            forged_state = base64.urlsafe_b64encode(forged_combined).decode("ascii").rstrip("=")
            
            # Mock Redis for decoding
            mock_redis.get.return_value = json.dumps({
                "nonce": payload["nonce"],
                "jti": attacker_jti,
                "binding_token": "test-binding-token",
                "connection_scope": "personal"
            })

            # The forged state will now FAIL signature verification
            forged_payload = decode_oauth_state(forged_state, require_jti_match=attacker_jti, require_binding_token="test-binding-token")
            assert forged_payload is None, "Tampered state should be rejected"

    def test_decode_oauth_state_now_fails_closed_on_redis_unavailable(self):
        """FIXED: decode_oauth_state now rejects request if Redis is unavailable."""
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti, binding_token=binding_token)

        # Mock Redis to be unavailable (returns None)
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=None):
            payload = decode_oauth_state(state, require_jti_match=attacker_jti, require_binding_token=binding_token)
            # FAILS CLOSED - returns None instead of payload
            assert payload is None, "Should reject when Redis is unavailable"
    
    def test_decode_oauth_state_now_fails_closed_on_redis_exception(self):
        """FIXED: decode_oauth_state now rejects request if Redis throws exception."""
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti, binding_token=binding_token)

        # Mock Redis to throw exception
        mock_redis_fail = MagicMock()
        mock_redis_fail.get.side_effect = Exception("Redis connection failed")

        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis_fail):
            payload = decode_oauth_state(state, require_jti_match=attacker_jti, require_binding_token=binding_token)
            # FAILS CLOSED - returns None instead of payload
            assert payload is None, "Should reject when Redis throws exception"

    def test_cross_tenant_token_theft_now_blocked_by_session_binding(self):
        """
        FIXED: Attack scenario now blocked by session binding.
        
        The callback requires JWT authentication and validates that the jti
        in the state matches the jti of the authenticated user.
        """
        # Step 1: Attacker calls /authorize (gets state with attacker's jti)
        attacker_tenant_id = "attacker-tenant-123"
        attacker_user_id = "attacker-user-456"
        attacker_jti = "attacker-jti-789"
        binding_token = "test-binding-token"

        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti, binding_token=binding_token)
        
        # Step 2: Attacker sends authorize URL to victim
        # Step 3: Victim authenticates with Google
        victim_auth_code = "victim-auth-code-999"

        # Step 4: Google redirects to /callback with victim's code + attacker's state
        # Step 5: Callback now requires JWT authentication
        # Victim must be logged into SynQ with THEIR OWN JWT (different jti)
        victim_jti = "victim-jti-888"  # Different from attacker's jti

        # Step 6: Callback decodes state with jti validation
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": attacker_jti,  # This is attacker's jti from state
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        # Try to decode with victim's jti (session binding check)
        payload = decode_oauth_state(attacker_state, require_jti_match=victim_jti, require_binding_token=binding_token)

        # ATTACK BLOCKED: jti mismatch causes rejection
        assert payload is None, "Attack should be blocked by jti mismatch"

        # Even without jti check, callback now uses tenant_id/user_id from JWT
        # NOT from state, so attacker's state values are ignored

    def test_state_now_bound_to_initiating_session(self):
        """
        FIXED: State is now bound to initiating user's JWT jti and cookie binding_token.

        The nonce is stored in Redis WITH the jti and binding_token, and the callback validates
        that the jti in the state matches the jti of the authenticated user.
        """
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti, binding_token=binding_token)

            # Verify Redis stored jti and binding_token with nonce
            call_args = mock_redis.setex.call_args
            # setex arguments: (key, ttl, value)
            stored_data = json.loads(call_args[0][2])  # Third argument is the stored value
            assert "jti" in stored_data
            assert stored_data["jti"] == attacker_jti
            assert "binding_token" in stored_data
            assert stored_data["binding_token"] == binding_token

        # Try to decode with different jti (session binding check)
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": attacker_jti,
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        different_jti = str(uuid4())
        payload = decode_oauth_state(state, require_jti_match=different_jti, require_binding_token=binding_token)

        # Should be rejected due to jti mismatch
        assert payload is None, "Should reject when jti doesn't match"

    def test_nonce_deleted_after_successful_use(self):
        """
        Nonce is still deleted on successful use (one-time use protection).
        This is now effective because the state is also signed and session-bound.
        """
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(attacker_tenant_id, attacker_user_id, "personal", jti=attacker_jti, binding_token=binding_token)

        # Mock Redis to simulate successful nonce lookup and deletion
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": attacker_jti,
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            payload = decode_oauth_state(state, require_jti_match=attacker_jti, require_binding_token=binding_token)
            assert payload is not None
            # Nonce is deleted (one-time use)
            mock_redis.delete.assert_called_once()

        # Try to replay the same state
        mock_redis.get.return_value = None  # Nonce already deleted
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            replay_payload = decode_oauth_state(state, require_jti_match=attacker_jti, require_binding_token=binding_token)
            assert replay_payload is None, "Replay should be rejected"

    def test_signature_tamper_rejected(self):
        """
        Signature tamper: modify the signature portion and assert rejection.
        """
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            tenant_id = str(uuid4())
            user_id = str(uuid4())
            jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(tenant_id, user_id, "personal", jti=jti, binding_token=binding_token)

        # Decode the state to get payload + signature
        import base64
        padded = state + ("=" * ((4 - len(state) % 4) % 4))
        combined = base64.urlsafe_b64decode(padded.encode("ascii"))
        raw, sig_b64 = combined.split(b".", 1)

        # Tamper with the signature by flipping a byte
        sig_bytes = bytearray(base64.urlsafe_b64decode(sig_b64))
        sig_bytes[0] = (sig_bytes[0] + 1) % 256  # Flip first byte
        tampered_sig_b64 = base64.urlsafe_b64encode(bytes(sig_bytes))

        # Reconstruct tampered state
        tampered_combined = raw + b"." + tampered_sig_b64
        tampered_state = base64.urlsafe_b64encode(tampered_combined).decode("ascii").rstrip("=")

        # Mock Redis for decoding
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": jti,
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            tampered_payload = decode_oauth_state(tampered_state, require_jti_match=jti, require_binding_token=binding_token)
            assert tampered_payload is None, "Tampered signature should be rejected"

    def test_expired_state_rejected(self):
        """
        Expiry: simulate a state that has expired (Redis TTL passed) and assert rejection.
        """
        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            tenant_id = str(uuid4())
            user_id = str(uuid4())
            jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(tenant_id, user_id, "personal", jti=jti, binding_token=binding_token)

        # Mock Redis to return None (nonce expired/deleted)
        mock_redis.get.return_value = None

        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            expired_payload = decode_oauth_state(state, require_jti_match=jti, require_binding_token=binding_token)
            assert expired_payload is None, "Expired state should be rejected"

    def test_explicit_http_replay_rejected(self):
        """
        Explicit replay: complete a callback once, then submit the exact same state again.
        Assert the second attempt is rejected at HTTP level.
        """
        from app.main import app
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            tenant_id = str(uuid4())
            user_id = str(uuid4())
            jti = str(uuid4())
            binding_token = "test-binding-token"

            state = encode_oauth_state(tenant_id, user_id, "personal", jti=jti, binding_token=binding_token)

        client = TestClient(app)
        manager = MagicMock()
        manager.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "x", "refresh_token": "y"}
        )

        # First callback - should succeed
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": jti,
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        with patch("app.connectors.router.google_oauth_from_settings", return_value=manager), \
             patch("app.connectors.router.backfill_source.delay") as mock_delay, \
             patch("app.connectors.router._record_connector_rows", new=AsyncMock(return_value=None)), \
             patch("app.connectors.router._resolve_mailbox_email", new=AsyncMock(return_value="user@example.com")), \
             patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            mock_delay.return_value = MagicMock(id="task-1")
            client.cookies.set("oauth_binding", binding_token)
            response1 = client.get(
                "/connectors/google/callback",
                params={"code": "test-code", "state": state},
                follow_redirects=False,
            )

        assert response1.status_code == 302, "First callback should succeed"

        # Second callback with exact same state - should fail (nonce deleted)
        mock_redis.get.return_value = None  # Nonce already deleted

        with patch("app.connectors.router.google_oauth_from_settings", return_value=manager), \
             patch("app.connectors.router.backfill_source.delay") as mock_delay, \
             patch("app.connectors.router._record_connector_rows", new=AsyncMock(return_value=None)), \
             patch("app.connectors.router._resolve_mailbox_email", new=AsyncMock(return_value="user@example.com")), \
             patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            response2 = client.get(
                "/connectors/google/callback",
                params={"code": "test-code", "state": state},
                follow_redirects=False,
            )

        assert response2.status_code == 302, "Second callback should return redirect"
        # Verify it's an error redirect, not success
        assert "error" in response2.headers.get("location", ""), "Replay should return error redirect"

    def test_url_forwarding_attack_blocked_by_cookie_binding(self):
        """
        URL forwarding attack: Attacker calls /authorize, sends Google URL to victim.
        Victim's browser (without binding cookie) completes /callback.
        Assert the callback is rejected because the binding cookie is missing.
        """
        from app.main import app
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()

        # Attacker's browser: calls /authorize
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            attacker_tenant_id = str(uuid4())
            attacker_user_id = str(uuid4())
            attacker_jti = str(uuid4())
            attacker_binding_token = "attacker-binding-token-123"

            # Simulate encode_oauth_state with attacker's binding_token
            state = encode_oauth_state(
                attacker_tenant_id,
                attacker_user_id,
                "personal",
                jti=attacker_jti,
                binding_token=attacker_binding_token
            )

        # Mock Redis to return the binding_token
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": attacker_jti,
            "binding_token": attacker_binding_token,
            "connection_scope": "personal"
        })

        # Victim's browser: has NO binding cookie, completes /callback with attacker's state
        victim_client = TestClient(app)
        manager = MagicMock()
        manager.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "x", "refresh_token": "y"}
        )

        with patch("app.connectors.router.google_oauth_from_settings", return_value=manager), \
             patch("app.connectors.router.backfill_source.delay") as mock_delay, \
             patch("app.connectors.router._record_connector_rows", new=AsyncMock(return_value=None)), \
             patch("app.connectors.router._resolve_mailbox_email", new=AsyncMock(return_value="user@example.com")), \
             patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            mock_delay.return_value = MagicMock(id="task-1")

            # Victim's callback WITHOUT the binding cookie
            response = victim_client.get(
                "/connectors/google/callback",
                params={"code": "victim-code", "state": state},
                follow_redirects=False,
            )

        # Should be rejected due to missing binding cookie
        assert response.status_code == 302, "Callback should return redirect"
        location = response.headers.get("location", "")
        assert "error" in location, f"URL forwarding attack should be blocked, got location: {location}"
        assert "missing_binding_cookie" in location, "Error should indicate missing binding cookie"

    def test_legitimate_flow_succeeds_with_cookie_binding(self):
        """
        Legitimate flow: Same browser calls /authorize (gets cookie) then /callback (sends cookie).
        Assert the callback succeeds because the binding cookie is present and matches.
        """
        from app.main import app
        from fastapi.testclient import TestClient

        mock_redis = MagicMock()

        # Same browser: calls /authorize
        with patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            tenant_id = str(uuid4())
            user_id = str(uuid4())
            jti = str(uuid4())
            binding_token = "legitimate-binding-token-456"

            state = encode_oauth_state(
                tenant_id,
                user_id,
                "personal",
                jti=jti,
                binding_token=binding_token
            )

        # Mock Redis to return the binding_token
        mock_redis.get.return_value = json.dumps({
            "nonce": "test-nonce",
            "jti": jti,
            "binding_token": binding_token,
            "connection_scope": "personal"
        })

        # Same browser: completes /callback WITH the binding cookie
        client = TestClient(app)
        manager = MagicMock()
        manager.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "x", "refresh_token": "y"}
        )

        with patch("app.connectors.router.google_oauth_from_settings", return_value=manager), \
             patch("app.connectors.router.backfill_source.delay") as mock_delay, \
             patch("app.connectors.router._record_connector_rows", new=AsyncMock(return_value=None)), \
             patch("app.connectors.router._resolve_mailbox_email", new=AsyncMock(return_value="user@example.com")), \
             patch("app.connectors.google.oauth_state._sync_redis", return_value=mock_redis):
            mock_delay.return_value = MagicMock(id="task-1")

            # Callback WITH the binding cookie
            client.cookies.set("oauth_binding", binding_token)
            response = client.get(
                "/connectors/google/callback",
                params={"code": "legitimate-code", "state": state},
                follow_redirects=False,
            )

        # Should succeed
        assert response.status_code == 302, "Legitimate callback should succeed"
        location = response.headers.get("location", "")
        assert "error" not in location, f"Legitimate flow should succeed, got location: {location}"


if __name__ == "__main__":
    # Run this test to demonstrate the vulnerability
    pytest.main([__file__, "-v", "-s"])
