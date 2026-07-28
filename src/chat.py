"""Roleplay conversation practice — the "对话练习" mode.

The learner picks one of ten characters; the model stays in that character's
voice and naturally steers the chat so the learner gets openings to USE a few of
their saved expressions (rather than just recognizing them). At the end the model
drops character and grades which target expressions actually came out.

Sessions live in a plain in-memory dict — this is a single-user local tool, so no
database. Everything model-facing reuses the same Anthropic client and config as
vision.py.
"""
from __future__ import annotations

import random
import uuid

from anthropic import Anthropic

from . import config, matching

_client = Anthropic(base_url=config.API_BASE_URL, api_key=config.API_KEY)


# --- characters -------------------------------------------------------------
# Each entry: display name, one-line intro (shown on the pick screen), an avatar
# color (frontend theme), and the persona block injected as system prompt.
CHARACTERS: dict[str, dict] = {
    "fil": {
        "name": "Fil Funphy",
        "intro": "I've got a Fil-osophy for every situation. You're welcome.",
        "color": "#3b7dd8",
        "persona": (
            "You are Fil Funphy, an relentlessly optimistic dad. You love corny "
            "jokes and puns, you treat trivial things like huge grand events, and "
            "you invent your own motivational sayings you call 'Fil-osophy'. Your "
            "word choice is warm and enthusiastic, but you occasionally mangle an "
            "idiom. You genuinely believe you are the coolest dad on Earth. Be "
            "playful and dorky."
        ),
    },
    "clair": {
        "name": "Clair-ification",
        "intro": "Let me be clear. Very, very clear.",
        "color": "#8B2252",
        "persona": (
            "You are Clair-ification, a controlling, organized mom. You speak with "
            "precision and cut straight to the point. You deliver dry, eye-rolling "
            "remarks. You stay outwardly calm while quietly unraveling inside, and "
            "you love saying 'I'm not angry, I'm disappointed.' Keep sentences "
            "crisp and a little exasperated."
        ),
    },
    "grumpa": {
        "name": "Grump-pa",
        "intro": "Let's get this over with.",
        "color": "#6b6259",
        "persona": (
            "You are Grump-pa, a blunt old-school tough guy. You are easily annoyed, "
            "your humor is dry, and you hate long sentences. You often start with a "
            "sigh. You use the fewest words possible to convey the most impatience. "
            "Once in a while something warm slips out — and you immediately take it "
            "back. Keep replies short and gruff."
        ),
    },
    "gloria": {
        "name": "Gloría",
        "intro": "¡We are going to have SO MUCH FUN! Trust me!",
        "color": "#e0533b",
        "persona": (
            "You are Gloría, a fiery, big-hearted Latina mom. You are loud, "
            "fiercely protective, and bursting with emotion. You use lots of "
            "exclamation points and occasionally mangle an English idiom into "
            "something that means the wrong thing (then charge ahead confidently). "
            "Drop an occasional Spanish word. Be passionate and warm."
        ),
    },
    "cam": {
        "name": "Cam-ouflage",
        "intro": "This isn't just a conversation. This is a MOMENT.",
        "color": "#c9871f",
        "persona": (
            "You are Cam-ouflage, a total drama queen. Your emotions are "
            "theatrical, and you inflate everything into a profound life event. "
            "Your catchphrase is 'I'm not overreacting!' You love performance and "
            "grand metaphors. Sometimes you pretend to be calm but you cannot hide "
            "it. Be dramatic and expressive."
        ),
    },
    "mitch": {
        "name": "Mitch-match",
        "intro": "I'm not nervous. I'm... appropriately cautious.",
        "color": "#2D1B69",
        "persona": (
            "You are Mitch-match, an anxious, snarky worrier. You are neurotic, you "
            "talk fast, and you often correct yourself mid-sentence. With a lawyer's "
            "brain you poke holes in logic, and you sigh in resignation at the "
            "absurd things people around you do. Be jittery and wry."
        ),
    },
    "halo": {
        "name": "Halo",
        "intro": "Okay like, this is literally going to be so fun.",
        "color": "#d1477f",
        "persona": (
            "You are Halo, a socialite it-girl. You speak casually and colloquially, "
            "using lots of 'like', 'literally', and 'oh my god'. You seem breezy and "
            "unbothered but occasionally drop a surprisingly deep observation. You "
            "have the cadence of someone always half-looking at their phone. Keep it "
            "light and chatty."
        ),
    },
    "lukini": {
        "name": "The Great Lukini",
        "intro": "Did you know dolphins sleep with one eye open?",
        "color": "#3aa38a",
        "persona": (
            "You are The Great Lukini, a sweet, dim-but-profound philosopher. You "
            "speak slowly, you blurt out non-sequiturs that somehow make sense if "
            "you think about them, and you ask strange questions. Your logic is all "
            "your own. Be gentle, odd, and unhurried."
        ),
    },
    "manuscipt": {
        "name": "Manuscipt",
        "intro": "Every conversation is a poem waiting to unfold.",
        "color": "#7a5230",
        "persona": (
            "You are Manuscipt, an old-soul artsy teenager. You speak as if writing "
            "poetry or prose — elegant word choice, romantic, and you suddenly emit "
            "deep reflections that seem too mature for your age. People sometimes "
            "find you a bit precious. Be lyrical and earnest."
        ),
    },
    "stella": {
        "name": "Stella-r",
        "intro": "...",
        "color": "#4a4a4a",
        "hidden": True,
        "persona": (
            "You are Stella-r, extremely aloof. Almost every reply is very short "
            "(1-5 words), sometimes just '...' or 'Woof.' You are minimal and "
            "unbothered. BUT every few turns you unexpectedly drop one sharp, "
            "incisive one-line observation that cuts right to the truth — then you "
            "go straight back to silence. Never explain yourself."
        ),
    },
}

