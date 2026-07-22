"""
supabase_service.py - All Supabase reads/writes for the MVP.
Uses ONE central Supabase (ours). Users isolated by telegram_id.
"""

import os

import jwt
from supabase import Client, ClientOptions, create_client

# --- Client Initialization ------------------------------------------------------------------------------
_supabase: Client | None = None


def get_client(telegram_id: str | None = None) -> Client:
    """
    Returns a Supabase client.
    If telegram_id is provided, returns a client authenticated with a custom JWT for RLS.
    Otherwise, returns the global service_role client.
    """
    url = os.environ["SUPABASE_URL"]

    if telegram_id:
        jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
        if jwt_secret:
            payload = {
                "role": "authenticated",
                "sub": telegram_id,
            }
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            return create_client(
                url,
                os.environ["SUPABASE_KEY"],
                options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
            )
        else:
            print("[supabase] WARNING: SUPABASE_JWT_SECRET not found, falling back to service_role client")

    # Global service_role client
    global _supabase
    if _supabase is None:
        key = os.environ["SUPABASE_KEY"]
        _supabase = create_client(url, key)
    return _supabase


# --- User Operations ---------------------------------------------------------------------------------------

def get_user_by_telegram_id(telegram_id: str) -> dict | None:
    """Returns user row or None if not registered."""
    try:
        result = get_client(telegram_id).table("users") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[supabase] get_user_by_telegram_id error: {e}")
        return None


def upsert_user(user: dict) -> dict | None:
    """Insert or update user by telegram_id. Returns saved row."""
    try:
        telegram_id = user.get("telegram_id")
        result = get_client(telegram_id).table("users") \
            .upsert(user, on_conflict="telegram_id") \
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[supabase] upsert_user error: {e}")
        return None


def update_last_active(telegram_id: str) -> None:
    """Touch last_active timestamp for keepalive tracking."""
    try:
        get_client(telegram_id).table("users") \
            .update({"last_active": "now()"}) \
            .eq("telegram_id", telegram_id) \
            .execute()
    except Exception as e:
        print(f"[supabase] update_last_active error: {e}")


# --- Staged Files Operations ---------------------------------------------------------------------------

def upsert_staged_file(payload: dict) -> dict | None:
    """
    Upsert a staged file diff.
    If an existing pending diff exists for the same (telegram_id, filepath) \u2192 update it.
    Otherwise \u2192 insert new.
    Returns the saved row.
    """
    try:
        telegram_id = payload["telegram_id"]
        db = get_client(telegram_id)
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
        result = get_client(telegram_id).table("staged_files") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .eq("status", "pending") \
            .order("staged_at", desc=False) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_pending_files error: {e}")
        return []



# --- Commit Log ----------------------------------------------------------------------------------------------

def insert_commit_log(log: dict) -> None:
    """Record a successful commit in the audit log."""
    try:
        telegram_id = log.get("telegram_id")
        get_client(telegram_id).table("commit_log") \
            .insert(log) \
            .execute()
    except Exception as e:
        print(f"[supabase] insert_commit_log error: {e}")


def get_recent_commits(telegram_id: str, limit: int = 10) -> list[dict]:
    """Returns the last N commits for a user, newest first."""
    try:
        result = get_client(telegram_id).table("commit_log") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .order("committed_at", desc=True) \
            .limit(limit) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_recent_commits error: {e}")
        return []


# --- Active Repo Tracking -------------------------------------------------------------------------------

def update_active_repo(telegram_id: str, active_repo: str, active_branch: str) -> None:
    """Update the user's currently active repo/branch (auto-detected from VS Code)."""
    try:
        get_client(telegram_id).table("users") \
            .update({"active_repo": active_repo, "active_branch": active_branch}) \
            .eq("telegram_id", telegram_id) \
            .execute()
    except Exception as e:
        print(f"[supabase] update_active_repo error: {e}")


