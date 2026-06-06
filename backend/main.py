"""
main.py — FastAPI app entry point.
Combines FastAPI HTTP routes + python-telegram-bot webhook in one process.
Deployed on Render (free tier, webhook mode = no sleeping).
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from bot import (
    build_start_conversation,
    build_files_conversation,
    log_handler,
    status_handler,
    help_handler,
    cancel_handler,
)
from admin import register_admin_handlers
from channel_logger import init_logger, log_startup, log_shutdown
from telegram.ext import CommandHandler

# ── Build Telegram Application ────────────────────────────────────────────────
telegram_app = (
    Application.builder()
    .token(os.environ["TELEGRAM_BOT_TOKEN"])
    .build()
)

# Register conversation handlers (order matters — conversations first)
telegram_app.add_handler(build_start_conversation())
telegram_app.add_handler(build_files_conversation())

# Standalone command handlers
telegram_app.add_handler(CommandHandler("log", log_handler))
telegram_app.add_handler(CommandHandler("status", status_handler))
telegram_app.add_handler(CommandHandler("help", help_handler))
telegram_app.add_handler(CommandHandler("cancel", cancel_handler))

# Admin-only handlers (guarded by ADMIN_TELEGRAM_IDS env var)
register_admin_handlers(telegram_app)


# ── FastAPI Lifespan ──────────────────────────────────────────────────────────
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
    description="GitHub commits from Telegram — backend service",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Telegram Webhook Route ────────────────────────────────────────────────────
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


# ── API Routes ────────────────────────────────────────────────────────────────
from routes.register import router as register_router
from routes.sync import router as sync_router
from routes.version import router as version_router

app.include_router(register_router)
app.include_router(sync_router)
app.include_router(version_router)


# ── Health Check ─────────────────────────────────────────────────────────────
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
