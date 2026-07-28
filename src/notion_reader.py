"""Read learn-worthy expression cards back out of the Notion database.

Mirrors the write side in `notion_writer.py`: the same data-source resolution,
the same proxy handling, the same property names. The reviewer web app calls
`fetch_cards()` to get a plain list of dicts ready to hand to the browser.

Two things worth knowing about the data:

* The screenshot is NOT a property. It lives in the page body as an `image`
  block, so we list each page's children and pull the first image URL. Notion
  file URLs are short-lived signed links, which is fine for a live reader that
  fetches fresh on every page load.
* Mode A ("挖空猜词") needs the target expression blanked out of the example
  line. We precompute that here so the frontend stays dumb. When the expression
  can't be located in the line, `cloze_ok` is False and the frontend silently
  falls back to the中译英 mode for that one card.
"""
from __future__ import annotations

import re

import httpx
from notion_client import Client

from . import config, matching

_NOTION_VERSION = "2025-09-03"

_client_kwargs = {"auth": config.NOTION_TOKEN, "notion_version": _NOTION_VERSION}
if config.HTTPS_PROXY:
    _transport = httpx.HTTPTransport(proxy=config.HTTPS_PROXY, retries=3)
    _client_kwargs["client"] = httpx.Client(transport=_transport, timeout=60)
_client = Client(**_client_kwargs)

_data_source_id: str | None = None

_BLANK = "＿＿＿"  # full-width so it reads clearly against subtitle text


def _resolve_data_source_id() -> str:
    global _data_source_id
    if _data_source_id is None:
        db = _client.databases.retrieve(config.NOTION_DATABASE_ID)
        sources = db.get("data_sources", [])
        if not sources:
            raise RuntimeError(
                "Database has no data sources; check NOTION_DATABASE_ID and sharing."
            )
        _data_source_id = sources[0]["id"]
    return _data_source_id


def _plain_text(prop: dict) -> str:
    """Flatten a title or rich_text property to a plain string."""
    if not prop:
        return ""
    parts = prop.get("title") or prop.get("rich_text") or []
    return "".join(p.get("plain_text", "") for p in parts).strip()


def _first_image_url(page_id: str) -> str:
    """Return the URL of the first image block in the page body, or ''."""
    try:
        resp = _client.blocks.children.list(page_id, page_size=50)
    except Exception:  # noqa: BLE001 — a missing body shouldn't kill the card
        return ""
    for block in resp.get("results", []):
        if block.get("type") != "image":
            continue
        img = block.get("image", {})
        if img.get("type") == "external":
            return img.get("external", {}).get("url", "")
        return img.get("file", {}).get("url", "")
    return ""


def _build_cloze(expression: str, example: str) -> tuple[str, bool]:
    """Blank `expression` out of `example`. Returns (clozed_text, ok).

    Tries a verbatim case-insensitive match first, then a whitespace-tolerant
    match (so "off  your  game" still hits "off your game"). If neither lands,
    ok is False and the caller degrades this card to中译英.
    """
    expr = expression.strip()
    line = example.strip()
    if not expr or not line:
        return line, False

    # 1) Exact, case-insensitive.
    idx = line.lower().find(expr.lower())
    if idx != -1:
        return line[:idx] + _BLANK + line[idx + len(expr):], True

    # 2) Whitespace-tolerant: match the expression's words with flexible gaps,
    #    anchored on word boundaries so we don't blank a substring mid-word.
    words = [re.escape(w) for w in expr.split()]
    if words:
        pattern = r"\b" + r"\s+".join(words) + r"\b"
        m = re.search(pattern, line, flags=re.IGNORECASE)
        if m:
            return line[: m.start()] + _BLANK + line[m.end():], True

    return line, False


def _build_review_prompt(
    review_sentence: str, expression: str, example: str
) -> tuple[str, str]:
    """Decide what the learner sees at layer 1 and how to answer it.

    Returns (prompt_text, prompt_kind) where kind is:
      * "cloze"  — a sentence with a ＿＿＿ blank to fill in
      * "zh2en"  — no usable sentence to blank, so recall from Chinese instead

    Preference order per the design's fallback rules:
      1. ReviewSentence containing ___  → swap ___ for the display blank.
      2. ReviewSentence with no ___      → can't blank it, degrade to zh2en.
      3. No ReviewSentence               → blank the expression out of Example.
      4. Neither works                   → zh2en.
    """
    rs = (review_sentence or "").strip()
    if rs:
        if "___" in rs:
            # Collapse any run of 3+ underscores into one display blank.
            return re.sub(r"_{3,}", _BLANK, rs), "cloze"
        return "", "zh2en"

    clozed, ok = _build_cloze(expression, example)
    if ok:
        return clozed, "cloze"
    return "", "zh2en"


def _page_to_card(page: dict) -> dict:
    props = page.get("properties", {})
    expression = _plain_text(props.get("Expression"))
    example = _plain_text(props.get("Example"))
    review_sentence = _plain_text(props.get("ReviewSentence"))

    review_prompt, review_kind = _build_review_prompt(
        review_sentence, expression, example
    )
    return {
        "id": page.get("id", ""),
        "expression": expression,
        "chinese": _plain_text(props.get("Chinese")),
        "context": _plain_text(props.get("Context")),
        "example": example,
        "difficulty": _plain_text(props.get("Difficulty")),
        "source": _plain_text(props.get("Source")),
        "image_url": _first_image_url(page.get("id", "")),
        # Raw stored sentence (empty on old cards) — used by the backfill script.
        "review_sentence": review_sentence,
        # Layer 1: the new-context challenge.
        "review_prompt": review_prompt,
        "review_kind": review_kind,
        # Layer 2 hints (generated server-side).
        "initials_hint": matching.initials_hint(expression),
        # Layer 3 extras.
        "common_structure": matching.common_structure(expression, example),
    }


def fetch_cards() -> list[dict]:
    """Query every page in the data source and return review-ready cards.

    Newest first. Cards missing an Expression are skipped as unreviewable.
    """
    source_id = _resolve_data_source_id()
    cards: list[dict] = []
    cursor: str | None = None
    while True:
        kwargs = {
            "data_source_id": source_id,
            "page_size": 100,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _client.data_sources.query(**kwargs)
        for page in resp.get("results", []):
            card = _page_to_card(page)
            if card["expression"]:
                cards.append(card)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return cards
