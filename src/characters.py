"""Roleplay characters — persisted in local SQLite (`data/characters.db`).

Both the ten built-in Modern Family characters and any user-created ones live in
one table, so the frontend reads a single source of truth. Built-ins are seeded
on first connect and cannot be deleted; custom characters are appended after
them and can be removed.

Each character stores its PERSONA. Older/built-in rows carry only a flat
`persona_prompt` string. Newer rows also carry a structured `card_json` — see
`CARD SCHEMA` below — plus a `card_tier` marking how complete it is:
  - "legacy": no card_json; persona_prompt is the only source (built-ins, and
    anything created before this feature existed).
  - "starter": card_json exists but is intentionally thin (1-2 signature_moves,
    1 opening_variant) — produced fast, in parallel, at cast-generation time.
  - "full": card_json has been topped up (3-5 signature_moves, 2-3
    opening_variants) — happens lazily the first time the character is
    actually selected for a chat (see chat.py's `_ensure_full_card`).
`persona_prompt` is kept in sync as a flattened rendering of card_json (via
`flatten_card`) so old consumers (the teaching template, export.js) never need
to know card_json exists.

CARD SCHEMA (card_json, when present):
    {
      "voice": {"pace": str, "sentence_length": str, "vocabulary": str,
                "tone": str, "emotional_range": str,
                "evidence": {"quote": str, "confidence": "verbatim"|"reconstructed",
                             "source": str}},
      "signature_moves": [{"name": str, "steps": [str], "frequency": str,
                            "evidence": {"quote": str,
                                         "confidence": "verbatim"|"reconstructed",
                                         "source": str},
                            "distinct_because": str}],
      "format_style": {"caps": str, "bold": str, "ellipsis": str,
                        "exclaim": str, "notes": str},
      "opening_variants": [str],
      "relationship_style": {"address_terms": [str], "encouragement_style": str,
                              "teasing_style": str},
      "avoid": [str]
    }
Evidence lives INLINE on `voice` and each `signature_moves` entry (a
quote/confidence/source triple) rather than in a separate cross-referenced
bank — a feature with no evidence object simply can't be written, and the
generation prompt (chat.py) refuses to accept one that's missing. `confidence`
is "verbatim" only when the model is confident the quote is word-for-word;
otherwise "reconstructed" (a plausible in-character line, not a citation).
`distinct_because` on each signature_move is a forced self-check: a sentence
explaining why this move wouldn't fit an interchangeable character of the same
archetype — see chat.py's `_CARD_HARD_RULES`.

The shared teaching rules live as a template in `chat.py`, so editing how the
tutor behaves is a one-place change that applies to every character at once.

The DB path is resolved from the project root (never the CWD) so it lands in the
same place under `python review.py` and under gunicorn on Render.
"""
from __future__ import annotations

import json
import re
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

