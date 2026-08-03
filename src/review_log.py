"""Local SQLite log of review attempts.

Every answer submission (and every skip) appends one row to
`data/review_log.db`. This is *recording only* — no scheduling, no reads back
into the review flow. It exists so a future spaced-repetition layer has real
history to learn from.

The DB path is resolved from the project root (never the CWD) so it lands in
the same place under `python review.py` and under gunicorn on Render.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

DB_PATH: Path = config.PROJECT_ROOT / "data" / "review_log.db"

# The four buckets the UI reports. Kept as a set so an unexpected value from a
# stale client is caught early rather than silently stored.
RESULTS = {
    "cold",     # 裸答对 — correct on the first, no-hint attempt
    "hint",     # 看提示后答对 — correct after the hint layer
    "wrong",    # 答错 — guessed again with hints and still missed
    "skip",     # 直接跳过看答案 — gave up / skipped straight to the answer
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id         TEXT NOT NULL,
            expression      TEXT NOT NULL,
            result          TEXT NOT NULL,
            elapsed_seconds REAL,
            created_at      TEXT NOT NULL
        )
        """
    )
    return conn


def record(
    page_id: str,
    expression: str,
    result: str,
    elapsed_seconds: float | None,
) -> None:
    """Append one attempt. Raises ValueError on an unknown result bucket."""
    if result not in RESULTS:
        raise ValueError(f"unknown result {result!r}; expected one of {sorted(RESULTS)}")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO review_log "
            "(page_id, expression, result, elapsed_seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (page_id, expression, result, elapsed_seconds, created_at),
        )
