import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError


os.environ.setdefault("API_BASE_URL", "https://example.invalid/api/v3")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("API_MODEL", "test-model")
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")
os.environ.setdefault("NOTION_DATABASE_ID", "test-database-id")
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret")

from src import chat  # noqa: E402
import review  # noqa: E402


def _tool_call_response(name, payload):
    call = SimpleNamespace(
        function=SimpleNamespace(name=name, arguments=json.dumps(payload))
    )
    message = SimpleNamespace(tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _fake_card(n=1, openings=1):
    return {
        "voice": {
            "pace": "fast", "sentence_length": "short", "vocabulary": "plain",
            "tone": "warm", "emotional_range": "wide",
            "evidence": {"quote": "q", "confidence": "reconstructed", "source": "s"},
        },
        "signature_moves": [
            {
                "name": f"Move {i}", "steps": ["a", "b"], "frequency": "often",
                "evidence": {"quote": "q", "confidence": "reconstructed", "source": "s"},
                "distinct_because": "specific reason",
            }
            for i in range(n)
        ],
        "format_style": {"caps": "rare", "bold": "rare", "ellipsis": "rare",
                          "exclaim": "rare", "notes": ""},
        "opening_variants": [f"Hey there {i}" for i in range(openings)],
        "relationship_style": {"address_terms": ["buddy"], "encouragement_style": "warm",
                                "teasing_style": "light"},
        "avoid": ["being generic"],
    }


def _persona_response(display_name="Wilter White"):
    return _tool_call_response("report_persona", {
        "display_name": display_name,
        "intro": "I am the one who conjugates.",
        "card": _fake_card(n=3, openings=2),
    })


class CastGenerationTests(unittest.TestCase):
    def test_select_cast_characters_dedupes_and_caps(self):
        items = [
            {"original_name": "Walter White", "display_name": "Wilter White", "intro": "i0"},
            {"original_name": "Jesse Pinkman", "display_name": "Jesse Pinkling", "intro": "i1"},
        ]
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **kwargs: _tool_call_response(
                    "report_cast_selection", {"characters": items}
                )
            ))
        )
        with patch.object(chat, "_client", fake_client):
            result = chat.select_cast_characters("Breaking Bad")
        self.assertEqual(2, len(result))
        self.assertEqual("Wilter White", result[0]["display_name"])

    def test_select_cast_characters_disables_thinking(self):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return _tool_call_response("report_cast_selection", {"characters": []})

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with patch.object(chat, "_client", fake_client):
            chat.select_cast_characters("Breaking Bad")
        self.assertEqual({"thinking": {"type": "disabled"}}, captured["extra_body"])

    def test_generate_cast_for_show_runs_starter_cards_in_parallel(self):
        selected = [
            {"original_name": "Walter White", "display_name": "Wilter White", "intro": "i0"},
            {"original_name": "Jesse Pinkman", "display_name": "Jesse Pinkling", "intro": "i1"},
            {"original_name": "Skyler White", "display_name": "Skyler Whibe", "intro": "i2"},
        ]

        def fake_generate_starter_card(show, original_name, display_name):
            return _fake_card(n=1, openings=1)

        with (
            patch.object(chat, "select_cast_characters", return_value=selected),
            patch.object(chat, "_generate_starter_card", side_effect=fake_generate_starter_card),
        ):
            result = chat.generate_cast_for_show("Breaking Bad")

        self.assertEqual(3, len(result))
        for item in result:
            self.assertEqual("starter", item["card_tier"])
            self.assertEqual(1, len(item["card"]["signature_moves"]))
            self.assertTrue(item["persona"])  # flattened prompt text is non-empty

    def test_generate_cast_for_show_drops_a_failed_character_without_sinking_batch(self):
        selected = [
            {"original_name": "Walter White", "display_name": "Wilter White", "intro": "i0"},
            {"original_name": "Jesse Pinkman", "display_name": "Jesse Pinkling", "intro": "i1"},
        ]

        def fake_generate_starter_card(show, original_name, display_name):
            if original_name == "Walter White":
                raise RuntimeError("upstream blew up")
            return _fake_card(n=1, openings=1)

        with (
            patch.object(chat, "select_cast_characters", return_value=selected),
            patch.object(chat, "_generate_starter_card", side_effect=fake_generate_starter_card),
        ):
            result = chat.generate_cast_for_show("Breaking Bad")

        self.assertEqual(1, len(result))
        self.assertEqual("Jesse Pinkling", result[0]["display_name"])

    def test_generate_cast_for_show_returns_empty_when_nothing_selected(self):
        with patch.object(chat, "select_cast_characters", return_value=[]):
            result = chat.generate_cast_for_show("Breaking Bad")
        self.assertEqual([], result)

    def test_persona_generation_disables_thinking_and_flattens_card(self):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return _persona_response()

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with patch.object(chat, "_client", fake_client):
            result = chat.generate_persona("Breaking Bad", "Walter White")

        self.assertEqual("Wilter White", result["display_name"])
        self.assertEqual({"thinking": {"type": "disabled"}}, captured["extra_body"])
        self.assertIn("card", result)
        self.assertTrue(result["persona"])  # flatten_card produced prompt text


class CastRouteTests(unittest.TestCase):
    def setUp(self):
        review.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = review.app.test_client()
        with self.client.session_transaction() as session:
            session["authed"] = True

    def test_route_uses_parallel_cast_generation(self):
        existing = [
            {"key": "custom_1", "name": "Wilter White", "source_show": "Breaking Bad"},
        ]
        personas = [
            {"display_name": "Jesse Pinkling", "intro": "Yo.", "card": _fake_card(),
             "persona": "You are Jesse Pinkling.", "card_tier": "starter"},
        ]
        created = {"key": "custom_2", "name": "Jesse Pinkling", "source_show": "Breaking Bad"}

        with (
            patch.object(review.characters, "list_characters", side_effect=[existing, existing]),
            patch.object(
                review.chat, "generate_cast_for_show", return_value=personas
            ) as generate,
            patch.object(review.characters, "add", return_value=created),
        ):
            response = self.client.post(
                "/api/characters/for-show", json={"show": "Breaking Bad"}
            )

        self.assertEqual(200, response.status_code)
        generate.assert_called_once_with("Breaking Bad", ["Wilter White"], [])
        self.assertEqual([created], response.get_json()["created"])

    def test_timeout_returns_json_504(self):
        timeout = APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))

        with (
            patch.object(review.characters, "list_characters", return_value=[]),
            patch.object(review.chat, "generate_cast_for_show", side_effect=timeout),
        ):
            response = self.client.post(
                "/api/characters/for-show", json={"show": "Breaking Bad"}
            )

        self.assertEqual(504, response.status_code)
        self.assertEqual(
            {"ok": False, "error": "角色生成超时，请稍后重试。"},
            response.get_json(),
        )


class SecurityCleanupTests(unittest.TestCase):
    def setUp(self):
        review.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = review.app.test_client()
        with self.client.session_transaction() as session:
            session["authed"] = True

    def test_ark_key_debug_endpoint_is_removed(self):
        response = self.client.get("/api/debug/ark-key")
        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
