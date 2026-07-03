"""
routes/unstage.py - DELETE /staged-files/<file_id>
Called by the VS Code extension when user clicks Unstage on a file.
"""

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException
from supabase_service import get_client

router = APIRouter()


@router.delete("/staged-files/{file_id}")
async def unstage_file(file_id: str, telegram_id: str = Depends(require_api_key)):
    """Remove a staged file by its UUID (marks as cancelled)."""
    try:
        db = get_client()
        # Verify file exists
        result = db.table("staged_files").select("id, telegram_id").eq("id", file_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Staged file not found.")

        # Verify ownership — prevent IDOR: ensure the file belongs to the requesting user
        file_owner = result.data[0].get("telegram_id")
        if str(file_owner) != str(telegram_id):
            raise HTTPException(status_code=403, detail="You do not have permission to unstage this file.")

        # Delete it
        db.table("staged_files").delete().eq("id", file_id).execute()
        return {"ok": True, "deleted_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[unstage] error: {e}")
        raise HTTPException(status_code=500, detail="Failed to unstage file.")
