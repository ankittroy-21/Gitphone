"""
main.py - FastAPI app entry point.
Combines FastAPI HTTP routes + python-telegram-bot webhook in one process.
Deployed on Render (free tier, webhook mode = no sleeping).
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Header, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from telegram import Update

APP_VERSION = "1.0.0"

def get_telegram_user_id(request: Request) -> str:
    telegram_id = getattr(request.state, "telegram_user_id", None)
    if telegram_id:
        return telegram_id
    return get_remote_address(request)

limiter = Limiter(key_func=get_telegram_user_id)

from admin import register_admin_handlers  # noqa: E402
from bot import (  # noqa: E402
    admin_ban_handler,
    admin_broadcast_handler,
    admin_revoke_handler,
    admin_stats_handler,
    admin_unban_handler,
    admin_users_handler,
    build_auth_conversation,
    build_branch_conversation,
    build_files_conversation,
    build_start_conversation,
    cancel_handler,
    clear_confirm_callback,
    clear_handler,
    help_handler,
    log_handler,
    preview_handler,
    set_repo_handler,
    status_handler,
    unstage_handler,
)
from channel_logger import init_logger, log_shutdown, log_startup  # noqa: E402
from telegram.ext import Application, CallbackQueryHandler, CommandHandler  # noqa: E402
from admin import register_admin_handlers
from channel_logger import init_logger, log_startup, log_shutdown
from notifications import init_notifier
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
    """Set webhook or start polling on startup, clean up on shutdown."""
    webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    is_development = os.environ.get("ENVIRONMENT") == "development" or not webhook_url

    polling_task = None

    if not is_development:
        await telegram_app.initialize()
        webhook_kwargs = {
            "url": f"{webhook_url}/webhook",
            "allowed_updates": ["message", "callback_query"],
        }
        secret_token = os.environ.get("TELEGRAM_SECRET_TOKEN")
        if secret_token:
            webhook_kwargs["secret_token"] = secret_token
        await telegram_app.bot.set_webhook(**webhook_kwargs)
        print(f"[main] Webhook set to {webhook_url}/webhook (secret_token={'set' if secret_token else 'not set'})")
        await telegram_app.start()

        # Init channel logger and announce startup
        init_logger(telegram_app.bot)
        init_notifier(telegram_app.bot)
        await log_startup(webhook_url)
    else:
        await telegram_app.initialize()
        await telegram_app.bot.delete_webhook()
        await telegram_app.start()
        print("[main] Development mode detected or no WEBHOOK_URL provided. Falling back to polling.")
        
        # Run polling loop as a background task
        polling_task = asyncio.create_task(
            telegram_app.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
        )

        init_logger(telegram_app.bot)
        init_notifier(telegram_app.bot)
        try:
            await log_startup("polling")
        except Exception:
            pass

    yield

    await log_shutdown()
    if is_development:
        if polling_task:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    else:
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(
    title="GitPhone API",
    description="GitHub commits from Telegram - backend service",
    version=APP_VERSION,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def extract_telegram_user_id(request: Request, call_next):
    if request.url.path == "/webhook" and request.method == "POST":
        try:
            body_bytes = await request.body()
            body_json = json.loads(body_bytes)
            if "message" in body_json and "from" in body_json["message"]:
                request.state.telegram_user_id = str(body_json["message"]["from"]["id"])
            elif "callback_query" in body_json and "from" in body_json["callback_query"]:
                request.state.telegram_user_id = str(body_json["callback_query"]["from"]["id"])

            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = receive
        except Exception:
            pass
    return await call_next(request)


# --- Telegram Webhook Route ------------------------------------------------------------------------------
@app.post("/webhook")
@limiter.limit("30/minute")
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
# noqa: E402 — routes must be imported after `app` is fully built above
from routes.auth import router as auth_router  # noqa: E402
from routes.register import router as register_router  # noqa: E402
from routes.staged_files import router as staged_files_router  # noqa: E402
from routes.sync import router as sync_router  # noqa: E402
from routes.unstage import router as unstage_router  # noqa: E402
from routes.version import router as version_router  # noqa: E402

app.include_router(register_router)
app.include_router(github_webhook_router)
app.include_router(sync_router)
app.include_router(version_router)
app.include_router(staged_files_router)
app.include_router(unstage_router)
app.include_router(auth_router)


# --- Health Check -------------------------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "gitphone", "version": APP_VERSION}


@app.get("/")
async def root():
    return {
        "service": "GitPhone",
        "docs": "/docs",
        "health": "/health",
        "version": APP_VERSION,
    }
