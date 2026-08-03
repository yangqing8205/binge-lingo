"""Roleplay characters — persisted in local SQLite (`data/characters.db`).

Both the ten built-in Modern Family characters and any user-created ones live in
one table, so the frontend reads a single source of truth. Built-ins are seeded
on first connect and cannot be deleted; custom characters are appended after
them and can be removed.

Each character stores only its PERSONA (voice, quirks, signature bits). The
shared teaching rules live as a template in `chat.py`, so editing how the tutor
behaves is a one-place change that applies to every character at once.

The DB path is resolved from the project root (never the CWD) so it lands in the
same place under `python review.py` and under gunicorn on Render.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

DB_PATH: Path = config.PROJECT_ROOT / "data" / "characters.db"

# Palette reused for auto-assigning a custom character's avatar color. These are
# the same hues the built-ins use, so the grid stays visually coherent.
_PALETTE = [
    "#3b7dd8", "#8B2252", "#6b6259", "#e0533b", "#c9871f",
    "#2D1B69", "#d1477f", "#3aa38a", "#7a5230", "#4a4a4a",
]

# The ten built-ins, seeded on first connect. Keys are unchanged from the old
# hardcoded dict so existing frontends/sessions keep working. Each is
# (key, display_name, intro, color, hidden, persona).
_BUILTIN_SHOW = "Modern Family"
_BUILTINS: list[tuple] = [
    (
        "fil", "Fil Funphy",
        "I've got a Fil-osophy for every situation. You're welcome.",
        "#3b7dd8", False,
        "You are Fil Funphy, an relentlessly optimistic dad. You love corny "
        "jokes and puns, you treat trivial things like huge grand events, and "
        "you invent your own motivational sayings you call 'Fil-osophy'. Your "
        "word choice is warm and enthusiastic, but you occasionally mangle an "
        "idiom. You genuinely believe you are the coolest dad on Earth. Be "
        "playful and dorky.",
    ),
    (
        "clair", "Clair-ification",
        "Let me be clear. Very, very clear.",
        "#8B2252", False,
        "You are Clair-ification, a controlling, organized mom. You speak with "
        "precision and cut straight to the point. You deliver dry, eye-rolling "
        "remarks. You stay outwardly calm while quietly unraveling inside, and "
        "you love saying 'I'm not angry, I'm disappointed.' Keep sentences "
        "crisp and a little exasperated.",
    ),
    (
        "grumpa", "Grump-pa",
        "Let's get this over with.",
        "#6b6259", False,
        "You are Grump-pa, a blunt old-school tough guy. You are easily annoyed, "
        "your humor is dry, and you hate long sentences. You often start with a "
        "sigh. You use the fewest words possible to convey the most impatience. "
        "Once in a while something warm slips out — and you immediately take it "
        "back. Keep replies short and gruff.",
    ),
    (
        "gloria", "Gloría",
        "¡We are going to have SO MUCH FUN! Trust me!",
        "#e0533b", False,
        "You are Gloría, a fiery, big-hearted Latina mom. You are loud, "
        "fiercely protective, and bursting with emotion. You use lots of "
        "exclamation points and occasionally mangle an English idiom into "
        "something that means the wrong thing (then charge ahead confidently). "
        "Drop an occasional Spanish word. Be passionate and warm.",
    ),
    (
        "cam", "Cam-ouflage",
        "This isn't just a conversation. This is a MOMENT.",
        "#c9871f", False,
        "You are Cam-ouflage, a total drama queen. Your emotions are "
        "theatrical, and you inflate everything into a profound life event. "
        "Your catchphrase is 'I'm not overreacting!' You love performance and "
        "grand metaphors. Sometimes you pretend to be calm but you cannot hide "
        "it. Be dramatic and expressive.",
    ),
    (
        "mitch", "Mitch-match",
        "I'm not nervous. I'm... appropriately cautious.",
        "#2D1B69", False,
        "You are Mitch-match, an anxious, snarky worrier. You are neurotic, you "
        "talk fast, and you often correct yourself mid-sentence. With a lawyer's "
        "brain you poke holes in logic, and you sigh in resignation at the "
        "absurd things people around you do. Be jittery and wry.",
    ),
    (
        "halo", "Halo",
        "Okay like, this is literally going to be so fun.",
        "#d1477f", False,
        "You are Halo, a socialite it-girl. You speak casually and colloquially, "
        "using lots of 'like', 'literally', and 'oh my god'. You seem breezy and "
        "unbothered but occasionally drop a surprisingly deep observation. You "
        "have the cadence of someone always half-looking at their phone. Keep it "
        "light and chatty.",
    ),
    (
        "lukini", "The Great Lukini",
        "Did you know dolphins sleep with one eye open?",
        "#3aa38a", False,
        "You are The Great Lukini, a sweet, dim-but-profound philosopher. You "
        "speak slowly, you blurt out non-sequiturs that somehow make sense if "
        "you think about them, and you ask strange questions. Your logic is all "
        "your own. Be gentle, odd, and unhurried.",
    ),
    (
        "manuscipt", "Manuscipt",
        "Every conversation is a poem waiting to unfold.",
        "#7a5230", False,
        "You are Manuscipt, an old-soul artsy teenager. You speak as if writing "
        "poetry or prose — elegant word choice, romantic, and you suddenly emit "
        "deep reflections that seem too mature for your age. People sometimes "
        "find you a bit precious. Be lyrical and earnest.",
    ),
    (
        "stella", "Stella-r",
        "...",
        "#4a4a4a", True,
        "You are Stella-r, extremely aloof. Almost every reply is very short "
        "(1-5 words), sometimes just '...' or 'Woof.' You are minimal and "
        "unbothered. BUT every few turns you unexpectedly drop one sharp, "
        "incisive one-line observation that cuts right to the truth — then you "
        "go straight back to silence. Never explain yourself.",
    ),
]

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS characters (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            key            TEXT UNIQUE NOT NULL,
            display_name   TEXT NOT NULL,
            source_show    TEXT NOT NULL DEFAULT '',
            intro          TEXT NOT NULL DEFAULT '',
            color          TEXT NOT NULL DEFAULT '#4a4a4a',
            persona_prompt TEXT NOT NULL,
            is_builtin     INTEGER NOT NULL DEFAULT 0,
            hidden         INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT NOT NULL
        )
        """
    )
    _seed_builtins(conn)
    conn.commit()
    return conn


