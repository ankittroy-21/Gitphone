"""
routes/version.py - GET /version
Called by VS Code extension on startup for schema version check.
"""

from fastapi import APIRouter

router = APIRouter()

CURRENT_SCHEMA_VERSION = 1


@router.get("/version")
async def get_version():
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "migration_sql": None,  # Populated when schema bumps
        "docs_url": "https://github.com/ankittroy-21/gitphone/blob/main/public/docs/setup-guide.md",
        "changelog_url": "https://github.com/ankittroy-21/gitphone/blob/ECSoC'26/CHANGELOG.md",
    }
