"""Tiny key-value store for app-wide settings — currently just `current_show`.

The product previously had no concept of "the show you're watching right now";
every screen guessed it independently from the newest Notion card, and guesses
disagreed with each other. This module is the single source of truth: watcher
sets it when you start a session, the frontend can change it via a switcher,
and every tab reads the same value.

Persisted in local SQLite, next to `characters.db`, so it survives restarts.
Not synced anywhere — on Render's free tier (no persistent disk) this resets
on every deploy, same as the other local DBs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

DB_PATH: Path = config.PROJECT_ROOT / "data" / "app_settings.db"

_CURRENT_SHOW_KEY = "current_show"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def get_current_show() -> str:
    """The show every tab should currently filter by. '' means no filter (all shows)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_CURRENT_SHOW_KEY,)
        ).fetchone()
    return row[0] if row else ""


def set_current_show(show: str) -> str:
    """Persist the current show. Empty string clears it (back to 'all shows')."""
    value = (show or "").strip()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_CURRENT_SHOW_KEY, value),
        )
        conn.commit()
    return value
