#!/usr/bin/env python3
"""
Example script demonstrating native authentication flow.

Usage: python scripts/demo_native_auth.py
"""

import asyncio
import httpx
from uuid import uuid4


BASE_URL = "http://localhost:8000/api/v1"


async def demo_native_auth():
    """Demonstrate native authentication flow."""
    
    print("=" * 80)
    print("NATIVE AUTHENTICATION DEMO")
    print("=" * 80)
    print()
    
    # Step 1: Create a user
    print("Step 1: Creating a new user...")
    print("-" * 80)
    
    email = f"demo-{uuid4().hex[:8]}@example.com"
    password = "DemoPassword123!"
    
    create_user_payload = {
        "tenant_subdomain": "alpha",  # Assuming 'alpha' tenant exists
        "email": email,
        "password": password,
        "display_name": "Demo User",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/admin/users",
                json=create_user_payload,
            )
            response.raise_for_status()
            user = response.json()
            
            print(f"✓ User created successfully!")
            print(f"  Email: {user['email']}")
            print(f"  Principal ID: {user['principal_id']}")
            print(f"  Tenant ID: {user['tenant_id']}")
            print()
        except httpx.HTTPStatusError as e:
            print(f"✗ Failed to create user: {e.response.text}")
            return
        except httpx.RequestError as e:
            print(f"✗ Request error: {e}")
            print("  Make sure the server is running at http://localhost:8000")
            return
        
        # Step 2: Login with email/password
        print("Step 2: Logging in with email and password...")
        print("-" * 80)
        
        login_payload = {
            "email": email,
            "password": password,
            "tenant_subdomain": "alpha",
        }
        
        try:
            response = await client.post(
                f"{BASE_URL}/auth/login",
                json=login_payload,
            )
            response.raise_for_status()
            tokens = response.json()
            
            print(f"✓ Login successful!")
            print(f"  Access Token: {tokens['access_token'][:50]}...")
            print(f"  Token Type: {tokens['token_type']}")
            print(f"  Expires In: {tokens['expires_in']} seconds")
            print()
            
            access_token = tokens["access_token"]
        except httpx.HTTPStatusError as e:
            print(f"✗ Failed to login: {e.response.text}")
            return
        
        # Step 3: Access protected endpoint
        print("Step 3: Accessing protected endpoint (/me)...")
        print("-" * 80)
        
        try:
            response = await client.get(
                f"{BASE_URL}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            me_data = response.json()
            
            print(f"✓ Successfully retrieved user info!")
            print(f"  Principal ID: {me_data['principal_id']}")
            print(f"  Tenant ID: {me_data['tenant_id']}")
            print(f"  Scopes: {me_data['scopes']}")
            print()
        except httpx.HTTPStatusError as e:
            print(f"✗ Failed to access /me: {e.response.text}")
            return
        
        # Step 4: Change password
        print("Step 4: Changing password...")
        print("-" * 80)
        
        new_password = "NewDemoPassword456!"
        change_password_payload = {
            "old_password": password,
            "new_password": new_password,
        }
        
        try:
            response = await client.post(
                f"{BASE_URL}/me/change-password",
                json=change_password_payload,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"✓ {result['message']}")
            print()
        except httpx.HTTPStatusError as e:
            print(f"✗ Failed to change password: {e.response.text}")
            return
        
        # Step 5: Login with new password
        print("Step 5: Logging in with new password...")
        print("-" * 80)
        
        login_payload["password"] = new_password
        
        try:
            response = await client.post(
                f"{BASE_URL}/auth/login",
                json=login_payload,
            )
            response.raise_for_status()
            tokens = response.json()
            
            print(f"✓ Login with new password successful!")
            print(f"  Access Token: {tokens['access_token'][:50]}...")
            print()
        except httpx.HTTPStatusError as e:
            print(f"✗ Failed to login with new password: {e.response.text}")
            return
        
        # Step 6: Verify old password no longer works
        print("Step 6: Verifying old password no longer works...")
        print("-" * 80)
        
        login_payload["password"] = password  # Old password
        
        try:
            response = await client.post(
                f"{BASE_URL}/auth/login",
                json=login_payload,
            )
            response.raise_for_status()
            print(f"✗ Old password still works (unexpected!)")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print(f"✓ Old password correctly rejected")
                print()
            else:
                print(f"✗ Unexpected error: {e.response.text}")
    
    print("=" * 80)
    print("DEMO COMPLETE!")
    print("=" * 80)
    print()
    print("Summary:")
    print("  - Created a new user with email/password")
    print("  - Logged in and received JWT tokens")
    print("  - Accessed a protected endpoint")
    print("  - Changed the password")
    print("  - Verified new password works and old password is rejected")
    print()
    print("See NATIVE_AUTH.md for detailed documentation.")


if __name__ == "__main__":
    asyncio.run(demo_native_auth())
