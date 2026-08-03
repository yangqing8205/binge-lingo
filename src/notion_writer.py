"""Write an analyzed screenshot into the configured Notion database.

Notion's newer API (version 2025-09-03) splits a database into a container plus
one or more *data sources*; pages are created under a `data_source_id` parent.
We resolve that id once from the database, then create one row per expression.
"""
from __future__ import annotations

from pathlib import Path

import httpx
from notion_client import Client

from . import config, uploader
from .models import Expression, ScreenshotAnalysis

_NOTION_VERSION = "2025-09-03"

_client_kwargs = {"auth": config.NOTION_TOKEN, "notion_version": _NOTION_VERSION}
if config.HTTPS_PROXY:
    # retries handles the intermittent TLS EOF from this machine's old LibreSSL.
    _transport = httpx.HTTPTransport(proxy=config.HTTPS_PROXY, retries=3)
    _client_kwargs["client"] = httpx.Client(transport=_transport, timeout=60)
_client = Client(**_client_kwargs)

_data_source_id: str | None = None


def _resolve_data_source_id() -> str:
    """The parent for page creation is the database's first data source."""
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


_schema_checked = False


def _ensure_review_sentence_property() -> None:
    """Add rich_text properties the writer sets, if the schema lacks them.

    Notion rejects page creates that set an unknown property, so a fresh
    database (created before a field existed) needs it added once. Covers
    ReviewSentence, Source, and CommonStructure. Idempotent and cached per process.
    """
    global _schema_checked
    if _schema_checked:
        return
    source_id = _resolve_data_source_id()
    ds = _client.data_sources.retrieve(source_id)
    props = ds.get("properties", {})
    missing = {
        name: {"rich_text": {}}
        for name in ("ReviewSentence", "Source", "CommonStructure")
        if name not in props
    }
    if missing:
        _client.data_sources.update(data_source_id=source_id, properties=missing)
    _schema_checked = True


def _rich_text(content: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]}


def _title(content: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": content[:2000]}}]}


def _image_block(descriptor: dict) -> dict:
    if descriptor["kind"] == "external":
        return {
            "type": "image",
            "image": {"type": "external", "external": {"url": descriptor["url"]}},
        }
    return {
        "type": "image",
        "image": {"type": "file_upload", "file_upload": {"id": descriptor["id"]}},
    }


def _properties(expr: Expression, screenshot_name: str, source: str = "") -> dict:
    props = {
        "Expression": _title(expr.expression),
        "Chinese": _rich_text(expr.meaning_zh),
        "Context": _rich_text(expr.scenario_zh),
        "Difficulty": _rich_text(expr.difficulty),
        "Example": _rich_text(expr.original_line),
        "ReviewSentence": _rich_text(expr.review_sentence),
        "Screenshot": _rich_text(screenshot_name),
    }
    # Only set CommonStructure when the model gave a real frame; empty means the
    # expression is fixed, so leave the property unset rather than storing "".
    if expr.common_structure:
        props["CommonStructure"] = _rich_text(expr.common_structure)
    # Only set Source when the watch session provided one; otherwise leave it
    # unset so the field stays empty and can be filled in by hand as before.
    if source:
        props["Source"] = _rich_text(source)
    return props


def write_entry(
    analysis: ScreenshotAnalysis, screenshot_path: Path, source: str = ""
) -> list[str]:
    """Create one row per expression. Returns the created page URLs.

    `source` (e.g. "Modern Family S3E5") is stamped onto every row when set;
    empty means the Source field is left blank.
    """
    _ensure_review_sentence_property()
    parent = {"type": "data_source_id", "data_source_id": _resolve_data_source_id()}
    urls: list[str] = []

    for expr in analysis.expressions:
        # Upload the image per row. A Notion file_upload id can only be attached
        # once, so each page needs its own upload.
        descriptor = uploader.upload_image(screenshot_path)
        page = _client.pages.create(
            parent=parent,
            properties=_properties(expr, screenshot_path.name, source),
            children=[_image_block(descriptor)],
        )
        urls.append(page.get("url", page.get("id", "")))

    return urls


def update_review_sentence(page_id: str, sentence: str) -> None:
    """Set the ReviewSentence property on an existing page (backfill path)."""
    _ensure_review_sentence_property()
    _client.pages.update(
        page_id=page_id,
        properties={"ReviewSentence": _rich_text(sentence)},
    )
