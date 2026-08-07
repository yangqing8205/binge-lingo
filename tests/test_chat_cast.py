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


def _tool_response(items):
    call = SimpleNamespace(
        function=SimpleNamespace(
            name="report_cast",
            arguments=json.dumps({"characters": items}),
        )
    )
    message = SimpleNamespace(tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _persona_response():
    call = SimpleNamespace(
        function=SimpleNamespace(
            name="report_persona",
            arguments=json.dumps({
                "display_name": "Wilter White",
                "intro": "I am the one who conjugates.",
                "persona": "You are Wilter White, precise and intimidating.",
            }),
        )
    )
    message = SimpleNamespace(tool_calls=[call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class CastGenerationTests(unittest.TestCase):
    def test_requested_count_limits_prompt_tokens_and_results(self):
        names = [
            ("Walter White", "Wilter White"),
            ("Jesse Pinkman", "Jesse Pinkling"),
            ("Skyler White", "Skyler Whibe"),
            ("Hank Schrader", "Hank Schradar"),
            ("Saul Goodman", "Saul Goodmand"),
        ]
        items = [
            {
                "original_name": original_name,
                "display_name": display_name,
                "intro": f"Intro {index}",
                "persona": f"Persona {index}",
            }
            for index, (original_name, display_name) in enumerate(names)
        ]
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: _tool_response(items))
            )
        )

        with patch.object(chat, "_client", fake_client):
            result = chat.generate_cast_for_show("Breaking Bad", requested_count=3)

        self.assertEqual(3, len(result))

    def test_requested_count_is_sent_to_the_model(self):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return _tool_response([])

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

        with patch.object(chat, "_client", fake_client):
            chat.generate_cast_for_show("Breaking Bad", requested_count=3)

        self.assertEqual(1600, captured["max_tokens"])
        self.assertEqual(
            {"thinking": {"type": "disabled"}}, captured["extra_body"]
        )
        user_prompt = captured["messages"][-1]["content"]
        self.assertIn("Generate exactly 3 new characters", user_prompt)

    def test_persona_generation_disables_thinking(self):
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
        self.assertEqual(
            {"thinking": {"type": "disabled"}}, captured["extra_body"]
        )


class CastRouteTests(unittest.TestCase):
    def setUp(self):
        review.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = review.app.test_client()
        with self.client.session_transaction() as session:
            session["authed"] = True

    def test_route_uses_lightweight_single_persona_generation(self):
        existing = [
            {
                "key": "custom_1",
                "name": "Wilter White",
                "source_show": "Breaking Bad",
            },
            {
                "key": "custom_2",
                "name": "Jesse Pinkling",
                "source_show": "Breaking Bad",
            },
        ]
        persona = {
            "display_name": "Sowl Goodman",
            "intro": "Better call Sowl.",
            "persona": "You are Sowl Goodman, a fast-talking fixer.",
        }
        created = {
            "key": "custom_3",
            "name": "Sowl Goodman",
            "source_show": "Breaking Bad",
        }

        with (
            patch.object(review.characters, "list_characters", side_effect=[existing, existing]),
            patch.object(review.chat, "generate_cast_for_show", return_value=[]),
            patch.object(
                review.chat, "generate_persona_for_show", return_value=persona
            ) as generate,
            patch.object(review.characters, "add", return_value=created),
        ):
            response = self.client.post(
                "/api/characters/for-show", json={"show": "Breaking Bad"}
            )

        self.assertEqual(200, response.status_code)
        generate.assert_called_once_with("Breaking Bad")
        self.assertEqual([created], response.get_json()["created"])

    def test_timeout_returns_json_504(self):
        timeout = APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))

        with (
            patch.object(review.characters, "list_characters", return_value=[]),
            patch.object(review.chat, "generate_persona_for_show", side_effect=timeout),
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
