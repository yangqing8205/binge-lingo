"""Scene Talk roleplay practice and AI-generated character personas.

The learner selects a character and practises saved expressions through a short
conversation. Character records live in SQLite, while active chat sessions are
process-local and therefore require a single Gunicorn worker in the current MVP.
All model calls reuse the OpenAI-compatible client and configuration from the
capture pipeline.

Character generation produces a structured CARD (see characters.py's module
docstring for the schema) rather than a flat persona string. Cast generation for
a new show is split into two stages so it stays fast even with a bigger schema:
  1. select_cast_characters() — one cheap call that just decides WHICH ~6
     characters to make (names + one-line intros).
  2. _generate_starter_card() — one call PER selected character, fanned out in
     PARALLEL via a thread pool. Wall-clock is ~one character's worth of work,
     not 6x, however many fields the card grows to carry.
Each character's card starts "starter" (1-2 signature_moves, 1 opening_variant)
and is topped up to "full" lazily, the first time it's actually selected for a
chat (see _ensure_full_card, called from start_session) — spreading that cost
across first-uses instead of paying it for every character up front.
All card-generation calls disable Ark's extended thinking (_NO_THINKING) — it
adds real latency and buys nothing for structured tool-call output.
"""
from __future__ import annotations

import concurrent.futures
import json
import random
import uuid

from openai import OpenAI

from . import characters, config, matching

_client = OpenAI(
    base_url=config.API_BASE_URL,
    api_key=config.API_KEY,
    timeout=90.0,
    max_retries=0,
)

_NO_THINKING = {"thinking": {"type": "disabled"}}

# Cap on parallel fanout calls for cast generation — bounds concurrent load on
# the gateway regardless of how many characters get selected (max 8, see
# select_cast_characters).
_MAX_PARALLEL_WORKERS = 8


# --- teaching template ------------------------------------------------------
# The shared tutoring rules, hardcoded once and reused by EVERY character
# (built-in or user-made). A character contributes only its persona; this
# template is appended to build the full system prompt. Editing how the tutor
# behaves — how it draws out targets, never leaks them, corrects, keeps replies
# short — is a one-place change here. `{targets}` is filled at session start.
_TEACHING_TEMPLATE = (
    "You are chatting with an English learner to help them PRACTICE speaking. "
    "Today's target expressions are: {targets}.\n"
    "YOUR JOB: stay fully in character and steer the conversation so the learner "
    "gets natural openings to USE these expressions themselves.\n"
    "ABSOLUTE RULE — you must NEVER say any of the target expressions yourself. "
    "Not even once. Not as a quote, not as an example, not accidentally. "
    "The whole point is that the LEARNER says them. You create the situation, "
    "you ask the question, you build the setup — but the target phrase must "
    "come from their mouth, not yours. Paraphrase around them. Hint at them. "
    "Set them up. But never say them.\n"
    "Also: never tell them which words to use or say things like 'please use X'. "
    "Keep each reply short and conversational (1-4 sentences, in your voice) "
    "so it feels like a real back-and-forth. If the learner clearly misuses "
    "one of the target expressions, gently correct them while staying in "
    "character. If several turns pass and a target still hasn't come up, "
    "make an opening for it more obvious — but still in character, and still "
    "without saying the target phrase yourself."
)


_RENAME_RULE_TEXT = """\
- display_name: a PARODY rename of the character. RULES (follow exactly):
  * Keep the original name's phonetic RHYTHM and syllable count.
  * Change only ONE or TWO letters from the original.
  * The result MUST NOT be a real existing first name or surname.
  * It should read as a playful near-homophone, like the app's existing cast:
    Phil Dunphy -> Fil Funphy, Claire -> Clair-ification.
  BAD (never do this):
    * "Jesse P." or "Jesse" — that is not a rename, it just truncates.
    * "Jesse Pinkerton" — that swaps in a DIFFERENT real surname.
  GOOD shape: tweak sounds, e.g. Jesse Pinkman -> Jesse Pinkling / Jessie Pinkman.\
"""

