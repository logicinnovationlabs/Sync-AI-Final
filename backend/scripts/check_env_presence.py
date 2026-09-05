"""
Report PRESENT/MISSING for required settings keys — never print values.

Usage (from backend/):
  python scripts/check_env_presence.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.core.config import settings  # noqa: E402

REQUIRED = [
    # Master-prompt
    "tenant_metadata_service_url",
    "oauth_issuer_url",
    "scim_sync_endpoint",
    "jwt_private_key_path",
    "jwt_public_key_path",
    "session_store_redis_url",
    "db_host",
    "db_name",
    "db_user",
    "db_password",
    "object_store_connection_string",
    "kms_key_vault_url",
    "kms_key_name",
    "kafka_brokers",
    "kafka_topic_raw",
    "kafka_topic_canonical",
    "connector_rate_limit_per_source",
    "vault_secret_path",
    "lexical_search_url",
    "vector_search_url",
    "vector_index_name",
    "llm_provider",
    "model_version",
    "otlp_endpoint",
    "log_level",
    "metrics_namespace",
    # Compat surface used by existing modules
    "control_plane_database_url",
    "jwt_algorithm",
    "jwt_issuer",
    "jwt_active_kid",
    "environment",
]

OPTIONAL = [
    "supabase_db_url",
    "vault_url",
    "vault_tenant_id",
    "vault_client_id",
    "vault_client_secret",
    "oidc_client_id",
    "oidc_client_secret",
    "scim_token",
    "google_client_id",
    "google_client_secret",
    "microsoft_client_id",
    "microsoft_client_secret",
    "microsoft_redirect_uri",
    "microsoft_sharepoint_client_id",
    "microsoft_sharepoint_client_secret",
    "microsoft_sharepoint_tenant_id",
    "microsoft_sharepoint_redirect_uri",
    "qdrant_api_key",
    "gemini_api_key",
    "azure_openai_endpoint",
    "azure_openai_deployment",
    "azure_openai_api_key",
    "anthropic_api_key",
    "token_encryption_key",
    "openrouter_api_key",
    "qwen_model",
    "llm_chat_provider",
]


def _status(val) -> str:
    if val is None:
        return "MISSING"
    if isinstance(val, str) and not val.strip():
        return "MISSING"
    return "PRESENT"


def main() -> int:
    print(
        f"env_file_configured: "
        f"{'yes' if os.getenv('SNYQ_IGNORE_ENV_FILE') != '1' else 'ignored (SNYQ_IGNORE_ENV_FILE=1)'}"
    )
    print(f"backend_dot_env_file: {'PRESENT' if (ROOT / '.env').exists() else 'MISSING'}")
    print("--- required ---")
    missing = 0
    for key in REQUIRED:
        val = getattr(settings, key, None)
        st = _status(val)
        if st == "MISSING":
            missing += 1
        print(f"{key}: {st}")
    print("--- optional ---")
    for key in OPTIONAL:
        val = getattr(settings, key, None)
        print(f"{key}: {_status(val)}")
    priv = Path(settings.jwt_private_key_path)
    pub = Path(settings.jwt_public_key_path)
    if not priv.is_absolute():
        priv = ROOT / priv
    if not pub.is_absolute():
        pub = ROOT / pub
    local_priv = ROOT / "keys" / "private.pem"
    local_pub = ROOT / "keys" / "public.pem"
    print("--- jwt key files ---")
    print(
        f"jwt_private_key_file: {'PRESENT' if priv.is_file() or local_priv.is_file() else 'MISSING'}"
    )
    print(
        f"jwt_public_key_file: {'PRESENT' if pub.is_file() or local_pub.is_file() else 'MISSING'}"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())