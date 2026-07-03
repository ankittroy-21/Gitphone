"""
main.py - FastAPI app entry point.
Combines FastAPI HTTP routes + python-telegram-bot webhook in one process.
Deployed on Render (free tier, webhook mode = no sleeping).
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException
from telegram import Update
from telegram.ext import Application

from bot import (
    build_start_conversation,
    build_files_conversation,
    build_auth_conversation,
    build_branch_conversation,
    log_handler,
    status_handler,
    help_handler,
    cancel_handler,
    set_repo_handler,
    preview_handler,
    unstage_handler,
    clear_handler,
    clear_confirm_callback,
    admin_ban_handler,
    admin_unban_handler,
    admin_users_handler,
    admin_broadcast_handler,
    admin_stats_handler,
    admin_revoke_handler,
)
from admin import register_admin_handlers
from channel_logger import init_logger, log_startup, log_shutdown
from telegram.ext import CommandHandler, CallbackQueryHandler

# --- Build Telegram Application ------------------------------------------------------------------------
telegram_app = (
    Application.builder()
    .token(os.environ["TELEGRAM_BOT_TOKEN"])
    .build()
)

# Conversation handlers (order matters - most specific first)
telegram_app.add_handler(build_start_conversation())
telegram_app.add_handler(build_files_conversation())
telegram_app.add_handler(build_auth_conversation())
telegram_app.add_handler(build_branch_conversation())

# Standalone user commands
telegram_app.add_handler(CommandHandler("log", log_handler))
telegram_app.add_handler(CommandHandler("status", status_handler))
telegram_app.add_handler(CommandHandler("help", help_handler))
telegram_app.add_handler(CommandHandler("cancel", cancel_handler))
telegram_app.add_handler(CommandHandler("repo", set_repo_handler))
telegram_app.add_handler(CommandHandler("preview", preview_handler))
telegram_app.add_handler(CommandHandler("unstage", unstage_handler))
telegram_app.add_handler(CommandHandler("clear", clear_handler))

# Inline button callbacks for /clear
telegram_app.add_handler(CallbackQueryHandler(clear_confirm_callback, pattern=r"^CLEAR_CONFIRM$"))

# Admin commands
telegram_app.add_handler(CommandHandler("ban", admin_ban_handler))
telegram_app.add_handler(CommandHandler("unban", admin_unban_handler))
telegram_app.add_handler(CommandHandler("users", admin_users_handler))
telegram_app.add_handler(CommandHandler("broadcast", admin_broadcast_handler))
telegram_app.add_handler(CommandHandler("stats", admin_stats_handler))
telegram_app.add_handler(CommandHandler("revoke", admin_revoke_handler))

# Legacy admin handlers from admin.py (kept for backward compat)
register_admin_handlers(telegram_app)



# --- FastAPI Lifespan ---------------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set webhook on startup, clean up on shutdown."""
    webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(
        url=f"{webhook_url}/webhook",
        allowed_updates=["message", "callback_query"],
    )
    print(f"[main] Webhook set to {webhook_url}/webhook")
    await telegram_app.start()

    # Init channel logger and announce startup
    init_logger(telegram_app.bot)
    await log_startup(webhook_url)

    yield

    await log_shutdown()
    await telegram_app.stop()
    await telegram_app.shutdown()


app = FastAPI(
    title="GitPhone API",
    description="GitHub commits from Telegram - backend service",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Telegram Webhook Route ------------------------------------------------------------------------------
@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    expected_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    
    if expected_token and x_telegram_bot_api_secret_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

# --- API Routes ------------------------------------------------------------------------------------------------
from routes.register import router as register_router
from routes.sync import router as sync_router
from routes.version import router as version_router
from routes.staged_files import router as staged_files_router
from routes.unstage import router as unstage_router
from routes.auth import router as auth_router

app.include_router(register_router)
app.include_router(sync_router)
app.include_router(version_router)
app.include_router(staged_files_router)
app.include_router(unstage_router)
app.include_router(auth_router)


# --- Health Check -------------------------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "gitphone", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "service": "GitPhone",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0",
    }
