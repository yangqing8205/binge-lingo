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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

DB_PATH: Path = config.PROJECT_ROOT / "data" / "review_log.db"

# The four buckets the UI reports. Uppercase names are the storage/code form;
# the UI maps them to Chinese labels. Kept as a set so an unexpected value from
# a stale client is caught early rather than silently stored.
RESULTS = {
    "FIRST_TRY_CORRECT",  # 一次答对 — correct on the first, no-hint attempt
    "CUED_CORRECT",       # 提示后答对 — correct after the hint layer
    "INCORRECT",          # 答错 — guessed again with hints and still missed
    "REVEALED",           # 看了答案 — gave up / skipped straight to the answer
}

# Old lowercase buckets → new uppercase names. Applied once on connect so any
# rows written before the rename are migrated in place, never left mixed.
_LEGACY_RENAMES = {
    "cold": "FIRST_TRY_CORRECT",
    "hint": "CUED_CORRECT",
    "wrong": "INCORRECT",
    "skip": "REVEALED",
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
    for old, new in _LEGACY_RENAMES.items():
        conn.execute(
            "UPDATE review_log SET result = ? WHERE result = ?", (new, old)
        )
    conn.commit()
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


def history(page_id: str) -> dict | None:
    """Per-expression practice history for the word-history component.

    Returns None when the page has no attempts yet (the UI hides the block).
    Otherwise: total attempts, how many were FIRST_TRY_CORRECT, and the most
    recent attempt's result + timestamp. Recording-only read; no scheduling.
    """
    if not page_id:
        return None
    with _connect() as conn:
        total, first_try = conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN result = 'FIRST_TRY_CORRECT' THEN 1 ELSE 0 END) "
            "FROM review_log WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        if not total:
            return None
        last = conn.execute(
            "SELECT result, created_at FROM review_log "
            "WHERE page_id = ? ORDER BY id DESC LIMIT 1",
            (page_id,),
        ).fetchone()
    return {
        "total": total,
        "first_try": first_try or 0,
        "last_result": last[0],
        "last_at": last[1],
    }


def today_count(page_ids: set[str] | None = None) -> int:
    """Number of attempts recorded so far today, in the server's local day.

    Timestamps are stored in UTC, so we compute the local day's [start, end)
    and convert both bounds to UTC ISO strings — comparing against a bare local
    date would miscount rows near midnight. Count only, no scheduling.

    `page_ids`, when given, restricts the count to attempts on those pages —
    this is how the TODAY counter stays scoped to the current show, since the
    log itself has no show column (only page_id/expression/result).
    """
    now_local = datetime.now().astimezone()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).isoformat()
    end_utc = end_local.astimezone(timezone.utc).isoformat()
    with _connect() as conn:
        if page_ids is not None:
            if not page_ids:
                return 0
            placeholders = ",".join("?" * len(page_ids))
            (n,) = conn.execute(
                f"SELECT COUNT(*) FROM review_log "
                f"WHERE created_at >= ? AND created_at < ? "
                f"AND page_id IN ({placeholders})",
                (start_utc, end_utc, *page_ids),
            ).fetchone()
        else:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM review_log "
                "WHERE created_at >= ? AND created_at < ?",
                (start_utc, end_utc),
            ).fetchone()
    return n
