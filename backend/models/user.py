from pydantic import BaseModel, Field
from typing import Optional


class RegisterPayload(BaseModel):
    telegram_id: str = Field(..., description="Telegram numeric user ID")
    github_token: str = Field(..., description="GitHub fine-grained PAT")
    default_repo: str = Field(..., description="Format: username/repo-name")
    branch: str = Field(default="main", description="Target branch")

    class Config:
        json_schema_extra = {
            "example": {
                "telegram_id": "123456789",
                "github_token": "ghp_xxxxxxxxxxxx",
                "default_repo": "username/repo-name",
                "branch": "main",
            }
        }


class UserResponse(BaseModel):
    ok: bool
    message: str
    telegram_id: Optional[str] = None
    error: Optional[str] = None
