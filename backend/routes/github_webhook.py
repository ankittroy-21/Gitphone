"""routes/github_webhook.py - Receives GitHub 'issues' webhooks and notifies assignees."""

import hashlib
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Request
from notifications import notify_issue_assigned
from supabase_service import get_user_by_github_username

router = APIRouter()

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 (sha256=<hmac>). Constant-time compare."""
    if not WEBHOOK_SECRET:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/github-webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    body = await request.body()
    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event == "ping":
        return {"ok": True, "pong": True}

    if x_github_event != "issues":
        return {"ok": True, "ignored": "not an issues event"}

    payload = await request.json()
    if payload.get("action") != "assigned":
        return {"ok": True, "ignored": "not an assignment"}

    issue = payload.get("issue", {}) or {}
    assignee = (payload.get("assignee") or {})
    login = assignee.get("login")
    repo_full = (payload.get("repository") or {}).get("full_name", "unknown/repo")

    if not login:
        return {"ok": True, "ignored": "no assignee login"}

    user = get_user_by_github_username(login)
    if not user:
        return {"ok": True, "ignored": "assignee not registered"}
    if user.get("status") == "banned":
        return {"ok": True, "ignored": "user banned"}

    sent = await notify_issue_assigned(
        telegram_id=user["telegram_id"],
        repo=repo_full,
        issue_title=issue.get("title", "(no title)"),
        issue_number=issue.get("number", 0),
        issue_url=issue.get("html_url", ""),
    )
    return {"ok": True, "notified": sent}
