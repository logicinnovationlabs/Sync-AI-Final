"""Postgres URL helpers for Render (IPv4) vs local Docker."""

from app.storage.pg_connect import (
    connect_args_for_url,
    prepare_database_url,
    to_asyncpg_url,
)


def test_localhost_rewritten_to_ipv4():
    url = prepare_database_url(
        "postgresql+asyncpg://postgres:pw@localhost:5432/control_plane"
    )
    assert "@127.0.0.1:5432/" in url
    assert connect_args_for_url(url)["ssl"] is False


def test_postgres_scheme_normalized():
    assert to_asyncpg_url("postgres://u:p@h:5432/db").startswith("postgresql+asyncpg://")


def test_direct_supabase_swapped_for_pooler():
    direct = "postgresql://postgres:secret@db.abcdefghijkl.supabase.co:5432/postgres"
    pooler = (
        "postgresql://postgres.abcdefghijkl:secret"
        "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )
    url = prepare_database_url(direct, pooler_url=pooler)
    assert "pooler.supabase.com" in url
    assert "db.abcdefghijkl.supabase.co" not in url
    assert connect_args_for_url(url)["ssl"] is True
    assert connect_args_for_url(url)["statement_cache_size"] == 0
