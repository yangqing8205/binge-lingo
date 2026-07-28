"""One-off backfill: give old Notion cards a ReviewSentence.

Cards saved before the three-layer reviewer landed have an empty ReviewSentence
and fall back to blanking the original Example line — a weaker review. This
script finds those cards, generates a fresh new-context cloze sentence from each
card's existing fields, and (with --apply) writes it back to Notion.

    python backfill_review_sentence.py            # dry run: print what it would do
    python backfill_review_sentence.py --apply    # actually update Notion
"""
from __future__ import annotations

import argparse
import sys

from src import notion_reader, notion_writer, vision


def _needs_backfill(card: dict) -> bool:
    return bool(card.get("expression", "").strip()) and not card.get(
        "review_sentence", ""
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill empty ReviewSentence cards.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write generated sentences back to Notion (default: dry run).",
    )
    args = parser.parse_args()

    print("[backfill] Reading cards from Notion…")
    try:
        cards = notion_reader.fetch_cards()
    except Exception as exc:  # noqa: BLE001 — surface the reason and stop
        print(f"[backfill] Failed to read Notion: {exc}")
        sys.exit(1)

    todo = [c for c in cards if _needs_backfill(c)]
    print(f"[backfill] {len(cards)} card(s) total, {len(todo)} missing ReviewSentence.")
    if not todo:
        print("[backfill] Nothing to do.")
        return

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[backfill] Mode: {mode}\n")

    generated: list[tuple[dict, str]] = []
    skipped = 0
    for card in todo:
        expr = card["expression"]
        try:
            sentence = vision.generate_review_sentence(
                expression=expr,
                context=card.get("context", ""),
                chinese=card.get("chinese", ""),
                example=card.get("example", ""),
            )
        except Exception as exc:  # noqa: BLE001 — keep the batch going
            print(f"  ! [{expr}] generation error: {exc}")
            skipped += 1
            continue

        if not sentence:
            print(f"  · [{expr}] model returned no usable sentence (no ___), skipped")
            skipped += 1
            continue

        print(f"  • {expr}\n      → {sentence}")
        generated.append((card, sentence))

    print(f"\n[backfill] Generated {len(generated)} OK, skipped {skipped}.")

    if not args.apply:
        print("[backfill] Dry run — nothing written. Re-run with --apply to update Notion.")
        return

    print("\n[backfill] Writing to Notion…")
    written = 0
    for card, sentence in generated:
        expr = card["expression"]
        try:
            notion_writer.update_review_sentence(card["id"], sentence)
            print(f"  ✓ {expr}")
            written += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {expr}: {exc}")

    print(f"\n[backfill] Updated {written}/{len(generated)} card(s) in Notion.")


if __name__ == "__main__":
    main()