# Shared across every card-generation prompt (single character, cast selection,
# starter card, and lazy completion) — NOT specific to any one show. These are
# the three rules the user asked for: cite a source per feature, make `avoid`
# name something specific to THIS character rather than the archetype, and
# force a self-check that catches interchangeable, could-be-anyone writing.
_CARD_HARD_RULES = """\
HARD RULES (apply to every feature you write, for any show or character):

1. SOURCE EVERY FEATURE. Each entry in signature_moves, and the voice
   description itself, must carry an `evidence` object: {quote, confidence,
   source} — `source` is the scene/episode/moment you're recalling (e.g. "the
   pilot, when he first meets the pharmacist" — a rough description is fine,
   you don't need an exact episode number). If you cannot name where a trait
   comes from, DO NOT WRITE IT — write fewer, sourced features instead of
   padding the list with unsourced ones.

2. DO NOT PRETEND TO HAVE A PERFECT MEMORY. For each `evidence.quote`, set
   `confidence` to "verbatim" ONLY if you are genuinely confident that is the
   real, word-for-word line. If you are recalling the gist/style of a moment
   but are not sure of the exact wording, set `confidence` to "reconstructed"
   and write `quote` as a line that fits that style — NOT as if it were a
   verified citation. Never dress up an invented line as "verbatim". When in
   doubt, use "reconstructed".

3. AVOID must name what's specific to THIS character, not the archetype.
   Every item in `avoid` must point at something that would NOT equally apply
   to other characters of the same broad type. A generic line like "don't make
   her too strict" is USELESS — it fits any strict-mom-type character ever
   written, so it doesn't belong in this card.
   BAD (interchangeable — could describe any character of this archetype):
     "Don't make him too dumb" / "Don't be overly dramatic" / "Don't be a
     one-note villain"
   GOOD (specific to this character, not swappable with a same-type
   character): "Her care always comes wrapped in a scoreboard — she never
   just says 'I told you so', she keeps literal count and brings up the tally
   weeks later" (specific mechanism, not just a trait label).

4. SELF-CHECK EACH signature_move BEFORE reporting it: fill `distinct_because`
   by asking yourself "if I swapped in a different character of the same
   general type (same job, same family role, same personality archetype), would
   this move still make sense for them too?" If the honest answer is "yes,
   this is generic/interchangeable", REWRITE the move to be more specific to
   THIS character (drawing on the sourced scene from rule 1) before reporting
   it — don't report the generic version.

5. IDENTITY-BEARING vs GENERIC TRAITS. The app already knows the character's
   archetype (friendly, awkward, optimistic, etc.). What it needs from you are
   the IDENTITY-BEARING behaviours that make THIS specific character
   RECOGNISABLE -- not just the archetype label. For every trait you write, ask
   yourself: "if I hid the character name and show, would a fan recognise this
   character from this behaviour after 4-5 turns?" If the honest answer is no,
   dig deeper or drop it. Prefer:
   - Recognisable greeting/opening patterns and conversational entry rituals
   - Recurring joke construction mechanics (setup->payoff, callback, etc.)
   - Characteristic reactions to embarrassment, confusion, or excitement
   - Recognisable social habits and verbal tics
   - Recurring obsessions, themes, or preoccupations
   - Specific types of misunderstanding or misplaced confidence
   - Signature conversational rhythms
   over generic labels like "friendly", "sarcastic", or "goofy".

6. SIGNATURE GREETINGS. `signature_greetings` must be CONCRETE setup/payoff
   BEHAVIOURS a fan would recognise, not generic opening lines. Each entry
   needs a `why_distinctive` self-check: explain why this greeting is specific
   to THIS character. If you cannot name a specific scene or moment, or if the
   greeting would fit any character of this archetype, DO NOT include it.
   - 0-3 entries max. Empty list is the safe default.
   - Only mark `confidence: "high"` when the greeting is a well-known
     character signature. When in doubt, use "medium" or omit it.
   - NEVER invent a fake "classic" greeting just to fill the field.
   - A generic "Hey buddy, great to see you!" is NOT a signature greeting.

7. WORLD MEMORY AND SCENE WORK. The character must feel like they live in the
   show's world, not in an English classroom. `world_memory` stores concrete
   facts (events, relationships, jobs, locations, conflicts) -- NOT personality
   descriptions. `opening_scenes` are mini scene setups where the conversation
   STARTS already in the middle of something -- like walking into an episode.
   The first thing the character says should NEVER sound like a teacher starting
   a lesson. It should sound like a character in the middle of their life.
"""

_EVIDENCE_SCHEMA = {
    "type": "object",
    "description": "Where this trait comes from — required, never omit.",
    "properties": {
        "quote": {
            "type": "string",
            "description": "The line/moment itself — verbatim if confidence is "
            "'verbatim', otherwise a reconstructed line in that style.",
        },
        "confidence": {
            "type": "string",
            "enum": ["verbatim", "reconstructed"],
            "description": "'verbatim' ONLY if you're genuinely confident this is "
            "the real word-for-word line. Otherwise 'reconstructed' — a line "
            "that fits the character's style, not presented as a real citation.",
        },
        "source": {
            "type": "string",
            "description": "Which scene/episode/moment this is from (rough "
            "description is fine, e.g. 'the pilot, meeting the new neighbor').",
        },
    },
    "required": ["quote", "confidence", "source"],
}

