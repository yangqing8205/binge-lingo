"""Roleplay conversation practice — the "对话练习" mode.

The learner picks one of ten characters; the model stays in that character's
voice and naturally steers the chat so the learner gets openings to USE a few of
their saved expressions (rather than just recognizing them). At the end the model
drops character and grades which target expressions actually came out.

Sessions live in a plain in-memory dict — this is a single-user local tool, so no
database. Everything model-facing reuses the same OpenAI-compatible client and
config as vision.py.
"""
from __future__ import annotations

import json
import random
import uuid

from openai import OpenAI

from . import characters, config, matching

_client = OpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)


# --- teaching template ------------------------------------------------------
# The shared tutoring rules, hardcoded once and reused by EVERY character
# (built-in or user-made). A character contributes only its persona; this
# template is appended to build the full system prompt. Editing how the tutor
# behaves — how it draws out targets, never leaks them, corrects, keeps replies
# short — is a one-place change here. `{targets}` is filled at session start.
_TEACHING_TEMPLATE = (
    "You are chatting with an English learner to help them PRACTICE speaking. "
    "Today's target expressions are: {targets}.\n"
    "Your job: stay fully in character and steer the conversation so the learner "
    "gets natural openings to USE these expressions themselves. NEVER tell them "
    "which words to use or say things like 'please use X'. Create situations and "
    "ask questions that invite the expression instead. Keep each reply short and "
    "conversational (1-4 sentences, in your voice) so it feels like a real "
    "back-and-forth. If the learner clearly misuses one of the target "
    "expressions, gently correct them while staying in character. If several "
    "turns pass and a target still hasn't come up, make an opening for it more "
    "obvious — but still in character."
)


# --- persona generation -----------------------------------------------------
# Builds the PERSONA layer for a user-requested character (teaching rules stay
# in the template above). No web access on this gateway — the model relies on
# its own knowledge; for obscure characters it may invent, which is acceptable.
_PERSONA_SYSTEM_PROMPT = """\
You design a roleplay PERSONA for an English-conversation practice app. Given a
show and a character from it, you produce a punchy persona the app can speak as.
You do NOT write teaching rules — the app adds those separately.

Return your result by calling the `report_persona` tool with these fields:

- display_name: a PARODY rename of the character. RULES (follow exactly):
  * Keep the original name's phonetic RHYTHM and syllable count.
  * Change only ONE or TWO letters from the original.
  * The result MUST NOT be a real existing first name or surname.
  * It should read as a playful near-homophone, like the app's existing cast:
    Phil Dunphy -> Fil Funphy, Claire -> Clair-ification.
  BAD (never do this):
    * "Jesse P." or "Jesse" — that is not a rename, it just truncates.
    * "Jesse Pinkerton" — that swaps in a DIFFERENT real surname.
  GOOD shape: tweak sounds, e.g. Jesse Pinkman -> Jesse Pinkling / Jessie Pinkman.

- intro: one short first-person catchphrase in the character's voice (English,
  or mixed with a little Chinese if it fits), like a chat-app status line. See
  the built-ins: "I've got a Fil-osophy for every situation. You're welcome."

- persona: a compact second-person description the app speaks AS. Cover, in a
  few sentences: speaking cadence and tone; a signature catchphrase or sentence
  pattern; core personality; how they tend to open a conversation; and ONE
  wordplay/pun bit rooted in the real show (the built-in "Fil-osophy" is the
  reference). Write it as direct instruction: "You are <name>, ...". Do not
  include any teaching or practice instructions.
"""

_PERSONA_TOOL = {
    "type": "function",
    "function": {
        "name": "report_persona",
        "description": "Report the generated roleplay persona for the character.",
        "parameters": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": "Parody rename: keep the phonetic rhythm, change "
                    "1-2 letters, must NOT be a real name.",
                },
                "intro": {
                    "type": "string",
                    "description": "One short first-person catchphrase in-voice.",
                },
                "persona": {
                    "type": "string",
                    "description": "Second-person persona the app speaks as; cadence, "
                    "catchphrase, personality, how they open, one show-rooted pun. "
                    "No teaching rules.",
                },
            },
            "required": ["display_name", "intro", "persona"],
        },
    },
}


