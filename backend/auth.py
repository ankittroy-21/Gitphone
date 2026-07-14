"""
auth.py - API Key authentication middleware for GitPhone backend.

Every request from the VS Code extension must include:
    X-API-Key: <secret_key>

The key is generated at registration, stored as a SHA-256 hash in Supabase,
and given to the extension once. It never travels over the wire again.

Endpoints that require auth:
  POST /sync-file
  GET  /staged-files/{telegram_id}
  DELETE /staged-files/{file_id}

Public endpoints (no auth needed):
  POST /register    \u2190 generates the key
  GET  /health
  GET  /version
  POST /webhook     \u2190 Telegram webhook (validated by python-telegram-bot)
"""

import hashlib
import secrets

from fastapi import Header, HTTPException
from supabase_service import get_client


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.
    Returns (raw_key, hashed_key).
    raw_key is given to the client once and never stored.
    hashed_key is stored in Supabase.
    """
    raw = secrets.token_urlsafe(32)          # 256-bit random, URL-safe
    hashed = _hash_key(raw)
    return raw, hashed


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of the raw key. This is what we store."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(telegram_id: str, raw_key: str) -> bool:
    """
    Check that the provided raw_key matches the stored hash for this user.
    Returns True if valid.
    """
    try:
        db = get_client()
        result = db.table("users") \
            .select("api_key_hash") \
            .eq("telegram_id", telegram_id) \
            .execute()
        if not result.data:
            return False
        stored_hash = result.data[0].get("api_key_hash")
        if not stored_hash:
            return False
        return _hash_key(raw_key) == stored_hash
    except Exception as e:
        print(f"[auth] verify_api_key error: {e}")
        return False


async def require_api_key(
    x_telegram_id: str = Header(..., description="Your Telegram numeric ID"),
    x_api_key: str = Header(..., description="Your GitPhone API key"),
) -> str:
    """
    FastAPI dependency - validates X-Telegram-Id + X-Api-Key headers.
    Raises 401 if invalid. Returns telegram_id on success.

    Usage:
        @router.get("/protected")
        async def endpoint(telegram_id: str = Depends(require_api_key)):
            ...
    """
    if not x_telegram_id or not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Telegram-Id or X-Api-Key headers."
        )

    if not verify_api_key(x_telegram_id, x_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Re-connect GitPhone in VS Code."
        )

    return x_telegram_id