_CARD_SCHEMA_PROPERTIES = {
    "voice": {
        "type": "object",
        "description": "How this character sounds when speaking.",
        "properties": {
            "pace": {"type": "string", "description": "Speaking speed/rhythm."},
            "sentence_length": {"type": "string", "description": "Typical sentence "
                "length and structure."},
            "vocabulary": {"type": "string", "description": "Word choice register "
                "— formal/slangy/technical/etc."},
            "tone": {"type": "string", "description": "Overall tone."},
            "emotional_range": {"type": "string", "description": "How much and "
                "how visibly emotion shows/shifts."},
            "evidence": _EVIDENCE_SCHEMA,
        },
        "required": ["pace", "sentence_length", "vocabulary", "tone",
                      "emotional_range", "evidence"],
    },
    "signature_moves": {
        "type": "array",
        "description": "1 or more sourced, character-specific interaction "
        "patterns pulled from real moments — never invented from the archetype.",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short name for the move."},
                "steps": {"type": "array", "items": {"type": "string"},
                          "description": "The structural steps of this move, in order."},
                "frequency": {"type": "string", "description": "How often this "
                    "move tends to come up, e.g. 'every session opener', 'rare, "
                    "maybe once per long conversation'."},
                "evidence": _EVIDENCE_SCHEMA,
                "distinct_because": {"type": "string", "description": "Why this "
                    "specific move would NOT fit an interchangeable character of "
                    "the same archetype — the rule-4 self-check, required."},
            },
            "required": ["name", "steps", "frequency", "evidence", "distinct_because"],
        },
    },
    "format_style": {
        "type": "object",
        "description": "What typographic habits this character's replies use.",
        "properties": {
            "caps": {"type": "string", "description": "When/how ALL CAPS is used, "
                "if at all."},
            "bold": {"type": "string", "description": "When/how **bold** is used, "
                "if at all."},
            "ellipsis": {"type": "string", "description": "When/how '...' is used, "
                "if at all."},
            "exclaim": {"type": "string", "description": "How freely '!' is used."},
            "notes": {"type": "string", "description": "Any other formatting quirk."},
        },
        "required": ["caps", "bold", "ellipsis", "exclaim", "notes"],
    },
    "opening_variants": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Several DIFFERENT ways this character might kick off a "
        "conversation, in their voice.",
    },
    "signature_greetings": {
        "type": "array",
        "description": "0-3 concrete, highly recognizable character-specific "
        "opening/greeting BEHAVIORS (not just text). Only include when reliable "
        "evidence exists -- empty list is better than a fake one. Each entry is a "
        "structured setup/payoff pair the runtime can actually render as sequential "
        "messages. A fan should recognise the character from the greeting alone.",
        "items": {
            "type": "object",
            "properties": {
                "setup": {
                    "type": "string",
                    "description": "The setup line -- first message in the sequence.",
                },
                "payoff": {
                    "type": "string",
                    "description": "The payoff line -- second message, after a beat.",
                },
                "usage": {
                    "type": "string",
                    "enum": ["new_session_opening"],
                    "description": "When this greeting is appropriate.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "'high' only when the greeting is a well-known "
                    "characteristic behaviour fans would recognise. 'medium' when "
                    "it's in-character but less iconic. 'low' entries are discarded "
                    "by the runtime -- only include them if you're unsure.",
                },
                "why_distinctive": {
                    "type": "string",
                    "description": "A sentence explaining why this greeting is "
                    "recognisable as THIS specific character -- the self-check that "
                    "prevents generic 'hey buddy!' from being stored as a signature.",
                },
            },
            "required": ["setup", "payoff", "usage", "confidence", "why_distinctive"],
        },
    },
    "world_memory": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Concrete facts about this character's world — events, "
        "relationships, habits, locations, long-running conflicts, jobs, hobbies. "
        "These are plot/scene materials the character can reference naturally, "
        "NOT personality traits. Each entry should be something a fan would "
        "recognise. Example: 'sells real estate and does magic tricks at open houses'.",
    },
    "signature_situations": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Recurring scenarios or situations this character is often "
        "found in. These are scene setups the runtime can use to ground a "
        "conversation in the show's world rather than generic English practice. "
        "Example: 'in the middle of an open house', 'fixing something around the house'.",
    },
    "opening_scenes": {
        "type": "array",
        "description": "Ready-to-use opening scene starters. Each one is a mini "
        "scene setup the character can walk into the conversation already in the "
        "middle of — like dropping the learner into an episode. The runtime picks "
        "one at session start instead of a generic 'let's practice English' opener.",
        "items": {
            "type": "object",
            "properties": {
                "situation": {
                    "type": "string",
                    "description": "What's happening when the conversation starts — "
                    "a one-sentence scene setup, like 'you just walked in on me "
                    "mid-magic-trick'.",
                },
                "setup": {
                    "type": "string",
                    "description": "The character's opening line(s) for this scene. "
                    "Should sound like the character is already in the middle of "
                    "something when the learner arrives. No teaching language.",
                },
                "possible_targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hints for which English expressions might "
                    "naturally come up in this scene. Not mandatory — just cues "
                    "so the runtime can guide target selection.",
                },
            },
            "required": ["situation", "setup", "possible_targets"],
        },
    },
    "relationship_style": {
        "type": "object",
        "description": "How this character relates to the learner they're chatting with.",
        "properties": {
            "address_terms": {"type": "array", "items": {"type": "string"},
                "description": "What they tend to call the person they're talking to."},
            "encouragement_style": {"type": "string", "description": "How they "
                "encourage the learner, in their voice."},
            "teasing_style": {"type": "string", "description": "How they tease/"
                "needle the learner, in their voice (if they do at all)."},
        },
        "required": ["address_terms", "encouragement_style", "teasing_style"],
    },
    "avoid": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Character-specific pitfalls per rule 3 — each one must "
        "name something that would NOT equally apply to other characters of the "
        "same archetype.",
    },
}


