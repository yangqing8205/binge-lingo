"""Central configuration loaded from the project-root .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name!r}. "
            f"Fill it in {PROJECT_ROOT / '.env'}"
        )
    return value


# --- LLM (OpenAI-compatible) ---
API_BASE_URL = _require("API_BASE_URL")
API_KEY = _require("API_KEY")
API_MODEL = os.getenv("API_MODEL", "anthropic/claude-sonnet-4-20250514").strip()

# --- Notion ---
NOTION_TOKEN = _require("NOTION_TOKEN")
NOTION_DATABASE_ID = _require("NOTION_DATABASE_ID")

# --- Watch folder ---
_watch = os.getenv("WATCH_DIR", "").strip()
WATCH_DIR = Path(_watch).expanduser() if _watch else PROJECT_ROOT / "screenshots"

# --- Image host ---
IMAGE_HOST = os.getenv("IMAGE_HOST", "notion").strip().lower()
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID", "").strip()

# --- Proxy (only applied to Notion traffic; the LLM gateway stays direct) ---
HTTPS_PROXY = (
    os.getenv("HTTPS_PROXY", "").strip()
    or os.getenv("https_proxy", "").strip()
)

# Local file tracking processed screenshots so restarts don't re-process.
STATE_FILE = PROJECT_ROOT / ".processed_screenshots.json"

# Image extensions we treat as screenshots.
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
