"""Tests for Supabase client utilities."""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables BEFORE importing app
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'test-anon-key'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'test-service-role-key'
os.environ['GEMINI_API_KEY'] = 'test-gemini-key'
os.environ['ANTHROPIC_API_KEY'] = 'test-anthropic-key'

from app.core.supabase_client import (
    get_supabase_admin,
    get_supabase_user,
    get_user_client,
    validate_access_token,
    verify_user_owns_document,
    clear_jwks_cache,
)
from app.core.config import settings


class TestSupabaseClient:
    """Test Supabase client utilities."""

    def test_get_supabase_admin(self):
        """Test admin client creation."""
        with patch('app.core.supabase_client.create_client') as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            client = get_supabase_admin()

            mock_create.assert_called_once_with(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            assert client == mock_client

    def test_get_user_client(self):
        """Test user client creation."""
        with patch('app.core.supabase_client.create_client') as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            client = get_user_client("test-token")

            mock_create.assert_called_once_with(
                settings.SUPABASE_URL,
                settings.SUPABASE_ANON_KEY
            )
            mock_client.auth.set_session.assert_called_once_with("test-token", "")
            assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_supabase_user(self):
        """Test async user client creation."""
        with patch('app.core.supabase_client.create_client') as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            client = await get_supabase_user("test-token")

            mock_create.assert_called_once_with(
                settings.SUPABASE_URL,
                settings.SUPABASE_ANON_KEY
            )
            mock_client.auth.set_session.assert_called_once_with("test-token", "")
            assert client == mock_client


class TestValidateAccessToken:
    """Test access token validation."""

    def setup_method(self):
        clear_jwks_cache()

    @pytest.mark.asyncio
    async def test_validate_access_token_missing(self):
        """Test validation fails for missing token."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await validate_access_token("")

        assert exc_info.value.status_code == 401
        assert "Missing access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_validate_access_token_whitespace(self):
        """Test validation fails for whitespace-only token."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await validate_access_token("   ")

        assert exc_info.value.status_code == 401
        assert "Missing access token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_validate_access_token_jwt_success(self):
        """Test successful local JWT validation."""
        # Create a mock JWT with proper structure
        import jwt as pyjwt
        from jose import jwt as jose_jwt

        # We'll mock the JWKS fetch and jwt.decode
        with patch('app.core.supabase_client._fetch_jwks') as mock_jwks:
            mock_jwks.return_value = {
                "keys": [{
                    "kid": "test-key-id",
                    "kty": "RSA",
                    "n": "test-modulus",
                    "e": "AQAB"
                }]
            }

            with patch('jose.jwt.decode') as mock_decode:
                mock_decode.return_value = {
                    "sub": "user-123",
                    "email": "test@example.com",
                    "aud": "authenticated",
                    "iss": "https://test.supabase.co/auth/v1"
                }

                with patch('jose.jwt.get_unverified_header') as mock_header:
                    mock_header.return_value = {"kid": "test-key-id"}

                    result = await validate_access_token("valid-jwt-token")

                    assert result["id"] == "user-123"
                    assert result["email"] == "test@example.com"
                    assert result["access_token"] == "valid-jwt-token"
                    assert "claims" in result

    @pytest.mark.asyncio
    async def test_validate_access_token_jwt_fallback(self):
        """Test fallback to Supabase Auth API when JWT validation fails."""
        from fastapi import HTTPException

        with patch('app.core.supabase_client._fetch_jwks') as mock_jwks:
            mock_jwks.return_value = {"keys": []}  # No matching key

            with patch('app.core.supabase_client.create_client') as mock_create:
                mock_client = MagicMock()
                mock_create.return_value = mock_client

                mock_user_response = MagicMock()
                mock_user_response.user = MagicMock()
                mock_user_response.user.id = "user-456"
                mock_user_response.user.email = "fallback@example.com"
                mock_client.auth.get_user = AsyncMock(return_value=mock_user_response)

                result = await validate_access_token("valid-jwt-token")

                assert result["id"] == "user-456"
                assert result["email"] == "fallback@example.com"

    @pytest.mark.asyncio
    async def test_validate_access_token_supabase_failure(self):
        """Test failure when both JWT and Supabase validation fail."""
        from fastapi import HTTPException

        with patch('app.core.supabase_client._fetch_jwks') as mock_jwks:
            mock_jwks.return_value = {"keys": []}

            with patch('app.core.supabase_client.create_client') as mock_create:
                mock_client = MagicMock()
                mock_create.return_value = mock_client
                mock_client.auth.get_user = AsyncMock(side_effect=Exception("Auth error"))

                with pytest.raises(HTTPException) as exc_info:
                    await validate_access_token("invalid-token")

                assert exc_info.value.status_code == 401
                assert "Invalid access token" in exc_info.value.detail


class TestVerifyUserOwnsDocument:
    """Test document ownership verification."""

    @pytest.mark.asyncio
    async def test_verify_user_owns_document_success(self):
        """Test successful ownership verification."""
        with patch('app.core.supabase_client.validate_access_token') as mock_validate:
            mock_validate.return_value = {
                "id": "user-123",
                "email": "test@example.com",
                "access_token": "test-token"
            }

            with patch('app.core.supabase_client.get_user_client') as mock_get_client:
                mock_client = MagicMock()
                mock_get_client.return_value = mock_client

                mock_result = MagicMock()
                mock_result.data = {"user_id": "user-123"}
                mock_client.from_.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

                user_id = await verify_user_owns_document("doc-123", "test-token")

                assert user_id == "user-123"

    @pytest.mark.asyncio
    async def test_verify_user_owns_document_not_found(self):
        """Test ownership verification fails when document not found."""
        from fastapi import HTTPException

        with patch('app.core.supabase_client.validate_access_token') as mock_validate:
            mock_validate.return_value = {
                "id": "user-123",
                "email": "test@example.com",
                "access_token": "test-token"
            }

            with patch('app.core.supabase_client.get_user_client') as mock_get_client:
                mock_client = MagicMock()
                mock_get_client.return_value = mock_client

                mock_result = MagicMock()
                mock_result.data = None
                mock_client.from_.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

                with pytest.raises(HTTPException) as exc_info:
                    await verify_user_owns_document("doc-123", "test-token")

                assert exc_info.value.status_code == 404
                assert "Document not found or access denied" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_user_owns_document_wrong_user(self):
        """Test ownership verification fails when document belongs to different user."""
        from fastapi import HTTPException

        with patch('app.core.supabase_client.validate_access_token') as mock_validate:
            mock_validate.return_value = {
                "id": "user-123",
                "email": "test@example.com",
                "access_token": "test-token"
            }

            with patch('app.core.supabase_client.get_user_client') as mock_get_client:
                mock_client = MagicMock()
                mock_get_client.return_value = mock_client

                mock_result = MagicMock()
                mock_result.data = {"user_id": "user-456"}  # Different user
                mock_client.from_.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = mock_result

                with pytest.raises(HTTPException) as exc_info:
                    await verify_user_owns_document("doc-123", "test-token")

                assert exc_info.value.status_code == 404


class TestJWKSCache:
    """Test JWKS caching behavior."""

    def setup_method(self):
        clear_jwks_cache()

    def test_clear_jwks_cache(self):
        """Test cache clearing."""
        from app.core.supabase_client import _jwks_cache

        # Add something to cache
        _jwks_cache["keys"] = {"test": "data"}
        _jwks_cache["expires_at"] = 9999999999

        clear_jwks_cache()

        assert _jwks_cache["keys"] == {}
        assert _jwks_cache["expires_at"] == 0