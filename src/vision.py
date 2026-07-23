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

3. NEVER extract any of the following, no matter what:
   - High-frequency / everyday words a learner already produces naturally.
   - Function words (articles, prepositions, pronouns, conjunctions, auxiliaries).
   - Interjections and fillers: huh, oh, um, uh, hmm, well, you know, I mean, like,
     yeah, okay, right, so, ah, hey, wow, etc.
   - Anything with no real semantic payload.

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
                    },
                    "required": [
                        "expression",
                        "meaning_zh",
                        "scenario_zh",
                        "original_line",
                        "difficulty",
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


_FIELD_KEYS = ("expression", "meaning_zh", "scenario_zh", "original_line", "difficulty")


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
        nxt = re.search(r'"(?:expression|meaning_zh|scenario_zh|original_line|difficulty)"\s*:',
                        chunk[start:])
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
        "difficulty": _extract_field(chunk, "difficulty", is_last=True),
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


def _parse_payload(payload: dict) -> ScreenshotAnalysis:
    expressions = []
    for item in _coerce_expression_list(payload.get("expressions", [])):
        if not isinstance(item, dict):
            continue
        expressions.append(
            Expression(
                expression=str(item.get("expression", "")).strip(),
                meaning_zh=str(item.get("meaning_zh", "")).strip(),
                scenario_zh=str(item.get("scenario_zh", "")).strip(),
                original_line=str(item.get("original_line", "")).strip(),
                difficulty=str(item.get("difficulty", "")).strip(),
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
