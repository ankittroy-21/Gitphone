"""
routes/staged_files.py - Staged file management endpoints.

GET  /staged-files/{telegram_id}   - list pending staged files (extension sidebar)
POST /staged-files/clear-all       - clear all staged files for a user
POST /commit-direct                - commit directly from VS Code (no Telegram)
"""

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from github_service import github_service
from pydantic import BaseModel
from supabase_service import (
    clear_all_staged,
    get_pending_files,
    get_staged_files_by_ids,
    get_user_by_telegram_id,
    mark_files_committed,
    sync_pending_state,
)

router = APIRouter()


# --- POST /staged-files/sync-state --------------------------------------------

class SyncStatePayload(BaseModel):
    telegram_id: str
    current_filepaths: list[str]


@router.post("/staged-files/sync-state")
async def sync_state_route(payload: SyncStatePayload, telegram_id: str = Depends(require_api_key)):
    """
    Called by extension whenever git state changes.
    Ensures bot doesn't show files that were committed/reverted manually.
    """
    if payload.telegram_id != telegram_id:
        raise HTTPException(status_code=403, detail="You can only sync your own staged files.")

    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")

    count = sync_pending_state(telegram_id, payload.current_filepaths)
    return {"ok": True, "reconciled_count": count}


# --- GET /staged-files/{telegram_id} ------------------------------------------

@router.get("/staged-files/{telegram_id}")
async def list_staged_files(telegram_id: str, auth_id: str = Depends(require_api_key)):
    """Return all pending staged files for the extension sidebar."""
    if telegram_id != auth_id:
        raise HTTPException(status_code=403, detail="You can only view your own staged files.")

    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")

    if user.get("status") == "banned":
        raise HTTPException(status_code=403, detail="Account suspended.")

    files = get_pending_files(telegram_id)

    return {
        "ok": True,
        "telegram_id": telegram_id,
        "repo": user.get("active_repo") or user.get("default_repo"),
        "branch": user.get("active_branch") or user.get("branch"),
        "count": len(files),
        "files": [
            {
                "id": f["id"],
                "filepath": f["filepath"],
                "file_size": f.get("file_size", 0),
                "is_binary": f.get("is_binary", False),
                "staged_at": f.get("staged_at", ""),
                "status": f.get("status", "pending"),
                "change_type": f.get("change_type", "modify"),
                "repo": f.get("repo") or user.get("active_repo") or user.get("default_repo"),
                "diff": f.get("diff"),  # sent to extension for inline diff view
            }
            for f in files
        ],
    }


# --- POST /staged-files/clear-all ---------------------------------------------

@router.post("/staged-files/clear-all")
async def clear_all_route(request: Request, _auth: str = Depends(require_api_key)):
    """Clear all pending staged files for the requesting user."""
    telegram_id = request.headers.get("X-Telegram-Id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="X-Telegram-Id header required")

    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")

    clear_all_staged(telegram_id)
    return {"ok": True, "message": "All staged files cleared."}


# --- POST /commit-direct ------------------------------------------------------

class DirectCommitPayload(BaseModel):
    telegram_id: str
    file_ids: list[str]
    commit_message: str


@router.post("/commit-direct")
async def commit_direct(payload: DirectCommitPayload, telegram_id: str = Depends(require_api_key)):
    """
    Commit staged files directly from VS Code without Telegram.
    Called by the extension's 'Commit All' / 'Commit This File' commands.
    """
    # Prevent IDOR: ensure the authenticated user matches the payload telegram_id
    if payload.telegram_id != telegram_id:
        raise HTTPException(status_code=403, detail="You can only commit your own staged files.")

    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not registered.")

    if user.get("status") == "banned":
        raise HTTPException(status_code=403, detail="Account suspended.")

    if not user.get("github_token"):
        raise HTTPException(
            status_code=400,
            detail="No GitHub PAT found. Register with /start in the Telegram bot first.",
        )

    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided.")

    staged_files = get_staged_files_by_ids(payload.file_ids)
    if not staged_files:
        raise HTTPException(status_code=404, detail="No staged files found with given IDs.")

    repo = (
        staged_files[0].get("repo")
        or user.get("active_repo")
        or user.get("default_repo")
    )
    branch = user.get("active_branch") or user.get("branch") or "main"

    if not repo:
        raise HTTPException(
            status_code=400,
            detail="No repo detected. Save a file so GitPhone can auto-detect your repo.",
        )

    result = github_service.commit_files(
        token=user["github_token"],
        repo_name=repo,
        branch=branch,
        staged_files=staged_files,
        commit_message=payload.commit_message,
    )

    if not result["ok"]:
        if result.get("error") == "conflict":
            conflict_files = result.get("conflict_files", [])
            raise HTTPException(
                status_code=409,
                detail=f"Conflict in: {', '.join(conflict_files)}. Use /files in Telegram \u2192 Force Commit.",
            )
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "GitHub commit failed."),
        )

    committed_ids = [f["id"] for f in staged_files]
    mark_files_committed(committed_ids)

    commit_sha = result.get("commit_sha", "")
    commit_url = f"https://github.com/{repo}/commit/{commit_sha}" if commit_sha else ""

    return {
        "ok": True,
        "commit_sha": commit_sha,
        "commit_url": commit_url,
        "repo": repo,
        "branch": branch,
        "files_committed": len(staged_files),
        "conflict_files": result.get("conflict_files", []),
    }
