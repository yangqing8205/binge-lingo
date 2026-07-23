"""BingeLingo reviewer — a tiny local web app for reviewing your saved cards.

    python review.py            # then open http://127.0.0.1:5001

The Notion token and proxy stay server-side; the browser only ever sees the
already-flattened card JSON from /api/cards.
"""
from __future__ import annotations

from flask import Flask, jsonify, send_from_directory

from src import config, notion_reader

app = Flask(__name__, static_folder="web", static_url_path="")

PORT = 5001


@app.get("/")
def index():
    return send_from_directory("web", "index.html")


@app.get("/api/cards")
def api_cards():
    try:
        cards = notion_reader.fetch_cards()
    except Exception as exc:  # noqa: BLE001 — surface the reason to the UI
        return jsonify({"ok": False, "error": str(exc), "cards": []}), 502
    return jsonify({"ok": True, "count": len(cards), "cards": cards})


def main() -> None:
    # Sanity-check required config up front with a clear message.
    _ = config.NOTION_TOKEN, config.NOTION_DATABASE_ID
    print(f"[BingeLingo] Reviewer running →  http://127.0.0.1:{PORT}")
    print("[BingeLingo] Reading live from Notion. Ctrl-C to stop.")
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
