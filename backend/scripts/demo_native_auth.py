#!/usr/bin/env python3
"""
Example script demonstrating native authentication + Block N admin invite.

Usage:
  1. Bootstrap a tenant (one-time): POST /api/v1/admin/tenants with admin_email.
  2. Set SNYQ_ADMIN_EMAIL / SNYQ_ADMIN_PASSWORD (the bootstrap temp password,
     or the password after /me/change-password).
  3. python scripts/demo_native_auth.py
"""

import asyncio
import os
import httpx
from uuid import uuid4


BASE_URL = os.getenv("SNYQ_API_URL", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.getenv("SNYQ_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("SNYQ_ADMIN_PASSWORD", "")
TENANT_SUBDOMAIN = os.getenv("SNYQ_TENANT_SUBDOMAIN", "alpha")


async def demo_native_auth():
    print("=" * 80)
    print("NATIVE AUTHENTICATION DEMO (Block N)")
    print("=" * 80)
    print()

    email = f"demo-{uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient() as client:
        if not ADMIN_PASSWORD:
            print("Set SNYQ_ADMIN_PASSWORD to an existing Full Admin password.")
            print("Unauthenticated POST /admin/users was removed in Block N.")
            print("Bootstrap: POST /api/v1/admin/tenants with admin_email / admin_display_name.")
            return

        print("Step 1: Logging in as tenant admin...")
        login_admin = await client.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
                "tenant_subdomain": TENANT_SUBDOMAIN,
            },
        )
        if login_admin.status_code != 200:
            print(f"✗ Admin login failed: {login_admin.text}")
            return
        admin_token = login_admin.json()["access_token"]
        print("✓ Admin login successful")
        print()

        print("Step 2: Inviting a member (POST /admin/users)...")
        create_resp = await client.post(
            f"{BASE_URL}/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": email,
                "display_name": "Demo User",
                "role": "member",
            },
        )
        if create_resp.status_code >= 400:
            print(f"✗ Failed to create user: {create_resp.text}")
            return
        user = create_resp.json()
        password = user["temporary_password"]
        print(f"✓ User invited: {user['email']} (temp password returned in response)")
        print()

        print("Step 3: Member login...")
        login_payload = {
            "email": email,
            "password": password,
            "tenant_subdomain": TENANT_SUBDOMAIN,
        }
        response = await client.post(f"{BASE_URL}/auth/login", json=login_payload)
        if response.status_code != 200:
            print(f"✗ Failed to login: {response.text}")
            return
        tokens = response.json()
        access_token = tokens["access_token"]
        print(f"✓ Login successful (role={tokens.get('role')})")
        print()

        print("Step 4: GET /me...")
        response = await client.get(
            f"{BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            print(f"✗ Failed to access /me: {response.text}")
            return
        me_data = response.json()
        print(f"✓ principal_id={me_data['principal_id']} scopes={me_data['scopes']}")
        print()

        print("Step 5: Changing password...")
        new_password = "NewDemoPassword456!"
        response = await client.post(
            f"{BASE_URL}/me/change-password",
            json={"old_password": password, "new_password": new_password},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            print(f"✗ Failed to change password: {response.text}")
            return
        print(f"✓ {response.json().get('message')}")
        print()

        login_payload["password"] = new_password
        response = await client.post(f"{BASE_URL}/auth/login", json=login_payload)
        if response.status_code != 200:
            print(f"✗ Failed to login with new password: {response.text}")
            return
        print("✓ Login with new password successful")
        print()

        login_payload["password"] = password
        response = await client.post(f"{BASE_URL}/auth/login", json=login_payload)
        if response.status_code == 401:
            print("✓ Old password correctly rejected")
        else:
            print("✗ Old password still works (unexpected)")

    print()
    print("DEMO COMPLETE")


if __name__ == "__main__":
    asyncio.run(demo_native_auth())
