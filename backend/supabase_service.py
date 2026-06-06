"""
supabase_service.py — All Supabase reads/writes for the MVP.
Uses ONE central Supabase (ours). Users isolated by telegram_id.
"""

import os
from typing import Optional
from supabase import create_client, Client

# ── Client Initialization ────────────────────────────────────────────────────
_supabase: Optional[Client] = None


def get_client() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ["YOUR_SUPABASE_URL"]
        key = os.environ["YOUR_SUPABASE_KEY"]
        _supabase = create_client(url, key)
    return _supabase


# ── User Operations ──────────────────────────────────────────────────────────

def get_user_by_telegram_id(telegram_id: str) -> Optional[dict]:
    """Returns user row or None if not registered."""
    try:
        result = get_client().table("users") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[supabase] get_user_by_telegram_id error: {e}")
        return None


def upsert_user(user: dict) -> Optional[dict]:
    """Insert or update user by telegram_id. Returns saved row."""
    try:
        result = get_client().table("users") \
            .upsert(user, on_conflict="telegram_id") \
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[supabase] upsert_user error: {e}")
        return None


def update_last_active(telegram_id: str) -> None:
    """Touch last_active timestamp for keepalive tracking."""
    try:
        get_client().table("users") \
            .update({"last_active": "now()"}) \
            .eq("telegram_id", telegram_id) \
            .execute()
    except Exception as e:
        print(f"[supabase] update_last_active error: {e}")


# ── Staged Files Operations ──────────────────────────────────────────────────

def upsert_staged_file(payload: dict) -> Optional[dict]:
    """
    Upsert a staged file diff.
    If an existing pending diff exists for the same (telegram_id, filepath) → update it.
    Otherwise → insert new.
    Returns the saved row.
    """
    try:
        db = get_client()
        telegram_id = payload["telegram_id"]
        filepath = payload["filepath"]

        # Check for existing pending diff for this file
        existing = db.table("staged_files") \
            .select("id") \
            .eq("telegram_id", telegram_id) \
            .eq("filepath", filepath) \
            .eq("status", "pending") \
            .execute()

        if existing.data:
            # Update existing row
            result = db.table("staged_files") \
                .update({
                    "diff": payload.get("diff"),
                    "full_content": payload.get("full_content"),
                    "base_sha": payload["base_sha"],
                    "is_binary": payload.get("is_binary", False),
                    "file_size": payload.get("file_size", 0),
                    "updated_at": "now()",
                }) \
                .eq("id", existing.data[0]["id"]) \
                .execute()
        else:
            # Insert new row
            result = db.table("staged_files") \
                .insert(payload) \
                .execute()

        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[supabase] upsert_staged_file error: {e}")
        return None


def get_pending_files(telegram_id: str) -> list[dict]:
    """Returns all pending staged files for a user, oldest first."""
    try:
        result = get_client().table("staged_files") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .eq("status", "pending") \
            .order("staged_at", desc=False) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_pending_files error: {e}")
        return []


def get_staged_files_by_ids(file_ids: list[str]) -> list[dict]:
    """Fetch specific staged file rows by UUID list."""
    try:
        result = get_client().table("staged_files") \
            .select("*") \
            .in_("id", file_ids) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_staged_files_by_ids error: {e}")
        return []


def mark_files_committed(file_ids: list[str]) -> None:
    """Mark staged files as committed after a successful GitHub push."""
    try:
        get_client().table("staged_files") \
            .update({"status": "committed"}) \
            .in_("id", file_ids) \
            .execute()
    except Exception as e:
        print(f"[supabase] mark_files_committed error: {e}")


# ── Commit Log ───────────────────────────────────────────────────────────────

def insert_commit_log(log: dict) -> None:
    """Record a successful commit in the audit log."""
    try:
        get_client().table("commit_log") \
            .insert(log) \
            .execute()
    except Exception as e:
        print(f"[supabase] insert_commit_log error: {e}")


def get_recent_commits(telegram_id: str, limit: int = 10) -> list[dict]:
    """Returns the last N commits for a user, newest first."""
    try:
        result = get_client().table("commit_log") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .order("committed_at", desc=True) \
            .limit(limit) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_recent_commits error: {e}")
        return []
