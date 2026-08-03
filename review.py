"""BingeLingo reviewer — a tiny local web app for reviewing your saved cards.

    python review.py            # then open http://127.0.0.1:5001

The Notion token and proxy stay server-side; the browser only ever sees the
already-flattened card JSON from /api/cards.
"""
from __future__ import annotations

import os
import secrets

from flask import (
    Flask,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
)

from src import chat, config, matching, notion_reader, review_log

# Resolve paths from this file's location, never the process CWD: under gunicorn
# on Render the working directory is not guaranteed to be the repo root, so any
# relative "web" path would fail to find the static assets.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")

PORT = 5001

# ---- simple password gate ----
# Single shared password; no accounts. Set APP_PASSWORD in the environment on
# deploy; falls back to the baked-in default for local use.
APP_PASSWORD = os.getenv("APP_PASSWORD", "9713.jiayouYQ")
# Signs the session cookie. Set SECRET_KEY on Render so logins survive restarts
# and are consistent across workers; otherwise a random per-process key is used.
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
# Endpoints reachable without a valid session.
_PUBLIC_PATHS = {"/login", "/favicon.ico"}


def _is_public_static(path: str) -> bool:
    """True if the request targets a real file under web/ (css/js/fonts/etc.).

    These carry no secrets, so the login page can load them before auth. We
    resolve against the actual files on disk rather than a hand-kept suffix
    list, and confine the lookup to WEB_DIR so a crafted path can't escape it.
    Card/character data lives behind /api/ and stays gated.
    """
    rel = path.lstrip("/")
    if not rel:
        return False
    candidate = os.path.normpath(os.path.join(WEB_DIR, rel))
    if os.path.commonpath([candidate, WEB_DIR]) != WEB_DIR:
        return False
    return os.path.isfile(candidate)


@app.before_request
def require_login():
    if session.get("authed"):
        return None
    if request.path in _PUBLIC_PATHS or _is_public_static(request.path):
        return None
    # API callers get a clean 401 so the UI can react; pages redirect to login.
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect("/login")


@app.get("/login")
def login_page():
    if session.get("authed"):
        return redirect("/review")
    return send_from_directory(WEB_DIR, "login.html")


@app.post("/login")
def login_submit():
    data = request.get_json(silent=True) or request.form
    password = str(data.get("password", ""))
    if secrets.compare_digest(password, APP_PASSWORD):
        session["authed"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "密码错误"}), 401


@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/")
def index():
    return redirect("/review")


@app.get("/review")
def page_review():
    return send_from_directory(WEB_DIR, "review.html")


@app.get("/chat")
def page_chat():
    return send_from_directory(WEB_DIR, "chat.html")


@app.get("/export")
def page_export():
    return send_from_directory(WEB_DIR, "export.html")


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


@app.post("/api/review-log")
def api_review_log():
    """Record one review attempt (or skip) to the local SQLite log.

    Recording only — this does not feed any scheduler and never affects which
    cards the reviewer shows. A logging failure must not break the review flow,
    so errors are swallowed with a soft-fail response.
    """
    data = request.get_json(silent=True) or {}
    page_id = str(data.get("page_id", ""))
    expression = str(data.get("expression", ""))
    result = str(data.get("result", ""))
    elapsed = data.get("elapsed_seconds")
    try:
        elapsed_seconds = float(elapsed) if elapsed is not None else None
    except (TypeError, ValueError):
        elapsed_seconds = None
    try:
        review_log.record(page_id, expression, result, elapsed_seconds)
    except Exception as exc:  # noqa: BLE001 — never let logging break review
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True})


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
    # Render (and most PaaS) inject the port to bind on via $PORT; fall back to
    # 5001 for local runs. Bind 0.0.0.0 so the container is reachable.
    port = int(os.getenv("PORT", PORT))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"[BingeLingo] Reviewer running →  http://{host}:{port}")
    print("[BingeLingo] Reading live from Notion. Ctrl-C to stop.")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
