"""
routes/auth.py -- GitHub Device Flow OAuth for the Telegram bot.

Flow:
  1. POST /auth/device/start    -- request device_code + user_code from GitHub
  2. Bot shows user: "Go to https://github.com/login/device, enter code: XXXX-XXXX"
  3. GET  /auth/device/poll     -- bot polls this until token arrives (max 5min)
  4. Token stored in users table, device state cleaned up

Requires env vars:
  GITHUB_CLIENT_ID     -- from GitHub OAuth App (Settings -> Developer Settings)
  GITHUB_CLIENT_SECRET -- same
"""

import os
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase_service import (
    delete_device_flow_state,
    get_device_flow_state,
    save_device_flow_state,
    update_github_token,
)

router = APIRouter()

GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

DEVICE_CODE_URL  = "https://github.com/login/device/code"
TOKEN_URL        = "https://github.com/login/oauth/access_token"
SCOPE            = "repo,read:user"


class DeviceStartRequest(BaseModel):
    telegram_id: str


class DevicePollRequest(BaseModel):
    telegram_id: str


# --- POST /auth/device/start ---------------------------------------------------

@router.post("/auth/device/start")
async def device_start(req: DeviceStartRequest):
    """
    Step 1: Request a device code from GitHub.
    Returns user_code and verification_uri to show the user.
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GitHub OAuth App not configured. Set GITHUB_CLIENT_ID env var."
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            DEVICE_CODE_URL,
            data={"client_id": GITHUB_CLIENT_ID, "scope": SCOPE},
            headers={"Accept": "application/json"},
            timeout=10,
        )

    data = resp.json()

    if "error" in data:
        raise HTTPException(status_code=400, detail=data.get("error_description", data["error"]))

    device_code      = data["device_code"]
    user_code        = data["user_code"]
    verification_uri = data["verification_uri"]
    expires_in       = data.get("expires_in", 900)
    interval         = data.get("interval", 5)

    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Store device state so poll endpoint knows what to poll
    save_device_flow_state(req.telegram_id, {
        "device_code": device_code,
        "interval": interval,
        "expires_at": expires_at.isoformat(),
    })

    return {
        "ok": True,
        "user_code": user_code,
        "verification_uri": verification_uri,
        "expires_in": expires_in,
        "interval": interval,
    }


# --- POST /auth/device/poll ----------------------------------------------------

@router.post("/auth/device/poll")
async def device_poll(req: DevicePollRequest):
    """
    Step 2 (repeated): Poll GitHub to check if user has authorized.
    Returns { status: "pending" | "authorized" | "expired" | "error" }
    """
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GitHub OAuth App not configured.")

    state = get_device_flow_state(req.telegram_id)
    if not state:
        raise HTTPException(status_code=404, detail="No active device flow. Call /auth/device/start first.")

    # Check expiry
    expires_at = datetime.fromisoformat(state["expires_at"])
    if datetime.utcnow() > expires_at:
        delete_device_flow_state(req.telegram_id)
        return {"status": "expired"}

    device_code = state["device_code"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )

    data = resp.json()

    if "access_token" in data:
        # Success! Store token
        token = data["access_token"]
        update_github_token(req.telegram_id, token)
        delete_device_flow_state(req.telegram_id)
        return {"status": "authorized"}

    error = data.get("error", "")

    if error == "authorization_pending":
        return {"status": "pending"}

    if error == "slow_down":
        return {"status": "pending", "slow_down": True}

    if error == "expired_token":
        delete_device_flow_state(req.telegram_id)
        return {"status": "expired"}

    # Other error
    delete_device_flow_state(req.telegram_id)
    return {"status": "error", "message": data.get("error_description", error)}
