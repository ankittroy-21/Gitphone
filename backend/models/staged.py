from pydantic import BaseModel, Field, validator
from typing import Optional


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


class SyncFilePayload(BaseModel):
    telegram_id: str = Field(..., description="Telegram numeric user ID")
    filepath: str = Field(..., description="Relative path from workspace root")
    diff: Optional[str] = Field(None, description="Unified diff patch (null if binary)")
    full_content: Optional[str] = Field(None, description="Base64-encoded content for binary/new files")
    base_sha: str = Field(..., description="Git SHA diff was computed against, or 'new_file'")
    is_binary: bool = Field(default=False)
    file_size: int = Field(default=0, description="File size in bytes")

    @validator("file_size")
    def check_size_limit(cls, v):
        if v > MAX_FILE_SIZE:
            raise ValueError("File exceeds 10MB limit")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "telegram_id": "123456789",
                "filepath": "src/index.js",
                "diff": "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new",
                "full_content": None,
                "base_sha": "abc123def456",
                "is_binary": False,
                "file_size": 2048,
            }
        }


class SyncFileResponse(BaseModel):
    ok: bool
    staged_id: Optional[str] = None
    message: str
    error: Optional[str] = None