# --- cast generation ---------------------------------------------------------
# Generating one auto-character per show left every non-built-in show with a
# cast of exactly one. This generates a whole main-cast group in a single model
# call (never one call per character) so a fresh show gets several characters
# to pick from, same as Modern Family's ten built-ins.
_CAST_SYSTEM_PROMPT = """\
You design a roleplay CAST for an English-conversation practice app, covering
several of a show's main characters at once. Given a show name, and optionally
(a) parody names already used FOR THIS SHOW and (b) parody names already used
by OTHER shows, pick this show's main characters and give each one a persona.

RULES:
- Pick roughly 6 main characters for this show in total — never fewer than 3,
  never more than 8, counting any that already exist for it.
- If "already used for this show" names are given, figure out which real
  character each one represents and do NOT pick that same character again.
  Your new picks plus however many already exist should land around 6 total
  (up to 8) — so if several already exist, pick fewer new ones. If this show
  already has 6 or more, return an empty characters array.
- Every display_name in your output must be a distinct parody rename — no two
  of your own characters can share one, and none can match a name already used
  for this show OR by another show (that list is for collision-avoidance only —
  it does not count toward this show's target).
- For each character, report original_name: the real character's name from the
  show (used only for our records, never shown to the learner).
- For EACH character, apply this rename rule:
  * Keep the original name's phonetic RHYTHM and syllable count.
  * Change only ONE or TWO letters from the original.
  * The result MUST NOT be a real existing first name or surname.
  * It should read as a playful near-homophone, like the app's existing cast:
    Phil Dunphy -> Fil Funphy, Claire -> Clair-ification.
  BAD (never do this): "Jesse P." (truncation, not a rename); "Jesse
  Pinkerton" (swaps in a different real surname).
  GOOD shape: Jesse Pinkman -> Jesse Pinkling / Jessie Pinkman.
- For each character also write: intro (one short first-person catchphrase in
  their voice, like a chat-app status line — e.g. "I've got a Fil-osophy for
  every situation. You're welcome.") and persona (a compact second-person
  description the app speaks AS — cadence and tone, a signature catchphrase or
  sentence pattern, core personality, how they tend to open a conversation, and
  ONE wordplay/pun bit rooted in the real show. Write it as direct instruction:
  "You are <name>, ...". No teaching or practice instructions.)

Return your result by calling `report_cast` with a `characters` array.
"""

_CAST_TOOL = {
    "type": "function",
    "function": {
        "name": "report_cast",
        "description": "Report the generated roleplay cast for the show.",
        "parameters": {
            "type": "object",
            "properties": {
                "characters": {
                    "type": "array",
                    "description": "Roughly 6 (max 8) distinct main characters.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "original_name": {
                                "type": "string",
                                "description": "The real character's name from the "
                                "show — for our records only, never shown to the "
                                "learner.",
                            },
                            "display_name": {
                                "type": "string",
                                "description": "Parody rename: keep the phonetic "
                                "rhythm, change 1-2 letters, must NOT be a real name.",
                            },
                            "intro": {
                                "type": "string",
                                "description": "One short first-person catchphrase "
                                "in-voice.",
                            },
                            "persona": {
                                "type": "string",
                                "description": "Second-person persona the app "
                                "speaks as; cadence, catchphrase, personality, how "
                                "they open, one show-rooted pun. No teaching rules.",
                            },
                        },
                        "required": ["original_name", "display_name", "intro", "persona"],
                    },
                },
            },
            "required": ["characters"],
        },
    },
}


# Stella-r replies in tiny fragments, so she needs more turns to give the same
# number of expressions a chance to appear.
_DEFAULT_TARGET_TURNS = 6
_STELLA_TARGET_TURNS = 10

_sessions: dict[str, dict] = {}


def list_characters(show: str | None = None) -> list[dict]:
    """Public metadata for the pick screen. Delegates to the characters DB so
    built-ins and user-made characters come from one source of truth."""
    return characters.list_characters(show=show)


