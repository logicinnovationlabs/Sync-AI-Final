"""
Unit tests for native authentication service.
"""

import pytest
from uuid import uuid4

from app.services.native_auth import native_auth_service
from app.core.exceptions import UnauthorizedError


@pytest.mark.asyncio
async def test_hash_and_verify_password():
    """Test password hashing and verification."""
    password = "SecurePassword123!"
    
    # Hash password
    password_hash = native_auth_service.hash_password(password)
    
    assert password_hash is not None
    assert len(password_hash) > 0
    assert password_hash != password  # Hashed, not plain text
    
    # Verify correct password
    assert native_auth_service.verify_password(password, password_hash)
    
    # Verify incorrect password
    assert not native_auth_service.verify_password("WrongPassword", password_hash)


@pytest.mark.asyncio
async def test_create_native_user(test_db):
    """Test creating a native auth user."""
    tenant_id = uuid4()
    
    user = await native_auth_service.create_native_user(
        email="test@example.com",
        password="SecurePass123!",
        display_name="Test User",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    assert user.email == "test@example.com"
    assert user.display_name == "Test User"
    assert user.password_hash is not None
    assert user.idp_subject.startswith("native:")
    assert user.source_profiles["auth_type"] == "native"
    assert user.status == "active"


@pytest.mark.asyncio
async def test_create_duplicate_user_fails(test_db):
    """Test that creating a user with duplicate email fails."""
    tenant_id = uuid4()
    
    # Create first user
    await native_auth_service.create_native_user(
        email="duplicate@example.com",
        password="Pass123!",
        display_name="User One",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    # Try to create second user with same email
    with pytest.raises(ValueError, match="already exists"):
        await native_auth_service.create_native_user(
            email="duplicate@example.com",
            password="Pass456!",
            display_name="User Two",
            tenant_id=tenant_id,
            db_session=test_db,
        )


@pytest.mark.asyncio
async def test_authenticate_user_success(test_db):
    """Test successful user authentication."""
    tenant_id = uuid4()
    password = "SecurePass123!"
    
    # Create user
    await native_auth_service.create_native_user(
        email="auth@example.com",
        password=password,
        display_name="Auth User",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    # Authenticate with correct credentials
    user = await native_auth_service.authenticate_user(
        email="auth@example.com",
        password=password,
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    assert user is not None
    assert user.email == "auth@example.com"


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(test_db):
    """Test authentication fails with wrong password."""
    tenant_id = uuid4()
    
    # Create user
    await native_auth_service.create_native_user(
        email="wrongpass@example.com",
        password="CorrectPass123!",
        display_name="Wrong Pass User",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    # Try to authenticate with wrong password
    with pytest.raises(UnauthorizedError, match="Invalid email or password"):
        await native_auth_service.authenticate_user(
            email="wrongpass@example.com",
            password="WrongPassword",
            tenant_id=tenant_id,
            db_session=test_db,
        )


@pytest.mark.asyncio
async def test_authenticate_nonexistent_user(test_db):
    """Test authentication fails for non-existent user."""
    tenant_id = uuid4()
    
    with pytest.raises(UnauthorizedError, match="Invalid email or password"):
        await native_auth_service.authenticate_user(
            email="nonexistent@example.com",
            password="SomePassword",
            tenant_id=tenant_id,
            db_session=test_db,
        )


@pytest.mark.asyncio
async def test_change_password_success(test_db):
    """Test successful password change."""
    tenant_id = uuid4()
    old_password = "OldPass123!"
    new_password = "NewPass456!"
    
    # Create user
    user = await native_auth_service.create_native_user(
        email="changepass@example.com",
        password=old_password,
        display_name="Change Pass User",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    # Change password
    await native_auth_service.change_password(
        user_id=user.principal_id,
        old_password=old_password,
        new_password=new_password,
        db_session=test_db,
    )
    
    # Verify can authenticate with new password
    authenticated_user = await native_auth_service.authenticate_user(
        email="changepass@example.com",
        password=new_password,
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    assert authenticated_user.principal_id == user.principal_id
    
    # Verify old password no longer works
    with pytest.raises(UnauthorizedError):
        await native_auth_service.authenticate_user(
            email="changepass@example.com",
            password=old_password,
            tenant_id=tenant_id,
            db_session=test_db,
        )


@pytest.mark.asyncio
async def test_change_password_wrong_old_password(test_db):
    """Test password change fails with wrong old password."""
    tenant_id = uuid4()
    
    # Create user
    user = await native_auth_service.create_native_user(
        email="wrongold@example.com",
        password="CorrectPass123!",
        display_name="Wrong Old User",
        tenant_id=tenant_id,
        db_session=test_db,
    )
    
    # Try to change password with wrong old password
    with pytest.raises(UnauthorizedError, match="Current password is incorrect"):
        await native_auth_service.change_password(
            user_id=user.principal_id,
            old_password="WrongOldPassword",
            new_password="NewPass456!",
            db_session=test_db,
        )
