"""BingeLingo reviewer — a tiny local web app for reviewing your saved cards.

    python review.py            # then open http://127.0.0.1:5001

The Notion token and proxy stay server-side; the browser only ever sees the
already-flattened card JSON from /api/cards.
"""
from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

from src import chat, config, matching, notion_reader

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


@app.post("/api/check")
def api_check():
    """Judge a typed answer against the target expression, server-side.

    Body: {"guess": "...", "expression": "..."}. Inflection-tolerant matching
    (stemming + helper-word stripping) lives in src.matching so the browser
    doesn't have to reason about English morphology.
    """
    data = request.get_json(silent=True) or {}
    guess = str(data.get("guess", ""))
    expression = str(data.get("expression", ""))
    correct = matching.is_correct(guess, expression)
    return jsonify({"ok": True, "correct": correct})


# ---- 对话练习 (roleplay conversation practice) ----

@app.get("/api/characters")
def api_characters():
    return jsonify({"ok": True, "characters": chat.list_characters()})


@app.post("/api/chat/start")
def api_chat_start():
    data = request.get_json(silent=True) or {}
    character = str(data.get("character", ""))
    try:
        cards = notion_reader.fetch_cards()
        expressions = [c["expression"] for c in cards if c.get("expression")]
        result = chat.start_session(character, expressions)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 — surface to the UI
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **result})


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", ""))
    message = str(data.get("message", ""))
    try:
        result = chat.turn(session_id, message)
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **result})


@app.post("/api/chat/end")
def api_chat_end():
    data = request.get_json(silent=True) or {}
    session_id = str(data.get("session_id", ""))
    try:
        result = chat.end_session(session_id)
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **result})


def main() -> None:
    # Sanity-check required config up front with a clear message.
    _ = config.NOTION_TOKEN, config.NOTION_DATABASE_ID
    print(f"[BingeLingo] Reviewer running →  http://127.0.0.1:{PORT}")
    print("[BingeLingo] Reading live from Notion. Ctrl-C to stop.")
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