def _norm_name(s: str) -> str:
    """Lowercase, keep only letters/spaces, collapse spaces — for name compare."""
    return " ".join("".join(c for c in s.lower() if c.isalpha() or c == " ").split())


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (small strings, so the simple DP is fine)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _looks_renamed(original: str, generated: str) -> bool:
    """Reject renames that didn't actually change the name enough.

    Fails when the generated name equals the original, is a bare prefix of it
    (the "Jesse P." / truncation case), or is within one edit of it (barely
    touched). This is a heuristic backstop for the prompt rule — it can't detect
    "swapped in another real surname", which the prompt handles.
    """
    o, g = _norm_name(original), _norm_name(generated)
    if not g:
        return False
    if g == o:
        return False
    # Truncation / initialism: "jesse pinkman" -> "jesse p" / "jesse".
    if o.startswith(g) or g.startswith(o):
        return False
    # Any real change of 1+ letters is acceptable (the spec allows changing one
    # or two letters); identical was already rejected above. We can't detect
    # "swapped in another real name" — the prompt handles that.
    return _edit_distance(o, g) >= 1


def generate_persona_for_show(show: str) -> dict:
    """Auto-pick the best conversational character from a show, then persona it.

    Used when the learner's current show (from Notion Source) has no character
    yet. The model chooses one character itself — favoring a talkative, vivid,
    linguistically distinctive one good for daily-conversation practice — and
    returns the same fields as generate_persona (display_name, intro, persona),
    plus `character` (the original name it picked, for reference). Same rename
    rules and backend retry apply.
    """
    show = (show or "").strip()
    if not show:
        raise ValueError("Show is required.")
    pick_note = (
        "The user did not name a character. Pick the SINGLE best character from "
        "this show for everyday English conversation practice — someone who talks "
        "a lot, has a vivid personality, and a distinctive way of speaking. State "
        "whom you picked, then build the persona for them."
    )
    # Reuse generate_persona's machinery by passing the picked-character prompt as
    # the 'character' slot description; the prompt already enforces the rename.
    return generate_persona(show, "(you choose the best character)", pick_note)


def generate_persona(show: str, character: str, note: str = "") -> dict:
    """Generate the persona layer for a new character via the model.

    Returns {"display_name", "intro", "persona"}. Applies the rename rules from
    the prompt, then a backend check: if the rename looks too close to the
    original, retry ONCE with a stronger instruction; accept the second result
    either way so we never loop. Raises ValueError on empty inputs.
    """
    show = (show or "").strip()
    character = (character or "").strip()
    if not show or not character:
        raise ValueError("Both show and character are required.")

    base_prompt = f"Show: {show}\nCharacter: {character}"
    if note.strip():
        base_prompt += f"\nExtra note from the user: {note.strip()}"

    def _one_call(extra: str = "") -> dict:
        resp = _client.chat.completions.create(
            model=config.API_MODEL,
            max_tokens=800,
            temperature=0.9,
            tools=[_PERSONA_TOOL],
            tool_choice={"type": "function", "function": {"name": "report_persona"}},
            messages=[
                {"role": "system", "content": _PERSONA_SYSTEM_PROMPT},
                {"role": "user", "content": base_prompt + extra},
            ],
        )
        tool_calls = resp.choices[0].message.tool_calls or []
        for call in tool_calls:
            if call.function.name == "report_persona":
                inp = json.loads(call.function.arguments)
                return {
                    "display_name": str(inp.get("display_name", "")).strip(),
                    "intro": str(inp.get("intro", "")).strip(),
                    "persona": str(inp.get("persona", "")).strip(),
                }
        return {"display_name": "", "intro": "", "persona": ""}

    result = _one_call()
    if not _looks_renamed(character, result["display_name"]):
        # One firmer retry, quoting the rejected name so the model doesn't repeat it.
        retry_note = (
            f"\n\nYour previous display_name {result['display_name']!r} was rejected: "
            f"it is too close to the original {character!r} or is a truncation. "
            "Produce a DIFFERENT parody rename that changes one or two letters of "
            "the sound while staying a near-homophone, and is not a real name."
        )
        retry = _one_call(retry_note)
        if retry["display_name"]:
            result = retry
    return result