def update_branch(telegram_id: str, branch: str) -> None:
    """Update a user's active branch manually (from /branch command)."""
    try:
        get_client(telegram_id).table("users") \
            .update({"active_branch": branch, "branch": branch}) \
            .eq("telegram_id", telegram_id) \
            .execute()
    except Exception as e:
        print(f"[supabase] update_branch error: {e}")


def get_pending_files_by_repo(telegram_id: str) -> dict[str, list[dict]]:
    """
    Returns pending staged files grouped by repo.
    { "owner/repo": [file, file], "other/repo": [file] }
    Files with no repo go under the user's active_repo or default_repo.
    """
    try:
        user = get_user_by_telegram_id(telegram_id)
        fallback_repo = (user or {}).get("active_repo") or (user or {}).get("default_repo", "unknown")

        result = get_client(telegram_id).table("staged_files") \
            .select("*") \
            .eq("telegram_id", telegram_id) \
            .eq("status", "pending") \
            .order("staged_at", desc=False) \
            .execute()

        files = result.data or []
        grouped: dict[str, list[dict]] = {}
        for f in files:
            repo = f.get("repo") or fallback_repo
            grouped.setdefault(repo, []).append(f)
        return grouped
    except Exception as e:
        print(f"[supabase] get_pending_files_by_repo error: {e}")
        return {}


def unstage_file_by_path(telegram_id: str, filepath: str) -> bool:
    """Remove a specific pending staged file by filepath. Returns True if found."""
    try:
        db = get_client(telegram_id)
        result = db.table("staged_files") \
            .select("id") \
            .eq("telegram_id", telegram_id) \
            .eq("filepath", filepath) \
            .eq("status", "pending") \
            .execute()
        if not result.data:
            return False
        for row in result.data:
            db.table("staged_files").update({"status": "cancelled"}).eq("id", row["id"]).execute()
        return True
    except Exception as e:
        print(f"[supabase] unstage_file_by_path error: {e}")
        return False


def clear_all_staged(telegram_id: str) -> int:
    """Cancel all pending staged files for a user. Returns count cleared."""
    try:
        db = get_client(telegram_id)
        result = db.table("staged_files") \
            .select("id") \
            .eq("telegram_id", telegram_id) \
            .eq("status", "pending") \
            .execute()
        count = len(result.data or [])
        if count:
            ids = [r["id"] for r in result.data]
            db.table("staged_files").update({"status": "cancelled"}).in_("id", ids).execute()
        return count
    except Exception as e:
        print(f"[supabase] clear_all_staged error: {e}")
        return 0


def sync_pending_state(telegram_id: str, current_filepaths: list[str]) -> int:
    """
    State Reconciliation:
    Marks any 'pending' file as 'committed' if its path is NOT in current_filepaths.
    Returns the count of files synchronized.
    """
    try:
        db = get_client(telegram_id)
        # 1. Get all pending files for this user
        result = db.table("staged_files") \
            .select("id, filepath") \
            .eq("telegram_id", telegram_id) \
            .eq("status", "pending") \
            .execute()

        if not result.data:
            return 0

        # 2. Identify files that are no longer dirty in VS Code
        to_mark_committed = []
        for row in result.data:
            if row["filepath"] not in current_filepaths:
                to_mark_committed.append(row["id"])

        # 3. Batch update them to 'committed'
        if to_mark_committed:
            db.table("staged_files") \
                .update({"status": "committed"}) \
                .in_("id", to_mark_committed) \
                .execute()
            return len(to_mark_committed)

        return 0
    except Exception as e:
        print(f"[supabase] sync_pending_state error: {e}")
        return 0


# --- Admin Operations -------------------------------------------------------------------------------------

