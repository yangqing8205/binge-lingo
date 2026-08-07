"""BingeLingo reviewer — a tiny local web app for reviewing your saved cards.

    python review.py            # then open http://127.0.0.1:5001

The Notion token and proxy stay server-side; the browser only ever sees the
already-flattened card JSON from /api/cards.
"""
from __future__ import annotations

import logging
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
from openai import APITimeoutError

from src import characters, chat, config, matching, notion_reader, review_log, settings

# Logs go to stderr, which Render captures. gunicorn also runs at INFO, so these
# land in the deploy log where you can read why a character generation failed.
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bingelingo")

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


@app.errorhandler(Exception)
def _json_errors_for_api(exc):
    """Any unhandled error under /api/* returns JSON, never Flask's HTML page.

    Without this, an exception in an API handler yields a text/html 500 starting
    with '<!doctype', which the frontend then fails to JSON.parse. Non-API routes
    keep their normal rendering: HTTPExceptions (404, etc.) are returned as-is and
    genuine crashes fall through to Flask's default 500.
    """
    from werkzeug.exceptions import HTTPException

    if request.path.startswith("/api/"):
        code = exc.code if isinstance(exc, HTTPException) else 500
        return jsonify({"ok": False, "error": str(exc)}), code
    if isinstance(exc, HTTPException):
        return exc  # render the normal HTML error page for this status
    raise exc  # genuine unexpected error on a page route → default 500


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
    """Cards for the reviewer. `?show=` filters to that show; omitted = all.

    The frontend is expected to pass the current_show value it read from
    /api/current-show — this endpoint doesn't infer a show on its own.
    """
    show = request.args.get("show", "").strip()
    try:
        cards = notion_reader.fetch_cards(show=show or None)
    except Exception as exc:  # noqa: BLE001 — surface the reason to the UI
        return jsonify({"ok": False, "error": str(exc), "cards": []}), 502
    return jsonify({"ok": True, "count": len(cards), "cards": cards})


# ---- 当前剧集 (the single source of truth every tab filters by) ----

@app.get("/api/current-show")
def api_current_show_get():
    return jsonify({"ok": True, "show": settings.get_current_show()})


@app.post("/api/current-show")
def api_current_show_set():
    data = request.get_json(silent=True) or {}
    show = str(data.get("show", ""))
    saved = settings.set_current_show(show)
    return jsonify({"ok": True, "show": saved})


@app.get("/api/shows")
def api_shows():
    """Distinct Show values seen in Notion, for the switcher's dropdown."""
    try:
        shows = notion_reader.list_shows()
    except Exception as exc:  # noqa: BLE001 — surface the reason to the UI
        return jsonify({"ok": False, "error": str(exc), "shows": []}), 502
    return jsonify({"ok": True, "shows": shows})


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


@app.get("/api/word-history")
def api_word_history():
    """Practice history for one expression (the reveal-block word-history).

    Read-only over the local log; returns {history: null} when the page has no
    attempts yet so the UI can hide the block.
    """
    page_id = request.args.get("page_id", "")
    return jsonify({"ok": True, "history": review_log.history(page_id)})


@app.get("/api/today-count")
def api_today_count():
    """Attempts recorded so far today — the top-bar TODAY counter. Count only.

    `?show=` scopes the count to that show's cards (the review log itself has
    no show column, so we resolve the current show's page ids from Notion
    first). Omitted = count across all shows.
    """
    show = request.args.get("show", "").strip()
    if show:
        try:
            page_ids = {c["id"] for c in notion_reader.fetch_cards(show=show)}
        except Exception:  # noqa: BLE001 — counter is non-critical, fail soft
            return jsonify({"ok": True, "count": 0})
        return jsonify({"ok": True, "count": review_log.today_count(page_ids)})
    return jsonify({"ok": True, "count": review_log.today_count()})


# ---- 对话练习 (roleplay conversation practice) ----

@app.get("/api/characters")
def api_characters():
    """`?show=` filters to that show's cast; omitted = every character."""
    show = request.args.get("show", "").strip()
    return jsonify({"ok": True, "characters": chat.list_characters(show=show or None)})


@app.post("/api/characters")
def api_characters_create():
    """Generate a custom character's persona and persist it.

    Body: {show, character, note?}. The model writes only the persona layer;
    teaching rules come from the shared template. Returns the new character.
    """
    data = request.get_json(silent=True) or {}
    show = str(data.get("show", "")).strip()
    character = str(data.get("character", "")).strip()
    note = str(data.get("note", "")).strip()
    if not show or not character:
        return jsonify({"ok": False, "error": "剧名和角色名都要填。"}), 400
    try:
        persona = chat.generate_persona(show, character, note)
        # Persist inside the try too: a DB write failure must still return JSON,
        # not Flask's default HTML 500 (which breaks the frontend's JSON parse).
        color = characters.pick_color(persona["display_name"] or character)
        created = characters.add(
            source_show=show,
            display_name=persona["display_name"] or character,
            intro=persona["intro"],
            color=color,
            persona=persona["persona"],
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI as JSON
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, "character": created})