def generate_cast_for_show(
    show: str,
    same_show_names: list[str] | None = None,
    other_show_names: list[str] | None = None,
) -> list[dict]:
    """Generate a whole main-cast top-up for a show in ONE model call.

    Used the first time a show is seen (or when it only has a handful of
    characters so far) so it gets a real cast to choose from instead of a
    single auto-picked character.

    `same_show_names` are display_names already used FOR THIS SHOW — the model
    must not re-pick the real character behind any of them, and they count
    toward the ~6 target (so a show with 1 existing character gets ~5 more,
    not 6 more). `other_show_names` are display_names used by OTHER shows —
    pure collision-avoidance, must not be reused, but don't count toward this
    show's target.

    Returns a list of {"display_name", "intro", "persona"} — degrades
    gracefully: any item that's malformed, a name collision (within the batch
    or against either name list), or a rename that's too close to the real
    character (per the same rule generate_persona enforces) is dropped rather
    than sinking the whole batch. Never retries — this is a single call.
    """
    show = (show or "").strip()
    if not show:
        raise ValueError("Show is required.")
    same_names = [n.strip() for n in (same_show_names or []) if n.strip()]
    other_names = [n.strip() for n in (other_show_names or []) if n.strip()]

    prompt = f"Show: {show}"
    if same_names:
        prompt += (
            "\n\nAlready used FOR THIS SHOW (do not re-pick the real character "
            "behind any of these; they count toward the ~6 target):\n"
            + ", ".join(same_names)
        )
    if other_names:
        prompt += (
            "\n\nAlready used by OTHER shows (avoid these exact names, but they "
            "do not count toward this show's target):\n"
            + ", ".join(other_names)
        )

    resp = _client.chat.completions.create(
        model=config.API_MODEL,
        max_tokens=3000,
        temperature=0.9,
        tools=[_CAST_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_cast"}},
        messages=[
            {"role": "system", "content": _CAST_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw_items: list = []
    tool_calls = resp.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name == "report_cast":
            raw_items = json.loads(call.function.arguments).get("characters") or []
            break

    used_norm = {_norm_name(n) for n in same_names + other_names}
    result: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue  # malformed entry — skip it, keep the rest of the batch
        display_name = str(item.get("display_name", "")).strip()
        original_name = str(item.get("original_name", "")).strip()
        intro = str(item.get("intro", "")).strip()
        persona = str(item.get("persona", "")).strip()
        if not display_name or not intro or not persona:
            continue
        norm = _norm_name(display_name)
        if not norm or norm in used_norm:
            continue  # duplicate within this batch or against an existing name
        if original_name and not _looks_renamed(original_name, display_name):
            continue  # rename too close to (or a truncation of) the real name
        used_norm.add(norm)
        result.append({"display_name": display_name, "intro": intro, "persona": persona})
        if len(result) >= 8:
            break  # hard cap regardless of what the model returned
    return result


def _pick_targets(expressions: list[str]) -> list[str]:
    pool = [e for e in expressions if e.strip()]
    random.shuffle(pool)
    n = min(len(pool), random.randint(3, 5))
    return pool[:n]


def _system_prompt(persona: str, targets: list[str]) -> str:
    """Full system prompt = the character's persona + the shared teaching rules."""
    tlist = ", ".join(f'"{t}"' for t in targets)
    return persona + "\n\n" + _TEACHING_TEMPLATE.format(targets=tlist)


def start_session(character_key: str, expressions: list[str]) -> dict:
    """Create a session, choose target expressions, and get the opening line."""
    char = characters.get(character_key)
    if not char:
        raise ValueError(f"Unknown character: {character_key!r}")

    targets = _pick_targets(expressions)
    session_id = uuid.uuid4().hex
    system = _system_prompt(char["persona"], targets)

    kickoff = (
        "Start the conversation now. In character, greet the learner and set up a "
        "casual little scenario that gives them a natural opening to use one of the "
        "target expressions. Do not mention the expressions or that this is a test."
    )
    reply = _call_model(system, [{"role": "user", "content": kickoff}], char)

    _sessions[session_id] = {
        "character": character_key,
        "char_name": char["name"],
        "system": system,
        "targets": targets,
        # Full turn history (user/assistant). The kickoff instruction is not
        # stored so it doesn't leak into later context.
        "history": [{"role": "assistant", "content": reply}],
    }
    return {
        "session_id": session_id,
        "character": character_key,
        "targets": targets,
        "reply": reply,
    }


def turn(session_id: str, message: str) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        raise KeyError("Session not found or expired.")

    sess["history"].append({"role": "user", "content": message})
    reply = _call_model(sess["system"], sess["history"], char=None)
    sess["history"].append({"role": "assistant", "content": reply})

    user_turns = sum(1 for m in sess["history"] if m["role"] == "user")
    limit = _STELLA_TARGET_TURNS if sess["character"] == "stella" else _DEFAULT_TARGET_TURNS
    return {"reply": reply, "user_turns": user_turns, "suggest_end": user_turns >= limit}


def _used_targets(history: list[dict], targets: list[str]) -> dict[str, bool]:
    """Which targets did the learner actually produce, across their own turns?

    Uses the same inflection-tolerant matcher as the cloze reviewer, checked over
    a sliding window of the user's words so an expression embedded in a longer
    sentence still counts.
    """
    user_text = " ".join(m["content"] for m in history if m["role"] == "user")
    used = {}
    for t in targets:
        used[t] = _appears_in(user_text, t)
    return used


def _appears_in(text: str, expression: str) -> bool:
    """True if `expression` appears anywhere in `text` (inflection-tolerant)."""
    norm_text = matching.normalize(text)
    norm_expr = matching.normalize(expression)
    if not norm_expr:
        return False
    if norm_expr in norm_text:
        return True
    # Fall back to the stem-sequence check over the whole user text.
    return matching.is_correct(text, expression)


def end_session(session_id: str) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        raise KeyError("Session not found or expired.")
    targets = sess["targets"]
    used = _used_targets(sess["history"], targets)

    used_list = [t for t in targets if used[t]]
    missed_list = [t for t in targets if not used[t]]

    critique = _critique(sess, used_list, missed_list)

    result = {
        "used": used_list,
        "missed": missed_list,
        "total": len(targets),
        "used_count": len(used_list),
        "critique": critique,
    }
    # Session is done; free it.
    _sessions.pop(session_id, None)
    return result


def _critique(sess: dict, used: list[str], missed: list[str]) -> str:
    """Ask the model to step OUT of character and coach briefly."""
    speaker = sess.get("char_name", "Character")
    transcript = "\n".join(
        ("Learner: " if m["role"] == "user" else speaker + ": ") + m["content"]
        for m in sess["history"]
    )
    system = (
        "You are a warm, encouraging English coach. Step OUT of any character. "
        "Given a practice conversation and which target expressions the learner "
        "did or didn't use, write a SHORT friendly debrief (Chinese is fine, and "
        "preferred). For each expression they missed, quote a specific moment in "
        "the transcript where they could have used it, phrased as: 在你说“…”的时候，"
        "其实可以说“<expression>”。 End with one line of overall encouragement. Do "
        "not be harsh."
    )
    prompt = (
        f"Target expressions: {targets_str(sess['targets'])}\n"
        f"Used correctly: {targets_str(used) or '（无）'}\n"
        f"Not used: {targets_str(missed) or '（无）'}\n\n"
        f"Transcript:\n{transcript}"
    )
    return _call_model(system, [{"role": "user", "content": prompt}], char=None)


def targets_str(items: list[str]) -> str:
    return ", ".join(items)


def _call_model(system: str, messages: list[dict], char: dict | None) -> str:
    """One model call. `char` is unused here but kept for future per-character
    tuning (temperature, max_tokens). Returns the assistant text."""
    resp = _client.chat.completions.create(
        model=config.API_MODEL,
        max_tokens=600,
        temperature=0.9,
        messages=[{"role": "system", "content": system}, *messages],
    )
    return (resp.choices[0].message.content or "").strip()
