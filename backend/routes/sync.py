"""
routes/sync.py - POST /sync-file
Called by VS Code extension on every file save.
Stores the diff in Supabase staged_files.
Auto-updates active_repo/active_branch from the extension's git detection.
"""

from fastapi import APIRouter, HTTPException, Depends
from models.staged import SyncFilePayload, SyncFileResponse
from supabase_service import (
    get_user_by_telegram_id, upsert_staged_file,
    update_last_active, update_active_repo,
)
import channel_logger
from auth import require_api_key

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

router = APIRouter()


@router.post("/sync-file", response_model=SyncFileResponse)
async def sync_file(payload: SyncFilePayload, _auth: str = Depends(require_api_key)):
    try:
        if payload.telegram_id != _auth:
            raise HTTPException(status_code=403, detail="Forbidden: telegram_id does not match authenticated user")
        # Step 1: Resolve user
        user = get_user_by_telegram_id(_auth)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not registered. Complete setup in VS Code first."
            )

        # Step 2: File size guard (defense in depth - extension checks first)
        if payload.file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds 10MB limit ({payload.file_size} bytes)"
            )

        # Step 3: Validate content - deletions are allowed with no diff/content
        is_deletion = payload.change_type == "delete" or payload.base_sha == "delete"
        if not is_deletion and not payload.diff and not payload.full_content:
            raise HTTPException(
                status_code=400,
                detail="Either diff or full_content must be provided"
            )

        # Step 4: Auto-update active repo if extension sent it
        effective_repo = payload.active_repo or user.get("active_repo") or user.get("default_repo", "")
        effective_branch = payload.active_branch or user.get("active_branch") or user.get("branch", "main")

        if payload.active_repo:
            update_active_repo(payload.telegram_id, payload.active_repo, effective_branch)

        # Step 5: Upsert staged file (include repo + change_type for grouping and display)
        staged_payload = {
            "user_id": user["id"],
            "telegram_id": payload.telegram_id,
            "filepath": payload.filepath,
            "diff": payload.diff,
            "full_content": payload.full_content,
            "base_sha": payload.base_sha,
            "is_binary": payload.is_binary,
            "file_size": payload.file_size,
            "repo": effective_repo,
            "change_type": payload.change_type or "modify",
            "status": "pending",
        }
        saved = upsert_staged_file(staged_payload)
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to stage file")

        # Step 6: Touch last_active
        update_last_active(payload.telegram_id)

        # Step 7: Log to channel (non-blocking)
        await channel_logger.log_file_staged(
            telegram_id=payload.telegram_id,
            filepath=payload.filepath,
            repo=effective_repo,
            file_size=payload.file_size,
            is_binary=payload.is_binary,
        )

        return SyncFileResponse(
            ok=True,
            staged_id=saved["id"],
            message="File staged successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[sync_file] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

