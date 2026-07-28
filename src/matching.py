"""Answer-judging and hint generation for the three-layer reviewer.

All of this runs server-side so the browser never has to reason about English
morphology. The one hard requirement from the design is *inflection-tolerant*
matching: "hang by a thread" must accept "hanging / was hanging / hung / hangs
by a thread" but reject "by a thread hanging" (wrong order) and "hang" (missing
words).

The approach:
  1. normalize   — lowercase, collapse spaces, drop trailing punctuation
  2. exact hit   — normalized strings equal → correct
  3. fuzzy hit   — reduce both sides to *core words* (drop articles/be-verbs),
     stem each core word, then require the target's core-stem sequence to appear
     as a contiguous run inside the guess's core-stem sequence (order preserved).
"""
from __future__ import annotations

import re

# Words stripped when extracting the "core" of an expression for matching.
# These carry grammar, not meaning, so a learner shouldn't be marked wrong for
# adding/dropping them ("was hanging" vs "hanging").
_HELPER_WORDS = {
    "a", "an", "the",
    "be", "is", "are", "was", "were", "been", "being", "am", "'s", "s",
    "to", "do", "does", "did",
    "will", "would", "have", "has", "had",
}

# A small irregular-verb map so common non-regular inflections collapse to one
# stem (Porter-style suffix stripping can't reach "hung" → "hang"). Inflected
# form → base form. Kept intentionally short: just the verbs likely to show up
# in idioms.
_IRREGULAR = {
    "hung": "hang", "hangs": "hang", "hanging": "hang",
    "went": "go", "gone": "go", "goes": "go", "going": "go",
    "got": "get", "gotten": "get", "gets": "get", "getting": "get",
    "took": "take", "taken": "take", "takes": "take", "taking": "take",
    "came": "come", "comes": "come", "coming": "come",
    "gave": "give", "given": "give", "gives": "give", "giving": "give",
    "made": "make", "makes": "make", "making": "make",
    "ran": "run", "runs": "run", "running": "run",
    "held": "hold", "holds": "hold", "holding": "hold",
    "blew": "blow", "blown": "blow", "blows": "blow", "blowing": "blow",
    "threw": "throw", "thrown": "throw", "throws": "throw", "throwing": "throw",
    "broke": "break", "broken": "break", "breaks": "break", "breaking": "break",
    "kept": "keep", "keeps": "keep", "keeping": "keep",
    "lost": "lose", "loses": "lose", "losing": "lose",
    "paid": "pay", "pays": "pay", "paying": "pay",
    "put": "put", "puts": "put", "putting": "put",
    "cut": "cut", "cuts": "cut", "cutting": "cut",
    "let": "let", "lets": "let", "letting": "let",
    "fell": "fall", "fallen": "fall", "falls": "fall", "falling": "fall",
    "drew": "draw", "drawn": "draw", "draws": "draw", "drawing": "draw",
    "sat": "sit", "sits": "sit", "sitting": "sit",
    "stood": "stand", "stands": "stand", "standing": "stand",
    "caught": "catch", "catches": "catch", "catching": "catch",
    "bought": "buy", "buys": "buy", "buying": "buy",
    "brought": "bring", "brings": "bring", "bringing": "bring",
    "left": "leave", "leaves": "leave", "leaving": "leave",
}

# Small words that stay whole (not blanked) in the initial-letter hint.
_KEEP_WHOLE = {"a", "an", "the", "by", "in", "on", "of", "at", "to", "up", "off"}

_TRAILING_PUNCT = ".,!?;:'\"“”‘’…、。！？，；："


def normalize(text: str) -> str:
    """Lowercase, collapse inner whitespace, trim, drop trailing punctuation."""
    s = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return s.rstrip(_TRAILING_PUNCT).strip()


def _stem(word: str) -> str:
    """Reduce a word to a crude stem so inflected forms collapse together.

    Irregular forms are looked up directly; everything else goes through a short
    ordered list of suffix-stripping rules (-ing/-ed/-ies/-es/-s) plus a
    doubled-consonant fix so "running" → "run" rather than "runn".
    """
    w = word.strip(_TRAILING_PUNCT).lower()
    if not w:
        return ""
    if w in _IRREGULAR:
        return _IRREGULAR[w]

    if len(w) > 4 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ied"):
        return w[:-3] + "y"
    elif len(w) > 3 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    elif len(w) > 3 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]

    # collapse a doubled final consonant left by -ing/-ed stripping
    if len(w) >= 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
        w = w[:-1]
    return w


def _core_stems(text: str) -> list[str]:
    """Split into words, drop helper words, return the stem of each remainder."""
    stems = []
    for tok in normalize(text).split():
        if tok in _HELPER_WORDS:
            continue
        stems.append(_stem(tok))
    return [s for s in stems if s]


def _contiguous_sublist(needle: list[str], haystack: list[str]) -> bool:
    """True if `needle` appears as a contiguous run inside `haystack`."""
    n, h = len(needle), len(haystack)
    if n == 0 or n > h:
        return False
    for start in range(h - n + 1):
        if haystack[start : start + n] == needle:
            return True
    return False


def is_correct(guess: str, expression: str) -> bool:
    """Judge a typed answer against the target expression.

    Exact (normalized) match wins immediately. Otherwise the target's core-word
    stems must appear, in order and contiguously, within the guess's core-word
    stems — so extra leading helpers ("was …") are fine but reordering or
    dropping content words is not.
    """
    g_norm, e_norm = normalize(guess), normalize(expression)
    if not g_norm or not e_norm:
        return False
    if g_norm == e_norm:
        return True

    target = _core_stems(expression)
    got = _core_stems(guess)
    if not target:
        # Expression is all helper words; fall back to the exact check above.
        return g_norm == e_norm
    return _contiguous_sublist(target, got)


def initials_hint(expression: str) -> str:
    """Turn an expression into a first-letter hint.

    Content words become "first-letter + underscores" (one underscore per
    remaining letter); small function words in `_KEEP_WHOLE` stay intact.
    "hanging by a thread" → "h______ by a t_____".
    """
    parts = []
    for raw in str(expression or "").split():
        low = raw.lower().strip(_TRAILING_PUNCT)
        if low in _KEEP_WHOLE:
            parts.append(raw)
            continue
        if len(raw) <= 1:
            parts.append(raw)
            continue
        parts.append(raw[0] + "_" * (len(raw) - 1))
    return " ".join(parts)


def common_structure(expression: str, example: str = "") -> str:
    """A short 'typical form' hint shown in the final layer.

    We don't have a dedicated field for this, so we derive it: if the expression
    starts with a bare base verb, prefix "be " to signal the usual copular frame
    (e.g. "hang by a thread" → "be hanging by a thread" is not attempted — we
    keep it honest and just present the canonical expression). Callers may show
    this alongside the verbatim Example line.
    """
    expr = str(expression or "").strip()
    return expr
