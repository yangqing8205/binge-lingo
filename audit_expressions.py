"""One-off audit: flag Notion Expression values that look non-standard.

READ-ONLY. Reads every card from Notion and prints two kinds of suspects for
manual review — it never edits anything:

  1. Inflected form  — the Expression contains a word ending in -ing/-ed that
     looks like a tensed verb (should be a dictionary base form, e.g.
     "playing craps" → "play craps"). A small stoplist filters obvious
     non-verbs (thing, morning, red, …) to cut noise.

  2. Suspicious word order — a separable phrasal verb whose particle sits right
     after the verb with the object AFTER it (e.g. "let down one's hair"), when
     the idiomatic form puts the object in the middle ("let one's hair down").

Usage:
    python audit_expressions.py

You confirm and fix anything by hand in Notion; this tool only reports.
"""
from __future__ import annotations

import re
import sys

from src import notion_reader

# Particles that participate in separable phrasal verbs.
_PARTICLES = {
    "up", "down", "out", "off", "in", "on", "over", "away", "back",
    "through", "around", "along", "apart", "aside", "under",
}

# Determiners/possessives that begin an object noun phrase. If one of these
# follows "<verb> <particle>", the object is trailing — the suspicious order.
_OBJECT_STARTERS = {
    "one's", "ones", "sb.'s", "his", "her", "their", "your", "my", "our", "its",
    "the", "a", "an", "this", "that", "these", "those",
}

# -ing/-ed words that are NOT inflected verbs, so we don't flag them.
_ING_ED_STOPLIST = {
    # -ing nouns / adjectives
    "thing", "things", "something", "anything", "nothing", "everything",
    "morning", "evening", "ceiling", "string", "spring", "wing", "ring",
    "king", "sibling", "ding", "bling", "inning", "belongings", "surroundings",
    "feelings", "winning", "darling", "sterling", "herring", "ceiling", "viking",
    "pudding", "building", "clothing", "lightning", "outing",
    # -ed adjectives / non-verb nouns
    "red", "bed", "bread", "dead", "ahead", "instead", "bored", "tired",
    "hundred", "wicked", "naked", "sacred", "shed", "wed", "fed", "bled",
    "need", "indeed", "seed", "weed", "greed", "speed", "breed", "creed",
    "bed", "led",
}


def _looks_inflected(word: str) -> bool:
    """True if `word` looks like a tensed/-ing verb form we'd want normalized."""
    w = word.lower().strip(".,!?;:'\"()")
    if w in _ING_ED_STOPLIST:
        return False
    if len(w) <= 4:  # too short to safely call an inflected verb (red, bed, ring)
        return False
    return w.endswith("ing") or w.endswith("ed")


def _inflected_hits(expression: str) -> list[str]:
    return [w for w in expression.split() if _looks_inflected(w)]


def _bad_word_order(expression: str) -> str | None:
    """If a separable phrasal verb has a trailing object, describe the suspicion.

    Pattern: <verb> <particle> <object-starter> …  → the object should sit
    between the verb and the particle. Returns a short note, or None.
    """
    toks = [t.lower().strip(".,!?;:\"()") for t in expression.split()]
    if len(toks) < 3:
        return None
    for i in range(len(toks) - 2):
        verb, particle, after = toks[i], toks[i + 1], toks[i + 2]
        if particle in _PARTICLES and after in _OBJECT_STARTERS:
            # Suggest the middle-object form: verb + <object…> + particle.
            obj = " ".join(toks[i + 2:])
            return (
                f'"{verb} {particle} {obj}" — object trails the particle; '
                f'separable form is likely "{verb} {obj} {particle}"'
            )
    return None


def main() -> None:
    print("[audit] Reading cards from Notion…")
    try:
        cards = notion_reader.fetch_cards()
    except Exception as exc:  # noqa: BLE001 — surface the reason and stop
        print(f"[audit] Failed to read Notion: {exc}")
        sys.exit(1)

    inflected: list[tuple[str, list[str]]] = []
    word_order: list[tuple[str, str]] = []
    for card in cards:
        expr = (card.get("expression") or "").strip()
        if not expr:
            continue
        hits = _inflected_hits(expr)
        if hits:
            inflected.append((expr, hits))
        note = _bad_word_order(expr)
        if note:
            word_order.append((expr, note))

    print(f"[audit] {len(cards)} card(s) total.\n")

    print(f"=== Inflected forms (-ing/-ed verbs to normalize): {len(inflected)} ===")
    if not inflected:
        print("  (none)")
    for expr, hits in inflected:
        print(f"  • {expr!r}   ← {', '.join(hits)}")

    print(f"\n=== Suspicious phrasal-verb word order: {len(word_order)} ===")
    if not word_order:
        print("  (none)")
    for expr, note in word_order:
        print(f"  • {expr!r}\n      {note}")

    print(
        "\n[audit] Read-only — nothing changed. Review the lists above and fix "
        "any real cases by hand in Notion."
    )


if __name__ == "__main__":
    main()