# Columns added after the table's original creation. Each is (name, ddl-suffix,
# default-for-existing-rows). Applied via ALTER TABLE on connect if missing —
# cheap idempotency check through PRAGMA table_info instead of a migrations
# framework, since this is a single-table local SQLite file.
_ADDED_COLUMNS: list[tuple[str, str]] = [
    ("card_json", "TEXT"),
    ("card_tier", "TEXT NOT NULL DEFAULT 'legacy'"),
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
    _migrate_columns(conn)
    _seed_builtins(conn)
    _repair_builtin_shows(conn)
    conn.commit()
    return conn


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """Add any of `_ADDED_COLUMNS` missing from an older `characters` table.

    Existing rows get card_json=NULL, card_tier='legacy' via the column
    defaults above — they keep working off persona_prompt alone.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(characters)")}
    for name, ddl_suffix in _ADDED_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE characters ADD COLUMN {name} {ddl_suffix}")


def _repair_builtin_shows(conn: sqlite3.Connection) -> None:
    """Fix built-in rows seeded by an earlier version that swapped source_show
    and intro. Idempotent: restores each built-in's source_show/intro from the
    canonical seed data by key. Harmless once rows are already correct."""
    by_key = {b[0]: b for b in _BUILTINS}  # key -> (key,name,intro,color,hidden,persona)
    rows = conn.execute(
        "SELECT key, source_show, intro FROM characters WHERE is_builtin = 1"
    ).fetchall()
    for row in rows:
        seed = by_key.get(row["key"])
        if not seed:
            continue
        correct_intro = seed[2]
        if row["source_show"] != _BUILTIN_SHOW or row["intro"] != correct_intro:
            conn.execute(
                "UPDATE characters SET source_show = ?, intro = ? WHERE key = ?",
                (_BUILTIN_SHOW, correct_intro, row["key"]),
            )


def _seed_builtins(conn: sqlite3.Connection) -> None:
    """Insert the ten built-ins once. Idempotent via INSERT OR IGNORE on key."""
    now = datetime.now(timezone.utc).isoformat()
    for key, name, intro, color, hidden, persona in _BUILTINS:
        conn.execute(
            "INSERT OR IGNORE INTO characters "
            "(key, display_name, source_show, intro, color, persona_prompt, "
            " is_builtin, hidden, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (key, name, _BUILTIN_SHOW, intro, color, persona,
             1 if hidden else 0, now),
        )


def _row_to_public(row: sqlite3.Row) -> dict:
    """Shape a row for the frontend/pick-screen and the export page.

    Includes persona + source_show because /export builds a portable prompt from
    them; the chat session also reads persona from here. `card` is the parsed
    structured card (None for legacy rows with no card_json) and `card_tier`
    is "legacy" / "starter" / "full" — chat.py uses card_tier to decide whether
    a character needs lazy completion before a session starts.
    """
    raw_card = row["card_json"]
    card = json.loads(raw_card) if raw_card else None
    return {
        "key": row["key"],
        "name": row["display_name"],
        "intro": row["intro"],
        "color": row["color"],
        "hidden": bool(row["hidden"]),
        "is_builtin": bool(row["is_builtin"]),
        "source_show": row["source_show"],
        "persona": row["persona_prompt"],
        "card": card,
        "card_tier": row["card_tier"],
    }


def list_characters(show: str | None = None) -> list[dict]:
    """Characters: built-ins first, then custom ones by creation order.

    `show`, when given, filters to characters whose source_show matches it
    (case/space-insensitive) — used to show only the current show's cast in
    Scene Talk instead of every character ever made.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM characters ORDER BY is_builtin DESC, id ASC"
        ).fetchall()
    chars = [_row_to_public(r) for r in rows]
    if show:
        target = _norm_show(show)
        chars = [c for c in chars if _norm_show(c["source_show"]) == target]
    return chars


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
    card: dict | None = None,
    card_tier: str = "legacy",
) -> dict:
    """Insert a custom character. Key is 'custom_<rowid>'. Returns its public dict.

    `persona` is always the flattened prompt text (teaching template and
    export.js only ever read persona_prompt). `card`/`card_tier` are optional —
    omit them for the old flat-persona flow, pass both when the caller has a
    structured card (card_tier is then "starter" or "full").
    """
    now = datetime.now(timezone.utc).isoformat()
    card_json = json.dumps(card, ensure_ascii=False) if card is not None else None
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO characters "
            "(key, display_name, source_show, intro, color, persona_prompt, "
            " is_builtin, hidden, created_at, card_json, card_tier) "
            "VALUES ('', ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
            (display_name, source_show, intro, color, persona, now,
             card_json, card_tier),
        )
        rowid = cur.lastrowid
        key = f"custom_{rowid}"
        conn.execute("UPDATE characters SET key = ? WHERE id = ?", (key, rowid))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ?", (rowid,)
        ).fetchone()
    return _row_to_public(row)


def update_card(key: str, card: dict, card_tier: str, persona: str) -> dict | None:
    """Overwrite a character's card/card_tier/persona_prompt after lazy completion.

    Used by chat.py when a "starter" card is topped up to "full" the first time
    the character is selected. Returns the updated public dict, or None if the
    key doesn't exist.
    """
    card_json = json.dumps(card, ensure_ascii=False)
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE characters SET card_json = ?, card_tier = ?, persona_prompt = ? "
            "WHERE key = ?",
            (card_json, card_tier, persona, key),
        )
        if cur.rowcount == 0:
            return None
        conn.commit()
        row = conn.execute("SELECT * FROM characters WHERE key = ?", (key,)).fetchone()
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


