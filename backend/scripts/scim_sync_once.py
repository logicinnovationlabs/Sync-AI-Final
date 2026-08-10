"""
One-shot SCIM sync process for A3 closeout.

Run as a separate OS process so each invocation is a genuine service restart
(new interpreter, new DB engine, no in-memory state).

Represents production sync behavior only: delegates to scim_sync_service.sync_users
with no tenant-reassignment side effects. Shared-DB collision cleanup belongs in
the test harness (test_signoff_closeout_local.py), not here.

Usage:
  python scripts/scim_sync_once.py --tenant-id <uuid> --fixture fixtures/okta_scim_users.json
Prints JSON: {"run":..., "principals": {"idp_subject": "principal_id", ...}}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

# Ensure backend root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SNYQ_IGNORE_ENV_FILE", "1")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    os.environ["TEST_DATABASE_URL"] = args.database_url
    os.environ["CONTROL_PLANE_DATABASE_URL"] = args.database_url

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models.base import Base
    from app.models.user import User
    from app.services.scim_sync import scim_sync_service

    fixture_path = Path(args.fixture)
    scim_users = json.loads(fixture_path.read_text(encoding="utf-8"))
    tenant_id = UUID(args.tenant_id)

    engine = create_async_engine(args.database_url, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        await scim_sync_service.sync_users(scim_users, tenant_id, session)
        subjects = [u.get("id") for u in scim_users if u.get("id")]
        result = await session.execute(
            select(User.idp_subject, User.principal_id).where(
                User.tenant_id == tenant_id,
                User.idp_subject.in_(subjects),
            )
        )
        principals = {row.idp_subject: str(row.principal_id) for row in result.all()}

    await engine.dispose()
    print(json.dumps({"principals": principals, "pid": os.getpid()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