_CAST_TARGET = 6  # eventual cast size per show
_CAST_BATCH_SIZE = 3  # keep each Ark call safely below Gunicorn's timeout


@app.post("/api/characters/for-show")
def api_characters_for_show():
    """Auto-generate (or top up) a show's main cast, then persist the new ones.

    Idempotent per show: if the show already has >= _CAST_TARGET characters,
    this is a no-op that just returns them. Otherwise it generates enough new
    ones, in one model call, to bring the show's cast up toward that target —
    any characters the show already has (e.g. a single manually-added one)
    count toward the target rather than being duplicated.
    """
    data = request.get_json(silent=True) or {}
    show = characters.show_from_source(str(data.get("show", "")))
    if not show:
        return jsonify({"ok": False, "error": "没有识别到剧名。"}), 400

    existing = characters.list_characters(show=show)
    if len(existing) >= _CAST_TARGET:
        log.info("for-show: show=%r already has %d characters, skipping",
                 show, len(existing))
        return jsonify({"ok": True, "characters": existing, "created": []})

    log.info("for-show: generating cast top-up for show=%r (%d existing)",
             show, len(existing))
    try:
        existing_keys = {c["key"] for c in existing}
        same_names = [c["name"] for c in existing]
        other_names = [c["name"] for c in characters.list_characters()
                       if c["key"] not in existing_keys]
        requested_count = min(_CAST_BATCH_SIZE, _CAST_TARGET - len(existing))
        personas = chat.generate_cast_for_show(
            show,
            same_names,
            other_names,
            requested_count=requested_count,
        )
        created = []
        for persona in personas:
            color = characters.pick_color(persona["display_name"] or show)
            created.append(characters.add(
                source_show=show,
                display_name=persona["display_name"] or show,
                intro=persona["intro"],
                color=color,
                persona=persona["persona"],
            ))
    except ValueError as exc:
        log.warning("for-show: bad input for show=%r: %s", show, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except APITimeoutError:
        log.warning("for-show: Ark timed out for show=%r", show)
        return jsonify({"ok": False, "error": "角色生成超时，请稍后重试。"}), 504
    except Exception as exc:  # noqa: BLE001 — surface to the UI as JSON
        # Full traceback to the deploy log so silent generation failures (gateway
        # errors, tool-call parsing, DB writes) are diagnosable.
        log.exception("for-show: generation failed for show=%r", show)
        return jsonify({"ok": False, "error": str(exc)}), 502
    log.info("for-show: created %d character(s) for show=%r", len(created), show)
    return jsonify({"ok": True, "characters": existing + created, "created": created})


@app.delete("/api/characters/<key>")
def api_characters_delete(key: str):
    """Delete a custom character. Built-ins are protected (400)."""
    if characters.delete(key):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "内置角色不可删除，或角色不存在。"}), 400


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


@app.get("/api/debug/ark-key")
def api_debug_ark_key():
    """TEMPORARY diagnostic — delete once the Render/Ark 401 is root-caused.

    Reports what this process actually read from the environment for the Ark
    credentials. Reads os.environ directly (not src.config, which .strip()s
    values) so a stray leading/trailing space, quote, or newline picked up
    from the Render dashboard shows up instead of being silently cleaned.
    Not linked from any page; still sits behind the same login gate as the
    rest of /api/* (see require_login above), so it isn't publicly reachable.
    """
    raw_key = os.environ.get("API_KEY", "")
    raw_base = os.environ.get("API_BASE_URL", "")
    raw_model = os.environ.get("API_MODEL", "")

    def _edge_repr(s: str, n: int = 6) -> dict:
        return {"first": repr(s[:n]), "last": repr(s[-n:]) if len(s) > n else ""}

    return jsonify({
        "ok": True,
        "api_key": {"length": len(raw_key), **_edge_repr(raw_key)},
        "api_base_url": {"value": raw_base, "repr": repr(raw_base)},
        "api_model": {"value": raw_model, "repr": repr(raw_model)},
        # Sanity check in case the wrong variable names were filled in on Render.
        "unexpected_ark_prefixed_vars_present": {
            "ARK_API_KEY": "ARK_API_KEY" in os.environ,
            "ARK_BASE_URL": "ARK_BASE_URL" in os.environ,
            "ARK_MODEL": "ARK_MODEL" in os.environ,
        },
    })


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
