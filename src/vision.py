"""Send a screenshot to Claude via the Anthropic native Messages API and
extract learn-worthy English expressions."""
from __future__ import annotations

import ast
import base64
import json
import mimetypes
import re
from pathlib import Path

from anthropic import Anthropic

from . import config
from .models import Expression, ScreenshotAnalysis

_client = Anthropic(base_url=config.API_BASE_URL, api_key=config.API_KEY)

_SYSTEM_PROMPT = """\
You are an English-learning assistant for an ADVANCED Chinese learner who watches
English TV shows and films. Their comprehension is strong — they understand almost
everything they hear. What they want to learn is the gap between "understanding" and
"being able to produce it themselves".

You are given a screenshot that may contain English subtitles or on-screen text.

Your job:
1. Read any English subtitle / caption / on-screen text in the image.
2. Extract ONLY mid-to-low-frequency expressions that carry real semantic content
   and sound native — idioms, phrasal verbs, fixed collocations, and slang. The
   test for each candidate is: "A well-educated English learner understands this,
   but wouldn't think to use it themselves when speaking." Extract only what passes
   that test.

   CITATION FORM — the `expression` you output is a DICTIONARY HEADWORD, not the
   inflected form from the subtitle. Normalize every time:
   - Restore the verb to its BASE form. Strip tense and -ing/-ed unless the
     expression is inherently progressive (rare). So a subtitle saying "he was
     playing it cool" yields `play it cool`, not `playing it cool`.
   - For SEPARABLE phrasal verbs, mark the object slot with `sb.` / `sth.` in its
     correct position. The object of a separable verb goes BETWEEN the verb and
     the particle, so the citation form must reflect that:
       · subtitle "she let her hair down"   -> `let sb.'s hair down`  (NOT "let down one's hair")
       · subtitle "he flipped out on me"     -> `flip out on sb.`
       · subtitle "the meds pulled him through" -> `pull sb. through`
   - Normalize possessives/pronouns to `one's` / `sb.` / `sth.` — never `your`,
     `his`, `her`, `my`. So "lose your cool" -> `lose one's cool`.

3. NEVER extract any of the following, no matter what:
   - High-frequency / everyday words a learner already produces naturally.
   - Function words (articles, prepositions, pronouns, conjunctions, auxiliaries).
   - Interjections and fillers: huh, oh, um, uh, hmm, well, you know, I mean, like,
     yeah, okay, right, so, ah, hey, wow, etc.
   - Anything with no real semantic payload.
   - LITERAL verb + noun combinations (the noun being a proper noun OR a plain
     common noun) where every word is common AND the combination has NO figurative
     or extended meaning. If pulling the phrase apart explains it fully, it is not
     an idiom — skip it. Counter-examples that must be REJECTED: `play craps`,
     `watch TV`, `take a bus`, `drive a car`, `open the door`. Contrast with
     expressions that must be KEPT because the whole means more than the parts:
     `hang by a thread`, `call it a day`, `hit the sack`, `spill the beans`.

   Example: for the subtitle "Oh, she's a bummer, huh?" the ONLY valid extraction
   is `bummer`. Do NOT extract "huh", "oh", or "she's".

4. The user took this screenshot ON PURPOSE, so it almost always contains something
   worth learning. Strongly prefer to return at least one expression — but that
   expression MUST clear the bar in steps 2–3. Never pad the result with a filler,
   interjection, or high-frequency word just to avoid an empty list. If, after an
   honest read, NOTHING in the frame qualifies, return an empty expressions list
   rather than a junk card. Prefer one strong pick over several weak ones.

5. For each item give: a Chinese meaning, a short Chinese note on when/how it is
   used, the ORIGINAL LINE it appeared in (the full subtitle/caption verbatim, as
   read from the image — do NOT invent an example), and a difficulty rating.
   The difficulty MUST be exactly one of: 初级, 中级, 高级.

6. Also write ONE brand-new `review_sentence` for spaced-repetition practice.
   Requirements:
   - Make it a MINI-SCENARIO: 2-3 short sentences that together form a tiny
     spoken situation — a snippet of dialogue or a little story — NOT a single
     isolated sentence. It must read like real conversational English.
   - Compose it fresh. Do NOT copy or lightly reword the original line.
   - Prefer the same kind of everyday situation as the screenshot (you have seen
     the frame), but if the scene isn't clear, invent a natural daily-life
     scenario. It must stand on its own without the image.
   - CRITICAL: the surrounding sentences must give enough semantic clues that an
     advanced learner can INFER the blanked expression from context alone.
   - Difficulty: everyday spoken register, just slightly challenging — the kind
     of thing a native speaker would actually say. Idiomatic and natural.
   - Replace the target expression with exactly three underscores `___`, exactly
     ONE blank in the whole scenario, placed where the expression naturally goes.
     Example, for "off your game":
     "You've missed three easy shots in a row today. What's going on — you're
     usually so sharp out there. Are you feeling okay, or are you just ___?"

7. Also give a `common_structure`: the expression's IDIOMATIC COLLOCATION FRAME,
   written with placeholders for the slots a speaker fills in — NOT the expression
   copied verbatim. Use `sb.` / `sth.` for people/things, `one's` for possessives,
   and `(...)` for optional parts. Separate genuinely distinct patterns with ` / `.
   Examples:
     - "pull through"      -> "pull sb. through / pull through sth."
     - "hang by a thread"  -> "be hanging by a thread"
     - "flip out"          -> "flip out (on sb.)"
     - "get the hang of"   -> "get the hang of sth."
   HARD RULES:
   - The value MUST NOT be identical to `expression`. If the only thing you could
     write is the expression itself, that means it has no useful frame — return an
     empty string "" instead.
   - If the expression is already a fixed, invariant form with no slots or
     collocation variants to teach, return an empty string "".
   - Keep it to the frame only — no Chinese, no explanation, no example sentence.

Always report your result by calling the `report_expressions` tool.
"""