def ban_user(telegram_id: str, reason: str = "") -> bool:
    """Ban a user by telegram_id. Returns True if user existed."""
    try:
        result = get_client().table("users") \
            .update({"status": "banned", "ban_reason": reason}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return bool(result.data)
    except Exception as e:
        print(f"[supabase] ban_user error: {e}")
        return False


def unban_user(telegram_id: str) -> bool:
    """Restore a banned user. Returns True if user existed."""
    try:
        result = get_client().table("users") \
            .update({"status": "active", "ban_reason": None}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return bool(result.data)
    except Exception as e:
        print(f"[supabase] unban_user error: {e}")
        return False


def revoke_api_key(telegram_id: str) -> bool:
    """Clear the API key hash forcing user to re-connect the extension."""
    try:
        result = get_client().table("users") \
            .update({"api_key_hash": None}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return bool(result.data)
    except Exception as e:
        print(f"[supabase] revoke_api_key error: {e}")
        return False


def get_all_users(limit: int = 50, offset: int = 0) -> list[dict]:
    """Returns paginated list of all users (admin only)."""
    try:
        result = get_client().table("users") \
            .select("telegram_id, default_repo, active_repo, branch, status, last_active, created_at") \
            .order("last_active", desc=True) \
            .range(offset, offset + limit - 1) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_all_users error: {e}")
        return []


def count_stats() -> dict:
    """Returns global platform statistics."""
    try:
        db = get_client()
        users = db.table("users").select("id, status", count="exact").execute()
        staged = db.table("staged_files").select("id, status", count="exact").eq("status", "pending").execute()
        commits = db.table("commit_log").select("id", count="exact").execute()
        banned = sum(1 for u in (users.data or []) if u.get("status") == "banned")
        return {
            "total_users": users.count or 0,
            "banned_users": banned,
            "pending_files": staged.count or 0,
            "total_commits": commits.count or 0,
        }
    except Exception as e:
        print(f"[supabase] count_stats error: {e}")
        return {}


def get_staged_files_by_ids(file_ids: list[str]) -> list[dict]:
    """Fetch specific staged files by their UUIDs (for direct commit)."""
    if not file_ids:
        return []
    try:
        result = get_client().table("staged_files") \
            .select("*") \
            .in_("id", file_ids) \
            .eq("status", "pending") \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[supabase] get_staged_files_by_ids error: {e}")
        return []


def mark_files_committed(file_ids: list[str]) -> bool:
    """Mark staged files as committed after a direct commit succeeds."""
    if not file_ids:
        return True
    try:
        get_client().table("staged_files") \
            .update({"status": "committed"}) \
            .in_("id", file_ids) \
            .execute()
        return True
    except Exception as e:
        print(f"[supabase] mark_files_committed error: {e}")
        return False


# --- Device Flow OAuth State ----------------------------------------------------------------------------

def save_device_flow_state(telegram_id: str, state: dict) -> bool:
    """Store GitHub Device Flow state (device_code, expires_at) in users table."""
    try:
        import json
        get_client(telegram_id).table("users") \
            .update({"device_flow_state": json.dumps(state)}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return True
    except Exception as e:
        print(f"[supabase] save_device_flow_state error: {e}")
        return False


def get_device_flow_state(telegram_id: str) -> dict | None:
    """Retrieve pending Device Flow state for a user."""
    try:
        import json
        result = get_client(telegram_id).table("users") \
            .select("device_flow_state") \
            .eq("telegram_id", telegram_id) \
            .single() \
            .execute()
        raw = result.data.get("device_flow_state") if result.data else None
        if not raw:
            return None
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        print(f"[supabase] get_device_flow_state error: {e}")
        return None


def delete_device_flow_state(telegram_id: str) -> bool:
    """Clear device flow state after auth completes or expires."""
    try:
        get_client(telegram_id).table("users") \
            .update({"device_flow_state": None}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return True
    except Exception as e:
        print(f"[supabase] delete_device_flow_state error: {e}")
        return False


def update_github_token(telegram_id: str, token: str) -> bool:
    """Update stored GitHub OAuth token after Device Flow authorization."""
    try:
        get_client(telegram_id).table("users") \
            .update({"github_token": token}) \
            .eq("telegram_id", telegram_id) \
            .execute()
        return True
    except Exception as e:
        print(f"[supabase] update_github_token error: {e}")
        return False

