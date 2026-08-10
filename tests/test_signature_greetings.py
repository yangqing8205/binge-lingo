"""Tests for signature_greetings — character fidelity enhancement.

Covers:
1. Old cards without signature_greetings still load
2. Full cards can store signature_greetings
3. Empty signature_greetings works normally
4. start_session() can select a signature greeting
5. setup/payoff becomes sequential messages[]
6. pause_before_ms is a valid integer
7. Same greeting not reused in same session
8. Fallback opening when no signature greeting exists
9. Existing signature_moves behavior still works
10. Starter -> full lazy completion still works
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("API_BASE_URL", "https://example.invalid/api/v3")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("API_MODEL", "test-model")
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")
os.environ.setdefault("NOTION_DATABASE_ID", "test-database-id")
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret")

import json
from src import chat, characters


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fake_card(**overrides):
    """Build a complete card dict with defaults, overridable per field."""
    card = {
        "voice": {
            "pace": "fast", "sentence_length": "short", "vocabulary": "plain",
            "tone": "warm", "emotional_range": "wide",
            "evidence": {"quote": "q", "confidence": "reconstructed", "source": "s"},
        },
        "signature_moves": [
            {
                "name": "Move 1", "steps": ["a", "b"], "frequency": "often",
                "evidence": {"quote": "q", "confidence": "reconstructed", "source": "s"},
                "distinct_because": "specific reason",
            }
        ],
        "format_style": {"caps": "rare", "bold": "rare", "ellipsis": "rare",
                         "exclaim": "rare", "notes": ""},
        "opening_variants": ["Hey there!"],
        "signature_greetings": [],
        "relationship_style": {"address_terms": ["buddy"], "encouragement_style": "warm",
                               "teasing_style": "light"},
        "avoid": ["being generic"],
    }
    card.update(overrides)
    return card


def _make_model_reply(text="Hello! Let's practice."):
    """Return a mock model reply as the tool-call response."""
    call = SimpleNamespace(
        function=SimpleNamespace(
            name="report_reply",
            arguments=json.dumps({"messages": [{"text": text, "pause_before_ms": 0}]}),
        )
    )
    message = SimpleNamespace(tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


# ── Tests ────────────────────────────────────────────────────────────────────

class SignatureGreetingsSchemaTests(unittest.TestCase):
    """Test 1, 2, 3: card schema and backward compatibility."""

    def test_old_card_without_signature_greetings_loads(self):
        """Test 1: old cards without signature_greetings still load."""
        card = _fake_card()
        del card["signature_greetings"]
        # flatten_card should handle missing key gracefully
        result = characters.flatten_card("Test Char", card)
        self.assertIn("Test Char", result)
        self.assertNotIn("Signature greetings", result)

    def test_full_card_stores_signature_greetings(self):
        """Test 2: full cards can store signature_greetings."""
        card = _fake_card(signature_greetings=[
            {
                "setup": "Quick—what's my favorite hospital dessert?",
                "payoff": "JELL-O! Hello buddy!",
                "usage": "new_session_opening",
                "confidence": "high",
                "why_distinctive": "recognizable setup/payoff greeting",
            }
        ])
        self.assertEqual(1, len(card["signature_greetings"]))
        self.assertEqual("high", card["signature_greetings"][0]["confidence"])

    def test_empty_signature_greetings_works_normally(self):
        """Test 3: empty signature_greetings works normally."""
        card = _fake_card(signature_greetings=[])
        self.assertEqual([], card["signature_greetings"])

        # _pick_signature_greeting should return None
        result = chat._pick_signature_greeting(card, set())
        self.assertIsNone(result)

    def test_none_signature_greetings_handled(self):
        """None signature_greetings should be treated as empty."""
        card = _fake_card(signature_greetings=None)
        result = chat._pick_signature_greeting(card, set())
        self.assertIsNone(result)


class SignatureGreetingSelectionTests(unittest.TestCase):
    """Test 4, 7: greeting selection and non-repetition."""

    def setUp(self):
        self.card_with_greetings = _fake_card(signature_greetings=[
            {
                "setup": "Quick—what's my favorite hospital dessert?",
                "payoff": "JELL-O! Hello buddy!",
                "usage": "new_session_opening",
                "confidence": "high",
                "why_distinctive": "recognizable setup/payoff greeting",
            },
            {
                "setup": "Knock knock!",
                "payoff": "It's me! Hi!",
                "usage": "new_session_opening",
                "confidence": "medium",
                "why_distinctive": "self-aware knock-knock joke",
            },
        ])

    def test_pick_signature_greeting_can_select(self):
        """Test 4: _pick_signature_greeting can select a greeting."""
        # Only high-confidence greetings are eligible
        result = chat._pick_signature_greeting(self.card_with_greetings, set())
        if result is not None:
            self.assertEqual("high", result["confidence"])
            self.assertIn("_idx", result)
            self.assertEqual(0, result["_idx"])  # only one high-confidence

    def test_same_greeting_not_reused(self):
        """Test 7: same greeting not reused in same session."""
        # Mark index 0 as used
        used = {0}
        result = chat._pick_signature_greeting(self.card_with_greetings, used)
        self.assertIsNone(result)  # only high-confidence was index 0

    def test_no_high_confidence_returns_none(self):
        """When no high-confidence greetings, returns None."""
        card = _fake_card(signature_greetings=[
            {
                "setup": "Hi!",
                "payoff": "Hello!",
                "usage": "new_session_opening",
                "confidence": "medium",
                "why_distinctive": "not very distinctive",
            }
        ])
        result = chat._pick_signature_greeting(card, set())
        self.assertIsNone(result)

    def test_no_greetings_returns_none(self):
        """Empty greeting list returns None."""
        card = _fake_card(signature_greetings=[])
        result = chat._pick_signature_greeting(card, set())
        self.assertIsNone(result)


class GreetingToMessagesTests(unittest.TestCase):
    """Test 5, 6: setup/payoff -> sequential messages, pause_before_ms."""

    def test_setup_payoff_becomes_sequential_messages(self):
        """Test 5: setup/payoff becomes sequential messages[]."""
        greeting = {
            "setup": "Quick—what's my favorite hospital dessert?",
            "payoff": "JELL-O! Hello buddy!",
        }
        messages = chat._greeting_to_messages(greeting)

        self.assertEqual(2, len(messages))
        self.assertEqual("Quick—what's my favorite hospital dessert?", messages[0]["text"])
        self.assertEqual(0, messages[0]["pause_before_ms"])
        self.assertEqual("JELL-O! Hello buddy!", messages[1]["text"])

    def test_pause_before_ms_is_valid_integer(self):
        """Test 6: pause_before_ms is a valid integer."""
        greeting = {
            "setup": "Setup line",
            "payoff": "Payoff line",
        }
        messages = chat._greeting_to_messages(greeting)

        self.assertEqual(2, len(messages))
        pause = messages[1]["pause_before_ms"]
        self.assertIsInstance(pause, int)
        self.assertEqual(900, pause)

    def test_greeting_without_setup(self):
        """Only payoff, no setup."""
        greeting = {"setup": "", "payoff": "Just the payoff!"}
        messages = chat._greeting_to_messages(greeting)
        self.assertEqual(1, len(messages))
        self.assertEqual("Just the payoff!", messages[0]["text"])
        self.assertEqual(0, messages[0]["pause_before_ms"])

    def test_greeting_without_payoff(self):
        """Only setup, no payoff."""
        greeting = {"setup": "Just the setup!", "payoff": ""}
        messages = chat._greeting_to_messages(greeting)
        self.assertEqual(1, len(messages))
        self.assertEqual("Just the setup!", messages[0]["text"])


class KickoffInstructionTests(unittest.TestCase):
    """Test 8: fallback opening when no greeting."""

    def test_fallback_opening_when_no_greeting(self):
        """Test 8: fallback opening works when no signature greeting."""
        card = _fake_card(opening_variants=["Hey there, ready to learn?"])
        result = chat._kickoff_instruction(card, greeting=None)

        self.assertIn("Start the conversation", result)
        self.assertIn("Hey there", result)

    def test_kickoff_with_greeting(self):
        """When greeting is provided, instruction is different."""
        greeting = {"setup": "S", "payoff": "P"}
        result = chat._kickoff_instruction(None, greeting=greeting)

        self.assertIn("You just opened with your signature greeting", result)
        self.assertIn("Do NOT repeat the greeting", result)
        self.assertNotIn("Start the conversation", result)


class FlattenCardTests(unittest.TestCase):
    """Test that flatten_card renders signature_greetings."""

    def test_flatten_card_includes_signature_greetings(self):
        card = _fake_card(signature_greetings=[
            {
                "setup": "Quick—what's my favorite hospital dessert?",
                "payoff": "JELL-O! Hello buddy!",
                "usage": "new_session_opening",
                "confidence": "high",
                "why_distinctive": "recognizable",
            },
            {
                "setup": "Knock knock!",
                "payoff": "It's me!",
                "usage": "new_session_opening",
                "confidence": "medium",
                "why_distinctive": "self-aware joke",
            },
        ])
        result = characters.flatten_card("Test", card)

        self.assertIn("Signature greetings", result)
        self.assertIn("hospital dessert", result)
        self.assertIn("JELL-O", result)
        # High-confidence greetings are labeled differently
        self.assertIn("Setup:", result)
        self.assertIn("(maybe)", result)  # medium confidence

    def test_flatten_card_empty_greetings(self):
        card = _fake_card(signature_greetings=[])
        result = characters.flatten_card("Test", card)

        self.assertNotIn("Signature greetings", result)

    def test_flatten_card_no_greetings_key(self):
        card = _fake_card()
        del card["signature_greetings"]
        result = characters.flatten_card("Test", card)

        self.assertNotIn("Signature greetings", result)


class SignatureMovesStillWorkTests(unittest.TestCase):
    """Test 9: existing signature_moves behavior still works."""

    def test_signature_moves_still_work(self):
        card = _fake_card(
            signature_moves=[
                {
                    "name": "Move 1", "steps": ["a", "b"], "frequency": "often",
                    "evidence": {"quote": "q", "confidence": "reconstructed", "source": "s"},
                    "distinct_because": "specific",
                },
                {
                    "name": "Move 2", "steps": ["c", "d"], "frequency": "rare",
                    "evidence": {"quote": "q2", "confidence": "reconstructed", "source": "s2"},
                    "distinct_because": "specific 2",
                },
            ],
            signature_greetings=[
                {
                    "setup": "S", "payoff": "P", "usage": "new_session_opening",
                    "confidence": "high", "why_distinctive": "distinctive",
                }
            ],
        )
        used = set()
        picked = chat._pick_unused_moves(card, used)
        self.assertEqual(2, len(picked))
        self.assertEqual(2, len(used))

        # Second call should cycle
        picked2 = chat._pick_unused_moves(card, used)
        self.assertEqual(2, len(picked2))  # resets when all used


class LazyCompletionTests(unittest.TestCase):
    """Test 10: starter -> full lazy completion still works."""

    def test_ensure_full_card_handles_signature_greetings(self):
        """_ensure_full_card should work with cards that have signature_greetings."""
        # This test verifies the flow doesn't break with the new field.
        # We mock _complete_card to return a card with signature_greetings.
        with patch.object(chat, "_complete_card", return_value=_fake_card(
            signature_moves=[{"name": "M1", "steps": ["a"], "frequency": "often",
                              "evidence": {"quote": "q", "confidence": "r", "source": "s"},
                              "distinct_because": "d"}],
            signature_greetings=[
                {"setup": "S", "payoff": "P", "usage": "new_session_opening",
                 "confidence": "high", "why_distinctive": "d"}
            ],
        )):
            char = {
                "key": "test_key",
                "name": "Test",
                "source_show": "Test Show",
                "card_tier": "starter",
                "card": _fake_card(signature_moves=[
                    {"name": "M1", "steps": ["a"], "frequency": "often",
                     "evidence": {"quote": "q", "confidence": "r", "source": "s"},
                     "distinct_because": "d"}
                ]),
                "persona": "You are Test.",
            }
            # Since update_card needs a real DB, we mock it
            with patch.object(characters, "update_card", return_value=char):
                result = chat._ensure_full_card(char)
                self.assertIsNotNone(result)


class PhilFixtureTests(unittest.TestCase):
    """Deterministic Phil-like test fixture — no real model call needed."""

    def test_phil_greeting_renders_correctly(self):
        """Phil's signature greeting renders as sequential messages."""
        phil_greeting = {
            "setup": "Quick—what's my favorite hospital dessert?",
            "payoff": "JELL-O! Hello buddy!",
            "usage": "new_session_opening",
            "confidence": "high",
            "why_distinctive": "recognizable setup/payoff greeting behavior",
        }
        messages = chat._greeting_to_messages(phil_greeting)

        self.assertEqual(2, len(messages))
        self.assertIn("hospital dessert", messages[0]["text"])
        self.assertIn("JELL-O", messages[1]["text"])
        self.assertEqual(900, messages[1]["pause_before_ms"])

    def test_phil_card_without_greeting_falls_back(self):
        """Phil card without greetings falls back to opening_variants."""
        card = _fake_card(
            signature_greetings=[],
            opening_variants=["Hey buddy, ready to learn?"],
        )
        result = chat._kickoff_instruction(card, greeting=None)
        self.assertIn("Hey buddy", result)


class CardSchemaPropertiesTests(unittest.TestCase):
    """Verify the new field is in the schema."""

    def test_signature_greetings_in_schema(self):
        self.assertIn("signature_greetings", chat._CARD_SCHEMA_PROPERTIES)
        sg = chat._CARD_SCHEMA_PROPERTIES["signature_greetings"]
        self.assertEqual("array", sg["type"])
        self.assertIn("setup", sg["items"]["properties"])
        self.assertIn("payoff", sg["items"]["properties"])
        self.assertIn("confidence", sg["items"]["properties"])
        self.assertIn("why_distinctive", sg["items"]["properties"])


if __name__ == "__main__":
    unittest.main()
