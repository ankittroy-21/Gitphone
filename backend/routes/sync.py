"""
routes/sync.py — POST /sync-file
Called by VS Code extension on every file save.
Stores the diff in Supabase staged_files.
"""

from fastapi import APIRouter, HTTPException
from models.staged import SyncFilePayload, SyncFileResponse
from supabase_service import get_user_by_telegram_id, upsert_staged_file, update_last_active
import channel_logger

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

router = APIRouter()


@router.post("/sync-file", response_model=SyncFileResponse)
async def sync_file(payload: SyncFilePayload):
    try:
        # Step 1: Resolve user
        user = get_user_by_telegram_id(payload.telegram_id)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not registered. Complete setup in VS Code first."
            )

        # Step 2: File size guard (defense in depth — extension checks first)
        if payload.file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds 10MB limit ({payload.file_size} bytes)"
            )

        # Step 3: Must have either diff or full_content
        if not payload.diff and not payload.full_content:
            raise HTTPException(
                status_code=400,
                detail="Either diff or full_content must be provided"
            )

        # Step 4: Upsert staged file
        staged_payload = {
            "user_id": user["id"],
            "telegram_id": payload.telegram_id,
            "filepath": payload.filepath,
            "diff": payload.diff,
            "full_content": payload.full_content,
            "base_sha": payload.base_sha,
            "is_binary": payload.is_binary,
            "file_size": payload.file_size,
            "status": "pending",
        }
        saved = upsert_staged_file(staged_payload)
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to stage file")

        # Step 5: Touch last_active
        update_last_active(payload.telegram_id)

        # Step 6: Log to channel (non-blocking)
        await channel_logger.log_file_staged(
            telegram_id=payload.telegram_id,
            filepath=payload.filepath,
            repo=user.get("default_repo", "—"),
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
