"""Make a screenshot publicly viewable inside Notion.

Two strategies:
  * "notion" (default): upload the file straight to Notion via its File Upload
    API, then reference it by upload id. No third-party host needed.
  * "imgur": upload anonymously to Imgur and return a public URL.
"""
from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path

import requests

from . import config

_NOTION_VERSION = "2022-06-28"
_NOTION_API = "https://api.notion.com/v1"

# Route Notion (and imgur) traffic through the proxy when configured.
_PROXIES = (
    {"http": config.HTTPS_PROXY, "https": config.HTTPS_PROXY}
    if config.HTTPS_PROXY
    else None
)


def _post_with_retry(*args, tries: int = 4, **kwargs):
    """Old LibreSSL on this machine drops TLS intermittently; retry on SSLError."""
    last = None
    for _ in range(tries):
        try:
            return requests.post(*args, **kwargs)
        except requests.exceptions.SSLError as exc:
            last = exc
            time.sleep(1)
    raise last


def _upload_to_imgur(path: Path) -> dict:
    if not config.IMGUR_CLIENT_ID:
        raise RuntimeError("IMAGE_HOST=imgur but IMGUR_CLIENT_ID is not set in .env")
    data = base64.b64encode(path.read_bytes())
    resp = _post_with_retry(
        "https://api.imgur.com/3/image",
        headers={"Authorization": f"Client-ID {config.IMGUR_CLIENT_ID}"},
        data={"image": data, "type": "base64"},
        timeout=60,
        proxies=_PROXIES,
    )
    resp.raise_for_status()
    link = resp.json()["data"]["link"]
    return {"kind": "external", "url": link}


def _upload_to_notion(path: Path) -> dict:
    """Notion's direct file upload flow: create an upload, send bytes, return id."""
    headers = {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": _NOTION_VERSION,
    }
    # Step 1: create a file upload object.
    create = _post_with_retry(
        f"{_NOTION_API}/file_uploads",
        headers={**headers, "Content-Type": "application/json"},
        json={"filename": path.name},
        timeout=60,
        proxies=_PROXIES,
    )
    create.raise_for_status()
    upload_id = create.json()["id"]

    # Step 2: send the raw bytes. Notion requires the correct content type on the
    # multipart part, not just the filename.
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    with path.open("rb") as fh:
        send = _post_with_retry(
            f"{_NOTION_API}/file_uploads/{upload_id}/send",
            headers=headers,
            files={"file": (path.name, fh, mime)},
            timeout=120,
            proxies=_PROXIES,
        )
    send.raise_for_status()
    return {"kind": "file_upload", "id": upload_id}


def upload_image(path: Path) -> dict:
    """Return a descriptor the notion_writer knows how to embed.

    Descriptor is one of:
      {"kind": "external", "url": <str>}
      {"kind": "file_upload", "id": <str>}
    """
    if config.IMAGE_HOST == "imgur":
        return _upload_to_imgur(path)
    return _upload_to_notion(path)