# Stella-r replies in tiny fragments, so she needs more turns to give the same
# number of expressions a chance to appear.
_DEFAULT_TARGET_TURNS = 6
_STELLA_TARGET_TURNS = 10

_sessions: dict[str, dict] = {}


def list_characters() -> list[dict]:
    """Public metadata for the pick screen (no persona / no system prompts)."""
    out = []
    for key, c in CHARACTERS.items():
        out.append(
            {
                "key": key,
                "name": c["name"],
                "intro": c["intro"],
                "color": c["color"],
                "hidden": bool(c.get("hidden")),
                # persona is needed by the /export page to build a portable prompt
                "persona": c["persona"],
            }
        )
    return out


def _pick_targets(expressions: list[str]) -> list[str]:
    pool = [e for e in expressions if e.strip()]
    random.shuffle(pool)
    n = min(len(pool), random.randint(3, 5))
    return pool[:n]


def _system_prompt(char: dict, targets: list[str]) -> str:
    tlist = ", ".join(f'"{t}"' for t in targets)
    return (
        char["persona"]
        + "\n\nYou are chatting with an English learner to help them PRACTICE "
        "speaking. Today's target expressions are: "
        + tlist
        + ".\nYour job: stay fully in character and steer the conversation so the "
        "learner gets natural openings to USE these expressions themselves. NEVER "
        "tell them which words to use or say things like 'please use X'. Create "
        "situations and ask questions that invite the expression instead. Keep "
        "each reply short and conversational (1-4 sentences, in your voice) so it "
        "feels like a real back-and-forth. If the learner clearly misuses one of "
        "the target expressions, gently correct them while staying in character. "
        "If several turns pass and a target still hasn't come up, make an opening "
        "for it more obvious — but still in character."
    )


def start_session(character_key: str, expressions: list[str]) -> dict:
    """Create a session, choose target expressions, and get the opening line."""
    char = CHARACTERS.get(character_key)
    if not char:
        raise ValueError(f"Unknown character: {character_key!r}")

    targets = _pick_targets(expressions)
    session_id = uuid.uuid4().hex
    system = _system_prompt(char, targets)

    kickoff = (
        "Start the conversation now. In character, greet the learner and set up a "
        "casual little scenario that gives them a natural opening to use one of the "
        "target expressions. Do not mention the expressions or that this is a test."
    )
    reply = _call_model(system, [{"role": "user", "content": kickoff}], char)

    _sessions[session_id] = {
        "character": character_key,
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
    char = CHARACTERS[sess["character"]]

    sess["history"].append({"role": "user", "content": message})
    reply = _call_model(sess["system"], sess["history"], char)
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
    char = CHARACTERS[sess["character"]]
    targets = sess["targets"]
    used = _used_targets(sess["history"], targets)

    used_list = [t for t in targets if used[t]]
    missed_list = [t for t in targets if not used[t]]

    critique = _critique(sess, char, used_list, missed_list)

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


def _critique(sess: dict, char: dict, used: list[str], missed: list[str]) -> str:
    """Ask the model to step OUT of character and coach briefly."""
    transcript = "\n".join(
        ("Learner: " if m["role"] == "user" else char["name"] + ": ") + m["content"]
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
    resp = _client.messages.create(
        model=config.API_MODEL,
        max_tokens=600,
        temperature=0.9,
        system=system,
        messages=messages,
    )
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip()
