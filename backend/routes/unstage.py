"""
routes/unstage.py - DELETE /staged-files/<file_id>
Called by the VS Code extension when user clicks Unstage on a file.
"""

from fastapi import APIRouter, HTTPException, Depends
from supabase_service import get_client, get_user_by_telegram_id
from auth import require_api_key

router = APIRouter()


@router.delete("/staged-files/{file_id}")
async def unstage_file(file_id: str, _auth: str = Depends(require_api_key)):
    """Remove a staged file by its UUID (marks as cancelled)."""
    try:
        db = get_client()
        # Verify file exists
        result = db.table("staged_files").select("id, telegram_id").eq("id", file_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Staged file not found.")

        # Ownership check: a valid API key only proves who the caller is, not
        # that they own this specific file. Without this, any authenticated
        # user could unstage/delete another user's staged file (IDOR).
        if str(result.data[0].get("telegram_id")) != str(_auth):
            raise HTTPException(status_code=404, detail="Staged file not found.")

        # Delete it
        db.table("staged_files").delete().eq("id", file_id).execute()
        return {"ok": True, "deleted_id": file_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[unstage] error: {e}")
        raise HTTPException(status_code=500, detail="Failed to unstage file.")
