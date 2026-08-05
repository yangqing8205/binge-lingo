"""One-off backfill: split legacy Source into Show + Episode.

Old cards only ever had a single Source field (e.g. "绝命毒师" or
"Modern Family S3E5"). The Show/Episode split is newer, so those cards have
Show empty even though the literal show name was already sitting in Source
the whole time — no guessing needed, just move it over:

  * If Source ends in an episode-shaped suffix (S3E5, s3e5, S03E05, 3x05 —
    case-insensitive), that suffix becomes Episode and the trimmed remainder
    becomes Show.
  * Otherwise the whole Source string becomes Show; Episode stays blank.
  * Show is case-normalized (title-cased) so "Modern Family" and
    "modern family" collapse into one dropdown entry instead of two.

Only touches cards where Show is empty and Source is non-empty — cards that
already have a Show, or have neither, are left alone.

Usage:
    python backfill_show_episode.py            # dry run: print what it would do
    python backfill_show_episode.py --apply    # actually update Notion
"""
from __future__ import annotations

import argparse
import re
import sys

from src import notion_reader

# Trailing episode-shaped suffix: S3E5 / s3e5 / S03E05, or 3x05. Anchored to
# the end of the string so it only strips a real trailing marker, not an
# "S3E5"-looking substring in the middle of a title.
_EPISODE_SUFFIX_RE = re.compile(
    r"^(?P<show>.*?)"
    r"[\s\-—·:：|]*"
    r"(?P<episode>(?:[Ss]\d{1,2}[Ee]\d{1,3})|(?:\d{1,2}[xX]\d{1,3}))"
    r"\s*$"
)


def _title_case(show: str) -> str:
    """Case-normalize for dedup. Title-cases ASCII words; a no-op on CJK text
    (no per-character casing there, so "绝命毒师" round-trips unchanged)."""
    return " ".join(w[:1].upper() + w[1:] if w[:1].isalpha() else w for w in show.split())


def parse_source(source: str) -> tuple[str, str]:
    """(show, episode) parsed from a legacy Source string. Episode is "" when
    no episode-shaped suffix is found — the whole string becomes Show then."""
    s = (source or "").strip()
    if not s:
        return "", ""
    m = _EPISODE_SUFFIX_RE.match(s)
    if m and m.group("show").strip():
        return _title_case(m.group("show").strip()), m.group("episode")
    return _title_case(s), ""


def _needs_backfill(card: dict) -> bool:
    return not (card.get("show") or "").strip() and bool((card.get("source") or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Show/Episode from legacy Source.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write parsed Show/Episode back to Notion (default: dry run).",
    )
    args = parser.parse_args()

    print("[backfill] Reading cards from Notion…")
    try:
        cards = notion_reader.fetch_cards()
    except Exception as exc:  # noqa: BLE001 — surface the reason and stop
        print(f"[backfill] Failed to read Notion: {exc}")
        sys.exit(1)

    todo = [c for c in cards if _needs_backfill(c)]
    print(f"[backfill] {len(cards)} card(s) total, {len(todo)} need backfill "
          f"(Show empty, Source set).\n")

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"=== {mode} — {len(todo)} card(s) ===")
    for card in todo:
        source = card.get("source", "")
        show, episode = parse_source(source)
        arrow = f"{source!r} -> Show={show!r}, Episode={episode!r}"
        print(f"  • {arrow}")
        if args.apply:
            notion_writer.update_show_episode(card["id"], show, episode)

    if not args.apply:
        print("\n[backfill] Dry run — nothing written. Re-run with --apply to update Notion.")
        return

    print(f"\n[backfill] Done — updated {len(todo)} card(s).")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        from src import notion_writer  # noqa: F401 — only needed for --apply
    main()
