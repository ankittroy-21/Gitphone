from pydantic import BaseModel, Field
from typing import Optional, List


class CommitRequest(BaseModel):
    telegram_id: str
    file_ids: List[str] = Field(..., description="UUIDs of staged_files to commit")
    commit_message: str = Field(..., min_length=1, max_length=500)


class CommitResponse(BaseModel):
    ok: bool
    commit_sha: Optional[str] = None
    message: str
    error: Optional[str] = None
    conflict_files: Optional[List[str]] = None