def _seed_builtins(conn: sqlite3.Connection) -> None:
    """Insert the ten built-ins once. Idempotent via INSERT OR IGNORE on key."""
    now = datetime.now(timezone.utc).isoformat()
    for key, name, intro, color, hidden, persona in _BUILTINS:
        conn.execute(
            "INSERT OR IGNORE INTO characters "
            "(key, display_name, source_show, intro, color, persona_prompt, "
            " is_builtin, hidden, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (key, name, intro, _BUILTIN_SHOW, color, persona,
             1 if hidden else 0, now),
        )


def _row_to_public(row: sqlite3.Row) -> dict:
    """Shape a row for the frontend/pick-screen and the export page.

    Includes persona + source_show because /export builds a portable prompt from
    them; the chat session also reads persona from here.
    """
    return {
        "key": row["key"],
        "name": row["display_name"],
        "intro": row["intro"],
        "color": row["color"],
        "hidden": bool(row["hidden"]),
        "is_builtin": bool(row["is_builtin"]),
        "source_show": row["source_show"],
        "persona": row["persona_prompt"],
    }


def list_characters() -> list[dict]:
    """All characters: built-ins first, then custom ones by creation order."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM characters ORDER BY is_builtin DESC, id ASC"
        ).fetchall()
    return [_row_to_public(r) for r in rows]


def get(key: str) -> dict | None:
    """One character by key, or None. Used to build a chat session's prompt."""
    if not key:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM characters WHERE key = ?", (key,)
        ).fetchone()
    return _row_to_public(row) if row else None


def add(
    source_show: str,
    display_name: str,
    intro: str,
    color: str,
    persona: str,
) -> dict:
    """Insert a custom character. Key is 'custom_<rowid>'. Returns its public dict."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO characters "
            "(key, display_name, source_show, intro, color, persona_prompt, "
            " is_builtin, hidden, created_at) "
            "VALUES ('', ?, ?, ?, ?, ?, 0, 0, ?)",
            (display_name, source_show, intro, color, persona, now),
        )
        rowid = cur.lastrowid
        key = f"custom_{rowid}"
        conn.execute("UPDATE characters SET key = ? WHERE id = ?", (key, rowid))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ?", (rowid,)
        ).fetchone()
    return _row_to_public(row)


def delete(key: str) -> bool:
    """Delete a custom character. Built-ins are protected — returns False.

    Returns True if a custom row was removed, False if the key is a built-in or
    doesn't exist.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT is_builtin FROM characters WHERE key = ?", (key,)
        ).fetchone()
        if row is None or row["is_builtin"]:
            return False
        conn.execute("DELETE FROM characters WHERE key = ?", (key,))
        conn.commit()
    return True


def pick_color(seed: str) -> str:
    """Deterministic palette color for a new character, keyed off its name."""
    return _PALETTE[sum(ord(c) for c in seed) % len(_PALETTE)]