def flatten_card(display_name: str, card: dict) -> str:
    """Render a structured card into the flat second-person prompt text.

    This is what actually gets stored in persona_prompt and fed to the model at
    chat time (via chat._system_prompt) — so every existing consumer (the
    teaching template, export.js's portable-prompt builder) keeps working
    unchanged, whether the character behind it is legacy or card-based.

    Evidence quotes are NOT dumped verbatim into the prompt — only their
    already-synthesized effect (voice/moves/etc.) is. `confidence:
    "reconstructed"` entries are worded as "the vibe of" rather than presented
    as a fact, per the evidence-integrity rule the generation prompt enforces.
    """
    lines = [f"You are {display_name}."]

    voice = card.get("voice") or {}
    voice_bits = [
        voice.get("pace", ""), voice.get("sentence_length", ""),
        voice.get("vocabulary", ""), voice.get("tone", ""),
        voice.get("emotional_range", ""),
    ]
    voice_bits = [b for b in voice_bits if b]
    if voice_bits:
        lines.append("Voice: " + " ".join(voice_bits))

    moves = card.get("signature_moves") or []
    if moves:
        lines.append("Signature moves you reach for (don't use every one every reply):")
        for m in moves:
            name = m.get("name", "")
            steps = " -> ".join(m.get("steps") or [])
            freq = m.get("frequency", "")
            bit = f"- {name}: {steps}"
            if freq:
                bit += f" (frequency: {freq})"
            lines.append(bit)

    openings = card.get("opening_variants") or []
    if openings:
        lines.append(
            "Ways you tend to kick off a conversation (vary it, don't repeat the "
            "same one every time): " + " / ".join(openings)
        )

    greetings = card.get("signature_greetings") or []
    if greetings:
        lines.append("Signature greetings you can use to open a conversation "
                     "(pick at most one per session, don't force it):")
        for g in greetings:
            setup = g.get("setup", "")
            payoff = g.get("payoff", "")
            conf = g.get("confidence", "")
            # Only high-confidence greetings are actionable at runtime
            if conf == "high":
                lines.append(f"  - Setup: {setup} | Payoff: {payoff}")
            elif conf == "medium":
                lines.append(f"  - (maybe) Setup: {setup} | Payoff: {payoff}")

    fmt = card.get("format_style") or {}
    fmt_bits = [
        fmt.get("caps", ""), fmt.get("bold", ""), fmt.get("ellipsis", ""),
        fmt.get("exclaim", ""), fmt.get("notes", ""),
    ]
    fmt_bits = [b for b in fmt_bits if b]
    if fmt_bits:
        lines.append("Formatting habits: " + " ".join(fmt_bits))

    rel = card.get("relationship_style") or {}
    rel_bits = []
    if rel.get("address_terms"):
        rel_bits.append("You call the learner things like: " + ", ".join(rel["address_terms"]) + ".")
    if rel.get("encouragement_style"):
        rel_bits.append(rel["encouragement_style"])
    if rel.get("teasing_style"):
        rel_bits.append(rel["teasing_style"])
    if rel_bits:
        lines.append("With the learner: " + " ".join(rel_bits))

    avoid = card.get("avoid") or []
    if avoid:
        lines.append("Avoid: " + "; ".join(avoid) + ".")

    return "\n".join(lines)


def pick_color(seed: str) -> str:
    """Deterministic palette color for a new character, keyed off its name."""
    return _PALETTE[sum(ord(c) for c in seed) % len(_PALETTE)]


# Trailing episode markers to strip so a Source like "Modern Family S3E5" (or
# "... S03E05", "... 第3季第5集", "... EP12") reduces to the bare show name.
_EPISODE_RE = re.compile(
    r"[\s\-—·:：|]*"
    r"(?:s\d{1,2}\s*e\d{1,3}"           # S3E5 / S03E05
    r"|season\s*\d+.*"                   # Season 3 ...
    r"|ep(?:isode)?\.?\s*\d+"            # EP12 / episode 12
    r"|第\s*\d+\s*季.*"                  # 第3季...
    r"|第\s*\d+\s*集)"                   # 第5集
    r".*$",
    re.IGNORECASE,
)


def show_from_source(source: str) -> str:
    """Reduce a freeform Source string to just the show name.

    "Modern Family S3E5" -> "Modern Family"; "绝命毒师 第2季第4集" -> "绝命毒师".
    Returns "" for empty input.
    """
    s = (source or "").strip()
    if not s:
        return ""
    return _EPISODE_RE.sub("", s).strip() or s


def _norm_show(s: str) -> str:
    return " ".join((s or "").lower().split())


def find_by_show(show: str) -> dict | None:
    """First character whose source_show matches `show` (case/space-insensitive).

    Built-ins win ties (they sort first), so "Modern Family" resolves to a
    built-in. Returns None when nothing matches.
    """
    target = _norm_show(show)
    if not target:
        return None
    for c in list_characters():
        if _norm_show(c["source_show"]) == target:
            return c
    return None


