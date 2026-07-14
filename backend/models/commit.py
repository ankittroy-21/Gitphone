from pydantic import BaseModel, Field


class CommitRequest(BaseModel):
    telegram_id: str
    file_ids: list[str] = Field(..., description="UUIDs of staged_files to commit")
    commit_message: str = Field(..., min_length=1, max_length=500)


class CommitResponse(BaseModel):
    ok: bool
    commit_sha: str | None = None
    message: str
    error: str | None = None
    conflict_files: list[str] | None = None