# Tool schema forces the model into valid structured output — no fragile JSON
# parsing of free-form text.
_TOOL = {
    "name": "report_expressions",
    "description": "Report the English expressions extracted from the screenshot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subtitle_text": {
                "type": "string",
                "description": "The raw English text read from the image, or empty string.",
            },
            "expressions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"},
                        "meaning_zh": {"type": "string"},
                        "scenario_zh": {"type": "string"},
                        "original_line": {
                            "type": "string",
                            "description": "The full original subtitle line this "
                            "expression appeared in, verbatim from the image.",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["初级", "中级", "高级"],
                        },
                        "review_sentence": {
                            "type": "string",
                            "description": "A NEW spoken-English sentence for review "
                            "practice, related to the scene, with the target "
                            "expression replaced by exactly three underscores ___.",
                        },
                        "common_structure": {
                            "type": "string",
                            "description": "The expression's idiomatic collocation "
                            "frame with placeholders (sb./sth./one's/optional "
                            "parts), e.g. 'pull sb. through / pull through sth.'. "
                            "MUST NOT equal the expression verbatim; empty string "
                            "if the form is fixed with no variant to teach.",
                        },
                    },
                    "required": [
                        "expression",
                        "meaning_zh",
                        "scenario_zh",
                        "original_line",
                        "difficulty",
                        "review_sentence",
                        "common_structure",
                    ],
                },
            },
        },
        "required": ["subtitle_text", "expressions"],
    },
}


def _encode_image(path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, data


_FIELD_KEYS = (
    "expression",
    "meaning_zh",
    "scenario_zh",
    "original_line",
    "difficulty",
    "review_sentence",
    "common_structure",
)


def _extract_field(chunk: str, key: str, is_last: bool) -> str:
    """Pull one field value out of a broken object chunk by anchoring on the
    key name and the next key (or the closing brace), tolerating unescaped
    quotes inside the value. Returns the raw value text (quotes stripped)."""
    m = re.search(rf'"{key}"\s*:\s*', chunk)
    if not m:
        return ""
    start = m.end()
    # Value ends where the next known key begins, else at the last brace.
    end = len(chunk)
    if not is_last:
        keys = "|".join(_FIELD_KEYS)
        nxt = re.search(rf'"(?:{keys})"\s*:', chunk[start:])
        if nxt:
            end = start + nxt.start()
    value = chunk[start:end].strip()
    value = value.rstrip(",").strip()
    # Strip one layer of surrounding quotes and a trailing comma/brace.
    value = value.rstrip("}").strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == '"':
        value = value[1:]
        if value.endswith('"'):
            value = value[:-1]
    return value.strip()


def _loads_loose(text: str):
    """Parse a chunk that is either JSON or a Python literal (single-quoted
    dict repr) — this gateway emits both. Returns the object or None."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _salvage_object(chunk: str) -> dict | None:
    """Last resort for an object whose string values contain unescaped quotes:
    extract each known field positionally instead of parsing JSON."""
    expr = _extract_field(chunk, "expression", is_last=False)
    if not expr:
        return None
    return {
        "expression": expr,
        "meaning_zh": _extract_field(chunk, "meaning_zh", is_last=False),
        "scenario_zh": _extract_field(chunk, "scenario_zh", is_last=False),
        "original_line": _extract_field(chunk, "original_line", is_last=False),
        "difficulty": _extract_field(chunk, "difficulty", is_last=False),
        "review_sentence": _extract_field(chunk, "review_sentence", is_last=False),
        "common_structure": _extract_field(chunk, "common_structure", is_last=True),
    }


def _coerce_expression_list(raw) -> list:
    """This gateway sometimes returns `expressions` as a *string* instead of an
    array — sometimes valid JSON, sometimes a single-quoted Python repr, and
    occasionally with unescaped quotes inside. Recover a list of dicts."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        whole = _loads_loose(text)
        if isinstance(whole, list):
            return whole
        # Salvage each object by locating balanced {...} chunks and parsing
        # them individually; skip any that are still malformed.
        items, depth, start = [], 0, None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    chunk = text[start : i + 1]
                    obj = _loads_loose(chunk)
                    if not isinstance(obj, dict):
                        obj = _salvage_object(chunk)
                    if isinstance(obj, dict):
                        items.append(obj)
                    start = None
        return items
    return []


def _norm_structure(s: str) -> str:
    """Loose key for the 'structure == expression' guard: lowercase, collapse
    whitespace, drop trailing punctuation, so 'Pull through.' == 'pull through'."""
    return re.sub(r"\s+", " ", str(s or "").lower()).strip().strip(".!?,;: ")


def _parse_payload(payload: dict) -> ScreenshotAnalysis:
    expressions = []
    for item in _coerce_expression_list(payload.get("expressions", [])):
        if not isinstance(item, dict):
            continue
        expr_text = str(item.get("expression", "")).strip()
        structure = str(item.get("common_structure", "")).strip()
        # Belt-and-suspenders against the very thing this field exists to avoid:
        # if the model echoed the expression verbatim, treat it as "no frame".
        if _norm_structure(structure) == _norm_structure(expr_text):
            structure = ""
        expressions.append(
            Expression(
                expression=expr_text,
                meaning_zh=str(item.get("meaning_zh", "")).strip(),
                scenario_zh=str(item.get("scenario_zh", "")).strip(),
                original_line=str(item.get("original_line", "")).strip(),
                difficulty=str(item.get("difficulty", "")).strip(),
                review_sentence=str(item.get("review_sentence", "")).strip(),
                common_structure=structure,
            )
        )
    expressions = [e for e in expressions if e.expression]
    return ScreenshotAnalysis(
        subtitle_text=str(payload.get("subtitle_text", "")).strip(),
        expressions=expressions,
    )


def analyze_screenshot(path: Path) -> ScreenshotAnalysis:
    """Analyze one image and return the extracted expressions."""
    mime, data = _encode_image(path)
    message = _client.messages.create(
        model=config.API_MODEL,
        max_tokens=2048,
        temperature=0.3,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "report_expressions"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract learn-worthy English expressions from this screenshot.",
                    },
                ],
            }
        ],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "report_expressions":
            return _parse_payload(block.input)
    return ScreenshotAnalysis()