# --- persona generation -----------------------------------------------------
# Builds the CARD layer for a user-requested character (teaching rules stay in
# the template above). No web access on this gateway — the model relies on its
# own knowledge; for obscure characters it may invent, which the hard rules
# above are meant to catch (label as "reconstructed" rather than pass off as fact).
_PERSONA_SYSTEM_PROMPT = f"""\
You design a roleplay CARD for an English-conversation practice app. Given a
show and a character from it, you produce a structured card the app uses to
speak as that character. You do NOT write teaching rules — the app adds those
separately.

{_CARD_HARD_RULES}

Return your result by calling the `report_persona` tool with these fields:

{_RENAME_RULE_TEXT}

- intro: one short first-person catchphrase in the character's voice (English,
  or mixed with a little Chinese if it fits), like a chat-app status line. See
  the built-ins: "I've got a Fil-osophy for every situation. You're welcome."

- card: the structured card (voice, signature_moves, format_style,
  opening_variants, signature_greetings, world_memory, signature_situations,
  opening_scenes, relationship_style, avoid) — this is a single, complete
  card, so aim for 2-4 signature_moves, 2-3 opening_variants,
  0-3 signature_greetings (only when you have reliable evidence -- empty list
  is the safe default for most characters), 5-10 world_memory entries,
  3-5 signature_situations, and 2-4 opening_scenes.
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
                "card": {
                    "type": "object",
                    "properties": _CARD_SCHEMA_PROPERTIES,
                    "required": list(_CARD_SCHEMA_PROPERTIES.keys()),
                },
            },
            "required": ["display_name", "intro", "card"],
        },
    },
}


# --- cast generation ---------------------------------------------------------
# Generating one auto-character per show left every non-built-in show with a
# cast of exactly one. This builds a whole main-cast group, but split into two
# stages so a bigger per-character schema doesn't blow up wall-clock time:
#   1. select_cast_characters() — ONE cheap call, no card fields at all, just
#      decides which ~6 characters to make.
#   2. _generate_starter_card() — ONE call PER selected character, fanned out
#      in a thread pool (see generate_cast_for_show) so total time is close to
#      a single character's generation time, not N times that.

_CAST_SELECT_SYSTEM_PROMPT = """\
You pick a roleplay CAST for an English-conversation practice app, covering
several of a show's main characters at once. Given a show name, and optionally
(a) parody names already used FOR THIS SHOW and (b) parody names already used
by OTHER shows, pick this show's main characters and rename each one. You do
NOT write personas here — that happens in a separate step, one character at a
time. Just pick names.

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
- For each character also write intro: one short first-person catchphrase in
  their voice, like a chat-app status line — e.g. "I've got a Fil-osophy for
  every situation. You're welcome."

Return your result by calling `report_cast_selection` with a `characters` array.
"""

_CAST_SELECT_TOOL = {
    "type": "function",
    "function": {
        "name": "report_cast_selection",
        "description": "Report which characters were picked for this show's cast.",
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
                        },
                        "required": ["original_name", "display_name", "intro"],
                    },
                },
            },
            "required": ["characters"],
        },
    },
}

# The per-character starter-card call — one of these runs per selected
# character, in parallel. Deliberately thinner than the full single-character
# card (generate_persona): fewer signature_moves, one opening_variant. The
# rest (format_style/relationship_style/avoid) are asked for in full since
# those are short lists anyway and don't meaningfully add to latency.
_STARTER_CARD_SYSTEM_PROMPT = f"""\
You design a STARTER roleplay card for one already-chosen character from a
show, for an English-conversation practice app. The name is already decided —
you only fill in the card. Keep this pass DELIBERATELY LIGHT: exactly 1-2
signature_moves and exactly 1 opening_variant (a fuller version gets generated
later, only if this character is actually picked for a chat). signature_greetings
should be an empty list at this stage -- leave them for the full-card completion.
Still give the full voice, format_style, relationship_style, and avoid — those are short and
worth getting right from the start.

