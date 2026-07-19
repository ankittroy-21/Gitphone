import channel_logger
from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException
from models.staged import MAX_FILE_SIZE, SyncFilePayload, SyncFileResponse
from supabase_service import (
    get_user_by_telegram_id,
    update_active_repo,
    update_last_active,
    upsert_staged_file,
)

# MAX_FILE_SIZE is imported from models.staged — single source of truth

router = APIRouter()

@router.post("/sync-file", response_model=SyncFileResponse)
async def sync_file(payload: SyncFilePayload, _auth: str = Depends(require_api_key)):
    try:
        if payload.telegram_id != _auth:
            raise HTTPException(status_code=403, detail="Forbidden: telegram_id does not match authenticated user")
        # Step 1: Resolve user
        user = get_user_by_telegram_id(payload.telegram_id)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not registered. Complete setup in VS Code first."
            )

        content_length = len(payload.full_content.encode('utf-8')) if payload.full_content else 0
        diff_length = len(payload.diff.encode('utf-8')) if payload.diff else 0

        if content_length > MAX_FILE_SIZE or diff_length > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Actual payload size exceeds 10MB limit")

        is_deletion = payload.change_type == "delete" or payload.base_sha == "delete"
        if not is_deletion and not payload.diff and not payload.full_content:
            raise HTTPException(
                status_code=400,
                detail="Either diff or full_content must be provided"
            )

        effective_repo = payload.active_repo or user.get("active_repo") or user.get("default_repo", "")
        effective_branch = payload.active_branch or user.get("active_branch") or user.get("branch", "main")

        if payload.active_repo:
            update_active_repo(payload.telegram_id, payload.active_repo, effective_branch)

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

        update_last_active(payload.telegram_id)

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
