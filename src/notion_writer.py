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


def _properties(expr: Expression, screenshot_name: str) -> dict:
    return {
        "Expression": _title(expr.expression),
        "Chinese": _rich_text(expr.meaning_zh),
        "Context": _rich_text(expr.scenario_zh),
        "Difficulty": _rich_text(expr.difficulty),
        "Example": _rich_text(expr.original_line),
        # Source left empty on purpose — filled in manually.
        "Screenshot": _rich_text(screenshot_name),
    }


def write_entry(analysis: ScreenshotAnalysis, screenshot_path: Path) -> list[str]:
    """Create one row per expression. Returns the created page URLs."""
    parent = {"type": "data_source_id", "data_source_id": _resolve_data_source_id()}
    urls: list[str] = []

    for expr in analysis.expressions:
        # Upload the image per row. A Notion file_upload id can only be attached
        # once, so each page needs its own upload.
        descriptor = uploader.upload_image(screenshot_path)
        page = _client.pages.create(
            parent=parent,
            properties=_properties(expr, screenshot_path.name),
            children=[_image_block(descriptor)],
        )
        urls.append(page.get("url", page.get("id", "")))

    return urls