{_CARD_HARD_RULES}

Return your result by calling `report_starter_card` with a `card` field.
"""

_STARTER_CARD_TOOL = {
    "type": "function",
    "function": {
        "name": "report_starter_card",
        "description": "Report the generated starter card for this character.",
        "parameters": {
            "type": "object",
            "properties": {"card": {
                "type": "object",
                "properties": _CARD_SCHEMA_PROPERTIES,
                "required": list(_CARD_SCHEMA_PROPERTIES.keys()),
            }},
            "required": ["card"],
        },
    },
}


def select_cast_characters(
    show: str,
    same_show_names: list[str] | None = None,
    other_show_names: list[str] | None = None,
) -> list[dict]:
    """Stage 1: pick which ~6 characters to generate for a show. One cheap call.

    Returns a list of {"original_name", "display_name", "intro"}, deduped
    against `same_show_names`/`other_show_names` and against name collisions
    within the batch itself. Does NOT generate any card content — see
    _generate_starter_card for stage 2.
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
        max_tokens=1200,
        temperature=0.9,
        extra_body=_NO_THINKING,
        tools=[_CAST_SELECT_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_cast_selection"}},
        messages=[
            {"role": "system", "content": _CAST_SELECT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw_items: list = []
    tool_calls = resp.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name == "report_cast_selection":
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
        if not display_name or not intro:
            continue
        norm = _norm_name(display_name)
        if not norm or norm in used_norm:
            continue  # duplicate within this batch or against an existing name
        if original_name and not _looks_renamed(original_name, display_name):
            continue  # rename too close to (or a truncation of) the real name
        used_norm.add(norm)
        result.append({
            "original_name": original_name,
            "display_name": display_name,
            "intro": intro,
        })
        if len(result) >= 8:
            break  # hard cap regardless of what the model returned
    return result


def _generate_starter_card(show: str, original_name: str, display_name: str) -> dict:
    """Stage 2, one character: generate just the starter card. Returns {} on
    any parse failure — the caller drops that character rather than failing
    the whole batch (see generate_cast_for_show)."""
    prompt = (
        f"Show: {show}\nCharacter (real name): {original_name}\n"
        f"Parody rename already chosen: {display_name}"
    )
    resp = _client.chat.completions.create(
        model=config.API_MODEL,
        max_tokens=1200,
        temperature=0.9,
        extra_body=_NO_THINKING,
        tools=[_STARTER_CARD_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_starter_card"}},
        messages=[
            {"role": "system", "content": _STARTER_CARD_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    tool_calls = resp.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name == "report_starter_card":
            return json.loads(call.function.arguments).get("card") or {}
    return {}


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
    """Generate a full card for a new character via the model.

    Returns {"display_name", "intro", "card", "persona"} — "persona" is
    card flattened to the prompt text (via characters.flatten_card), so
    callers that only want the flat string (the DB write, export.js) don't
    need to know the card exists. Applies the rename rules from the prompt,
    then a backend check: if the rename looks too close to the original, retry
    ONCE with a stronger instruction; accept the second result either way so we
    never loop. Raises ValueError on empty inputs.
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
            max_tokens=1600,
            temperature=0.9,
            extra_body=_NO_THINKING,
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
                    "card": inp.get("card") or {},
                }
        return {"display_name": "", "intro": "", "card": {}}

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
    result["persona"] = characters.flatten_card(
        result["display_name"] or character, result["card"]
    )
    return result


def generate_cast_for_show(
    show: str,
    same_show_names: list[str] | None = None,
    other_show_names: list[str] | None = None,
    requested_count: int = 3,
) -> list[dict]:
    """Generate a whole main-cast top-up for a show.

    Used the first time a show is seen (or when it only has a handful of
    characters so far) so it gets a real cast to choose from instead of a
    single auto-picked character.

    Two stages: select_cast_characters() (one cheap call) decides names, then
    one starter-card call per selected character runs IN PARALLEL via a thread
    pool — so wall-clock stays close to one character's generation time
    regardless of how many characters get picked or how many fields the card
    schema carries. This is what keeps this endpoint from creeping toward the
    120s gunicorn worker timeout as the card schema grows.

    `same_show_names` / `other_show_names` behave as before (see
    select_cast_characters). Returns a list of {"display_name", "intro",
    "card", "persona", "card_tier": "starter"} — degrades gracefully: any
    character whose starter-card call fails or comes back malformed is
    dropped rather than sinking the whole batch.
    """
    selected = select_cast_characters(show, same_show_names, other_show_names)
    if not selected:
        return []

    def _build_one(item: dict) -> dict | None:
        try:
            card = _generate_starter_card(show, item["original_name"], item["display_name"])
        except Exception:  # noqa: BLE001 — one bad call must not sink the batch
            return None
        if not card:
            return None
        return {
            "display_name": item["display_name"],
            "intro": item["intro"],
            "card": card,
            "persona": characters.flatten_card(item["display_name"], card),
            "card_tier": "starter",
        }

    result: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(_MAX_PARALLEL_WORKERS, len(selected))
    ) as pool:
        for built in pool.map(_build_one, selected):
            if built is not None:
                result.append(built)
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


# --- lazy card completion ----------------------------------------------------
# A "starter" card (see chat.py module docstring) has only 1-2 signature_moves
# and 1 opening_variant. The first time that character is actually picked for a
# chat, top it up to "full" (3-5 moves, 2-3 openings) with one more model call,
# then persist it so every later session with this character reuses the full
# card for free. "legacy" characters (no card_json at all) and already-"full"
# ones are untouched.
_COMPLETE_CARD_SYSTEM_PROMPT = f"""\
You are expanding an EXISTING starter roleplay card for a character from a
show into a fuller one, for an English-conversation practice app. You will be
given the starter card as-is — keep voice/format_style/relationship_style/
avoid as they are unless you spot a real problem, but:
- Expand signature_moves to 3-5 TOTAL (keep the existing one(s), add more).
- Expand opening_variants to 2-3 TOTAL (keep the existing one, add more).
- Add signature_greetings: 0-3 entries, ONLY when you have reliable evidence
  of a recognisable character-specific greeting behaviour. Empty list is the
  safe default. Follow the same evidence rules as signature_moves.
- Expand world_memory to 5-10 concrete facts (events, relationships, habits,
  locations, long-running conflicts, jobs, hobbies).
- Expand signature_situations to 3-5 recurring scenes.
- Add 2-4 opening_scenes -- each with situation + setup + possible_targets.

{_CARD_HARD_RULES}

Return the COMPLETE card (every field, not just the new parts) by calling
`report_full_card`.
"""

_COMPLETE_CARD_TOOL = {
    "type": "function",
    "function": {
        "name": "report_full_card",
        "description": "Report the expanded, fuller card for this character.",
        "parameters": {
            "type": "object",
            "properties": {"card": {
                "type": "object",
                "properties": _CARD_SCHEMA_PROPERTIES,
                "required": list(_CARD_SCHEMA_PROPERTIES.keys()),
            }},
            "required": ["card"],
        },
    },
}


def _complete_card(show: str, display_name: str, starter_card: dict) -> dict:
    """One call: expand a starter card to full. Returns {} on parse failure."""
    prompt = (
        f"Show: {show}\nCharacter: {display_name}\n\n"
        f"Starter card so far:\n{json.dumps(starter_card, ensure_ascii=False, indent=2)}"
    )
    resp = _client.chat.completions.create(
        model=config.API_MODEL,
        max_tokens=1800,
        temperature=0.9,
        extra_body=_NO_THINKING,
        tools=[_COMPLETE_CARD_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_full_card"}},
        messages=[
            {"role": "system", "content": _COMPLETE_CARD_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    tool_calls = resp.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name == "report_full_card":
            return json.loads(call.function.arguments).get("card") or {}
    return {}


def _ensure_full_card(char: dict) -> dict:
    """Top up `char` to a "full" card if it's currently "starter". Best-effort:
    on any failure, returns `char` unchanged (chat proceeds on the starter card
    rather than blocking on a retry)."""
    if char.get("card_tier") != "starter" or not char.get("card"):
        return char
    try:
        completed = _complete_card(char["source_show"], char["name"], char["card"])
    except Exception:  # noqa: BLE001 — best-effort, fall back to the starter card
        return char
    if not completed:
        return char
    persona = characters.flatten_card(char["name"], completed)
    updated = characters.update_card(char["key"], completed, "full", persona)
    return updated or char


# --- signature-move / opening-variant rotation -------------------------------
# "选择角色 → 读取角色卡 → 挑选本次尚未使用的1~2个特征" — each model call that
# produces an in-character reply gets a fresh nudge toward 1-2 signature_moves
# the session hasn't leaned on yet, so a single move doesn't repeat every turn.
# No-op for legacy/cardless characters (nothing to rotate through).
_MOVES_PER_TURN = 2


def _pick_unused_moves(card: dict | None, used_names: set[str]) -> list[dict]:
    moves = (card or {}).get("signature_moves") or []
    if not moves:
        return []
    unused = [m for m in moves if m.get("name") not in used_names]
    if not unused:
        used_names.clear()  # everything's been used at least once — start a new lap
        unused = moves
    pool = unused[:]
    random.shuffle(pool)
    picked = pool[:_MOVES_PER_TURN]
    for m in picked:
        used_names.add(m.get("name", ""))
    return picked


def _feature_injection(card: dict | None, used_names: set[str]) -> str:
    """A short addendum to the system prompt nudging THIS reply toward 1-2
    not-yet-used signature moves. Empty string if the card has none."""
    picked = _pick_unused_moves(card, used_names)
    if not picked:
        return ""
    lines = [
        "\n\nFor THIS reply, if it fits naturally, lean into one of these "
        "signature moves (skip it if the moment genuinely doesn't call for it):"
    ]
    for m in picked:
        steps = " then ".join(m.get("steps") or [])
        lines.append(f"- {m.get('name', '')}: {steps}")
    return "\n".join(lines)


def _kickoff_instruction(card: dict | None, greeting: dict | None = None) -> str:
    """Build the kickoff instruction for the model.

    FIRST-TURN RULE: do NOT mention English, vocabulary, phrases, expressions,
    practice, learning, lessons, targets, tests, tutoring, or today's goals.
    Instead, pick one concrete situation from the character's world and begin
    in the middle of it. The target expressions are hidden context — never
    reveal that engineering in the opening.
    """
    openings = (card or {}).get("opening_variants") or []
    memories = (card or {}).get("world_memory") or []

    base = """
Begin as if the learner has casually entered your real life.

FIRST-TURN RULE:
Do NOT mention English, vocabulary, phrases, expressions, practice,
learning, lessons, targets, tests, tutoring, or today's goals.

Instead:
1. Pick ONE concrete situation, relationship, obsession, memory,
   problem, or running gag from your own world.
2. Begin in the middle of that situation.
3. Speak as the character would naturally speak about it.
4. Give the other person something easy and human to react to.
5. Keep it to 1-4 sentences.

The target expressions are hidden context for where the conversation
may eventually go. Do NOT reveal that engineering in the opening.
"""

    if memories:
        base += "\nPossible pieces of your world:\n- " + "\n- ".join(memories)

    if openings:
        base += (
            "\n\nUse this only as inspiration for the type of scene, "
            "not as a script to repeat verbatim:\n"
            + random.choice(openings)
        )

    return base


def _wrap_stella(messages: list[dict]) -> list[dict]:
    """Force Stella/animal-character output into the 'Woof. (Translation: ...)' format.

    The model is instructed to produce ONLY the semantic meaning of the bark
    (no 'Woof', no 'Translation:'). We strip any accidental wrapper the model
    might still generate, then re-wrap consistently so the UI always shows:
      Woof.
      (Translation: ...)
    """
    if not messages:
        return [{"text": "Woof.\n(Translation: ...)", "pause_before_ms": 0}]

    raw = " ".join(m.get("text", "") for m in messages).strip()

    # Model is instructed to produce semantic meaning only.
    # Clean accidental wrapper if it still generated one.
    raw = raw.removeprefix("Woof.").strip()
    raw = raw.removeprefix("Woof!").strip()
    if raw.startswith("(Translation:") and raw.endswith(")"):
        raw = raw[len("(Translation:"):-1].strip()

    return [{
        "text": f"Woof.\n(Translation: {raw})",
        "pause_before_ms": 0,
    }]


def _join_reply_text(messages: list[dict]) -> str:
    """Flatten a structured reply into plain text for the conversation history
    the model itself sees on later turns (the frontend gets the structured
    version; the model's own context doesn't need pause timing)."""
    return " ".join(m["text"] for m in messages if m.get("text"))


def start_session(character_key: str, expressions: list[str]) -> dict:
    """Create a session, choose target expressions, and get the opening line.

    The opening is generated by the model using kickoff instructions that
    pull from the character's world_memory and opening_variants — the first
    turn sounds like a character in the middle of their life, not a teacher
    starting a lesson.
    """
    char = characters.get(character_key)
    if not char:
        raise ValueError(f"Unknown character: {character_key!r}")
    char = _ensure_full_card(char)

    targets = _pick_targets(expressions)
    session_id = uuid.uuid4().hex
    system = _system_prompt(char["persona"], targets)
    card = char.get("card")
    used_moves: set[str] = set()

    # Stella: add the special instruction so model generates meaning only
    if character_key == "stella":
        system += (
            "\n\nFor Stella, generate ONLY the meaning of the bark. "
            "Do not write 'Woof' yourself. "
            "Do not write 'Translation:'. "
            "One short sentence only."
        )

    kickoff = _kickoff_instruction(card) + _feature_injection(card, used_moves)
    model_messages = _call_model_reply(system, [{"role": "user", "content": kickoff}])

    # Stella / animal-character: force output format
    if character_key == "stella":
        model_messages = _wrap_stella(model_messages)

    _sessions[session_id] = {
        "character": character_key,
        "char_name": char["name"],
        "system": system,
        "card": card,
        "used_moves": used_moves,
        "targets": targets,
        # Full turn history (user/assistant). The kickoff instruction is not
        # stored so it doesn't leak into later context.
        "history": [{"role": "assistant", "content": _join_reply_text(model_messages)}],
    }
    return {
        "session_id": session_id,
        "character": character_key,
        "targets": targets,
        "messages": model_messages,
    }


def turn(session_id: str, message: str) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        raise KeyError("Session not found or expired.")

    sess["history"].append({"role": "user", "content": message})
    system = sess["system"] + _feature_injection(sess["card"], sess["used_moves"])
    messages = _call_model_reply(system, sess["history"])

    # Stella / animal-character: force output format on every turn
    if sess["character"] == "stella":
        messages = _wrap_stella(messages)

    sess["history"].append({"role": "assistant", "content": _join_reply_text(messages)})

    user_turns = sum(1 for m in sess["history"] if m["role"] == "user")
    limit = _STELLA_TARGET_TURNS if sess["character"] == "stella" else _DEFAULT_TARGET_TURNS
    return {"messages": messages, "user_turns": user_turns, "suggest_end": user_turns >= limit}


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
        extra_body=_NO_THINKING,
        messages=[{"role": "system", "content": system}, *messages],
    )
    return (resp.choices[0].message.content or "").strip()


# In-character replies are forced through this tool so the frontend gets a
# proper message SEQUENCE (bubbles + pauses) instead of one blob of text with
# markdown the frontend has to interpret. `pause_before_ms` is optional and
# defaults to 0 (no beat before that bubble) — most replies are a single
# message with no pause; multi-message replies (a quick line, a beat, then the
# punchline) are for when the character's format_style/signature_move calls
# for it, not a mandatory pattern every reply must use.
_REPLY_TOOL = {
    "type": "function",
    "function": {
        "name": "report_reply",
        "description": "Report your in-character reply as an ordered message sequence.",
        "parameters": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "minItems": 1,
                    "description": "1-3 messages, in the order they should appear. "
                    "Usually just 1 — use more only when a beat/pause is actually "
                    "part of how this character talks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The message text. May use **bold** "
                                "for emphasis if that fits the character's "
                                "format_style — no other markup.",
                            },
                            "pause_before_ms": {
                                "type": "integer",
                                "description": "Milliseconds to pause before showing "
                                "this message (0 for the first message, or for any "
                                "message with no dramatic beat before it).",
                            },
                        },
                        "required": ["text"],
                    },
                },
            },
            "required": ["messages"],
        },
    },
}


def _call_model_reply(system: str, messages: list[dict]) -> list[dict]:
    """One model call for an in-character turn. Returns the frontend-facing
    message list: [{"text": str, "pause_before_ms": int}, ...]. Falls back to
    a single plain-text message if the tool call is missing/malformed, so a
    parsing hiccup degrades to today's single-bubble behavior rather than
    breaking the turn.
    """
    resp = _client.chat.completions.create(
        model=config.API_MODEL,
        max_tokens=700,
        temperature=0.9,
        extra_body=_NO_THINKING,
        tools=[_REPLY_TOOL],
        tool_choice={"type": "function", "function": {"name": "report_reply"}},
        messages=[{"role": "system", "content": system}, *messages],
    )
    tool_calls = resp.choices[0].message.tool_calls or []
    for call in tool_calls:
        if call.function.name == "report_reply":
            try:
                raw = json.loads(call.function.arguments).get("messages") or []
            except (json.JSONDecodeError, AttributeError):
                break
            out = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                pause = item.get("pause_before_ms") or 0
                try:
                    pause = max(0, int(pause))
                except (TypeError, ValueError):
                    pause = 0
                out.append({"text": text, "pause_before_ms": pause})
            if out:
                return out
    fallback = (resp.choices[0].message.content or "").strip()
    return [{"text": fallback, "pause_before_ms": 0}] if fallback else [
        {"text": "...", "pause_before_ms": 0}
    ]
