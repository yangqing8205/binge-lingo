"""One-off audit: how many cards are missing the Show field.

READ-ONLY. Deliberately does NOT guess a show for empty-Show cards — a wrong
guess is worse than a blank field, so this only reports counts and existing
Show values for you to review by hand.

Usage:
    python audit_show_field.py
"""
from __future__ import annotations

import sys
from collections import Counter

from src import notion_reader


def main() -> None:
    print("[audit] Reading cards from Notion…")
    try:
        cards = notion_reader.fetch_cards()
    except Exception as exc:  # noqa: BLE001 — surface the reason and stop
        print(f"[audit] Failed to read Notion: {exc}")
        sys.exit(1)

    total = len(cards)
    with_show = [c for c in cards if (c.get("show") or "").strip()]
    without_show = total - len(with_show)

    print(f"\n[audit] {total} card(s) total.")
    print(f"  Show set:   {len(with_show)}")
    print(f"  Show empty: {without_show}")

    counts = Counter((c.get("show") or "").strip() for c in with_show)
    print(f"\n=== Distinct Show values: {len(counts)} ===")
    if not counts:
        print("  (none)")
    for show, n in counts.most_common():
        print(f"  • {show!r}   {n} card(s)")

    # Cards with a Source but no Show are the old-format rows this migration
    # is meant to leave alone — surfaced separately so they're easy to spot.
    legacy = [
        c for c in cards
        if (c.get("source") or "").strip() and not (c.get("show") or "").strip()
    ]
    print(f"\n=== Old-format cards (Source set, Show empty): {len(legacy)} ===")
    for c in legacy[:20]:
        print(f"  • {c['source']!r}")
    if len(legacy) > 20:
        print(f"  … and {len(legacy) - 20} more")

    print(
        "\n[audit] Read-only — nothing changed. Show-empty cards stay empty on "
        "purpose; fill them in by hand in Notion if you want them under a show."
    )


if __name__ == "__main__":
    main()