_REVIEW_SYSTEM_PROMPT = """\
You help an ADVANCED Chinese learner of English review expressions they saved
while watching TV. Given ONE target expression plus context about where it came
from, write ONE brand-new practice MINI-SCENARIO.

Requirements:
- Write 2-3 short sentences that together form a tiny spoken situation — a
  snippet of dialogue or a little story — NOT a single isolated sentence. It
  must read like real conversational English.
- Compose it fresh. Do NOT copy or lightly reword the original line.
- Set it in the same kind of everyday situation as the original context if you
  can infer one; otherwise invent a natural daily-life scenario. It must stand
  on its own.
- CRITICAL: the surrounding sentences must give enough semantic clues that an
  advanced learner can INFER the blanked expression from context alone.
- Difficulty: everyday spoken register, just slightly challenging — the kind of
  thing a native speaker would actually say. Idiomatic and natural.
- Replace the target expression with exactly three underscores `___`, exactly
  ONE blank in the whole scenario, placed where the expression naturally goes.
  Example, for "off your game":
  "You've missed three easy shots in a row today. What's going on — you're
  usually so sharp. Are you feeling okay, or are you just ___?"

Always report your result by calling the `report_review_sentence` tool.
"""

_REVIEW_TOOL = {
    "name": "report_review_sentence",
    "description": "Report the new review practice sentence for the expression.",
    "input_schema": {
        "type": "object",
        "properties": {
            "review_sentence": {
                "type": "string",
                "description": "A NEW spoken-English sentence with the target "
                "expression replaced by exactly three underscores ___.",
            },
        },
        "required": ["review_sentence"],
    },
}


def generate_review_sentence(
    expression: str,
    context: str = "",
    chinese: str = "",
    example: str = "",
) -> str:
    """Generate a fresh cloze review sentence from an expression's stored fields.

    Text-only sibling of `analyze_screenshot` for backfilling old cards. Returns
    the sentence (with a `___` blank) or "" if the model didn't produce a usable
    one — the caller decides whether to skip.
    """
    expr = (expression or "").strip()
    if not expr:
        return ""

    lines = [f"Target expression: {expr}"]
    if chinese.strip():
        lines.append(f"Chinese meaning: {chinese.strip()}")
    if context.strip():
        lines.append(f"Usage note / scenario (Chinese): {context.strip()}")
    if example.strip():
        lines.append(
            f"Original line it appeared in (do NOT reuse this verbatim): "
            f"{example.strip()}"
        )
    lines.append(
        "Write one new practice sentence with the expression blanked as ___."
    )
    prompt = "\n".join(lines)

    message = _client.messages.create(
        model=config.API_MODEL,
        max_tokens=512,
        temperature=0.7,
        system=_REVIEW_SYSTEM_PROMPT,
        tools=[_REVIEW_TOOL],
        tool_choice={"type": "tool", "name": "report_review_sentence"},
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "report_review_sentence":
            sentence = str(block.input.get("review_sentence", "")).strip()
            return sentence if "___" in sentence else ""
    return ""
