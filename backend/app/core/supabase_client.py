"""Supabase client utilities for VERITAS AI.

Provides admin and user-scoped clients, JWT validation, and token management.
"""

import time
import logging
from typing import Optional, Dict, Any
from functools import lru_cache

import httpx
from jose import jwt, JWTError
from jose.utils import base64url_decode
from supabase import create_client, Client
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


# Cache for JWKS (JSON Web Key Set) - refreshes every hour
_jwks_cache: Dict[str, Any] = {"keys": {}, "expires_at": 0}


async def _fetch_jwks() -> Dict[str, Any]:
    """Fetch JWKS from Supabase for JWT verification."""
    global _jwks_cache

    # Check cache
    if _jwks_cache["expires_at"] > time.time() and _jwks_cache["keys"]:
        return _jwks_cache["keys"]

    jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            jwks = resp.json()

        # Cache for 1 hour
        _jwks_cache["keys"] = jwks
        _jwks_cache["expires_at"] = time.time() + 3600
        return jwks
    except Exception as e:
        logger.warning(f"Failed to fetch JWKS: {e}")
        return _jwks_cache["keys"]  # Return cached keys if available


def _construct_rsa_key(jwk: Dict[str, Any]) -> Any:
    """Construct RSA public key from JWK."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    e = base64url_decode(jwk["e"].encode())
    n = base64url_decode(jwk["n"].encode())

    public_numbers = rsa.RSAPublicNumbers(
        e=int.from_bytes(e, "big"),
        n=int.from_bytes(n, "big")
    )
    return public_numbers.public_key()


async def validate_jwt_locally(access_token: str) -> Dict[str, Any]:
    """Validate JWT token locally using Supabase JWKS.

    This avoids a network round-trip to Supabase Auth for token validation.
    Returns the decoded claims if valid.

    Raises:
        HTTPException: If token is invalid, expired, or malformed.
    """
    if not access_token or not access_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token"
        )

    try:
        # Get JWKS
        jwks = await _fetch_jwks()
        if not jwks:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to fetch signing keys"
            )

        # Decode header to get key ID
        unverified_header = jwt.get_unverified_header(access_token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")

        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing key ID"
            )

        # Support only RS256 for Supabase
        if alg != "RS256":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unsupported algorithm: {alg}. Expected RS256."
            )

        # Find matching key
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break

        if not key:
            # Try to refresh JWKS once
            _jwks_cache["expires_at"] = 0
            jwks = await _fetch_jwks()
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break

        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find matching signing key"
            )

        # Construct RSA public key from JWK
        rsa_key = _construct_rsa_key(key)

        # Decode and verify token
        claims = jwt.decode(
            access_token,
            rsa_key,
            algorithms=["RS256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1",
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True}
        )

        return claims

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token"
        )


async def validate_access_token(access_token: str) -> dict:
    """Validate access token with Supabase Auth and return user data.

    First tries local JWT validation (fast, no network call).
    Falls back to Supabase Auth API if local validation fails.

    Raises:
        HTTPException: If token is invalid, expired, or user not found.
    """
    # Try local JWT validation first
    try:
        claims = await validate_jwt_locally(access_token)
        return {
            "id": claims.get("sub"),
            "email": claims.get("email"),
            "access_token": access_token,
            "claims": claims
        }
    except HTTPException:
        # Fall back to Supabase Auth API
        pass

    try:
        # Create a temporary client with the user's access token
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        client.auth.set_session(access_token, "")

        # Validate token by getting user info from Supabase Auth
        user_response = client.auth.get_user(access_token)

        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token"
            )

        return {
            "id": user_response.user.id,
            "email": user_response.user.email,
            "access_token": access_token
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token"
        )


def get_supabase_admin() -> Client:
    """Get Supabase client with service role key for admin operations.

    This client bypasses RLS policies. Use only for backend operations
    that need elevated privileges (e.g., document processing pipeline).
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


async def get_supabase_user(access_token: str) -> Client:
    """Get Supabase client authenticated as a specific user.

    This client enforces RLS policies. Use for frontend-facing operations
    where the user's permissions should be respected.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, "")
    return client


def get_user_client(access_token: str) -> Client:
    """Get Supabase client with user's access token (for RLS enforcement).

    Synchronous version for use in non-async contexts.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, "")
    return client


async def verify_document_ownership(document_id: str, user_id: str, admin: Client) -> bool:
    """Verify that a document belongs to a user.

    Args:
        document_id: The document UUID
        user_id: The user UUID
        admin: Admin Supabase client

    Returns:
        True if document belongs to user, False otherwise.
    """
    try:
        result = admin.from_("documents").select("user_id").eq("id", document_id).maybe_single().execute()
        if not result.data:
            return False
        return str(result.data["user_id"]) == str(user_id)
    except Exception as e:
        logger.warning(f"Document ownership verification failed: {e}")
        return False


async def verify_user_owns_document(document_id: str, access_token: str) -> str:
    """Verify user owns document and return user_id.

    Uses user-scoped client to enforce RLS.

    Raises:
        HTTPException: If document not found or access denied.
    """
    user_data = await validate_access_token(access_token)
    user_client = get_user_client(access_token)

    result = user_client.from_("documents").select("user_id").eq("id", document_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    return result.data["user_id"]


def clear_jwks_cache():
    """Clear the JWKS cache (useful for testing or forced refresh)."""
    global _jwks_cache
    _jwks_cache = {"keys": {}, "expires_at": 0}