"""
routes/register.py - POST /register
Called by the VS Code extension during first-time setup.
Validates GitHub token + repo access, then saves user to Supabase.
Generates a per-user API key returned ONCE - extension stores it for all future requests.
"""

from fastapi import APIRouter, HTTPException
from models.user import RegisterPayload, UserResponse
from github_service import github_service
from supabase_service import upsert_user
from auth import generate_api_key

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterPayload):
    try:
        # Step 1: Validate GitHub token and repo access
        gh_result = github_service.validate_token_and_repo(
            payload.github_token, payload.default_repo
        )
        if not gh_result["ok"]:
            error = gh_result.get("error", "github_error")
            message = gh_result.get("message", "GitHub validation failed")
            raise HTTPException(status_code=400, detail={"error": error, "message": message})

        # Step 2: Generate API key (raw returned to client, hash stored in DB)
        raw_key, hashed_key = generate_api_key()

        # Step 3: Upsert user record in Supabase
        user_data = {
            "telegram_id": payload.telegram_id,
            "github_token": payload.github_token,
            "github_username": (gh_result.get("username") or "").lower() or None,
            "default_repo": payload.default_repo,
            "branch": payload.branch or gh_result.get("default_branch", "main"),
            "api_key_hash": hashed_key,   # Never store the raw key
        }
        saved = upsert_user(user_data)
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to save user configuration")

        return UserResponse(
            ok=True,
            message="Registered successfully",
            telegram_id=payload.telegram_id,
            api_key=raw_key,   # Sent ONCE - extension must store this securely
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[register] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
