"""Scene Talk upgrade tests.

Covers:
- Built-in cast completeness (12 characters, all have world_memory + opening_scenes)
- Stella output format enforcement
- First-round no-teaching-language rule
- Opening scene selection
- sync_builtin_characters mechanism
- Backward compatibility (old cards still work)
"""
from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("API_BASE_URL", "https://example.invalid/api/v3")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("API_MODEL", "test-model")
os.environ.setdefault("NOTION_TOKEN", "test-notion-token")
os.environ.setdefault("NOTION_DATABASE_ID", "test-database-id")
os.environ.setdefault("APP_PASSWORD", "test-password")
os.environ.setdefault("SECRET_KEY", "test-secret")

from src import characters
from src import chat


# ── Built-in cast completeness ───────────────────────────────────────────────

EXPECTED_BUILTINS = {
    "fil", "clair", "grumpa", "gloria", "cam", "mitch",
    "halo", "alex", "lukini", "manuscipt", "lily", "stella",
}


class BuiltinCastCompleteTests(unittest.TestCase):
    """All 12 Modern Family built-ins exist and have complete cards."""

    def test_all_twelve_builtins_present(self):
        """Exactly 12 built-in characters in the canonical list."""
        from src.characters import _BUILTINS, _BUILTIN_CARDS
        builtin_keys = {b[0] for b in _BUILTINS}
        self.assertEqual(EXPECTED_BUILTINS, builtin_keys)
        self.assertEqual(12, len(_BUILTINS))
        self.assertEqual(12, len(_BUILTIN_CARDS))

    def test_each_builtin_has_full_card(self):
        """Every built-in has a non-None card with all new fields."""
        from src.characters import _BUILTIN_CARDS

        required_fields = [
            "voice", "signature_moves", "format_style",
            "opening_variants", "signature_greetings",
            "world_memory", "signature_situations", "opening_scenes",
            "relationship_style", "avoid",
        ]

        for key, card in _BUILTIN_CARDS.items():
            for field in required_fields:
                self.assertIn(field, card, f"{key} missing {field}")

    def test_world_memory_has_concrete_facts(self):
        """world_memory entries are concrete facts, not personality traits."""
        from src.characters import _BUILTIN_CARDS

        trait_words = ["friendly", "goofy", "optimistic", "sarcastic", "warm",
                       "shy", "smart", "kind", "funny", "awkward"]

        for key, card in _BUILTIN_CARDS.items():
            wm = card.get("world_memory", [])
            self.assertGreaterEqual(len(wm), 5, f"{key} too few world_memory entries")
            # At least half should NOT contain generic trait words
            non_trait = [f for f in wm if not any(t in f.lower() for t in trait_words)]
            self.assertGreaterEqual(
                len(non_trait), len(wm) // 2,
                f"{key}: too many world_memory entries sound like personality traits"
            )

    def test_signature_situations_exist(self):
        """Every character has 3+ signature_situations."""
        from src.characters import _BUILTIN_CARDS
        for key, card in _BUILTIN_CARDS.items():
            ss = card.get("signature_situations", [])
            self.assertGreaterEqual(len(ss), 3, f"{key} too few signature_situations")

    def test_opening_scenes_have_correct_structure(self):
        """Every character has opening_scenes with situation/setup/possible_targets."""
        from src.characters import _BUILTIN_CARDS

        for key, card in _BUILTIN_CARDS.items():
            scenes = card.get("opening_scenes", [])
            self.assertGreaterEqual(len(scenes), 2, f"{key} too few opening_scenes")
            for sc in scenes:
                self.assertIn("situation", sc, f"{key} scene missing situation")
                self.assertIn("setup", sc, f"{key} scene missing setup")
                self.assertIn("possible_targets", sc, f"{key} scene missing possible_targets")
                self.assertIsInstance(sc["possible_targets"], list)
                self.assertTrue(sc["situation"].strip())
                self.assertTrue(sc["setup"].strip())

    def test_opening_scenes_have_no_teaching_language(self):
        """Scene setups don't contain English/practice/lesson words."""
        from src.characters import _BUILTIN_CARDS
        banned = ["english", "practice", "lesson", "learn", "expression",
                  "target", "vocabulary", "study"]

        for key, card in _BUILTIN_CARDS.items():
            for sc in card.get("opening_scenes", []):
                setup_lower = sc["setup"].lower()
                for word in banned:
                    self.assertNotIn(
                        word, setup_lower,
                        f"{key} scene setup contains banned word '{word}': {sc['setup'][:50]}"
                    )

    def test_alex_and_lily_are_new(self):
        """Alex and Lily exist as new built-ins with proper data."""
        from src.characters import _BUILTIN_CARDS

        self.assertIn("alex", _BUILTIN_CARDS)
        self.assertIn("lily", _BUILTIN_CARDS)

        # Alex should have science/academic stuff
        alex_wm = " ".join(_BUILTIN_CARDS["alex"]["world_memory"]).lower()
        self.assertTrue(any(w in alex_wm for w in ["science", "academic", "competition", "smart"]))

        # Lily should have deadpan/dad drama stuff
        lily_wm = " ".join(_BUILTIN_CARDS["lily"]["world_memory"]).lower()
        self.assertTrue(any(w in lily_wm for w in ["deadpan", "food", "snack", "drama"]))

    def test_stella_has_minimal_moves(self):
        """Stella has fewer signature_moves (she's a dog)."""
        from src.characters import _BUILTIN_CARDS
        stella_moves = len(_BUILTIN_CARDS["stella"]["signature_moves"])
        self.assertLessEqual(stella_moves, 3)


# ── Stella output format ─────────────────────────────────────────────────────

class StellaFormatTests(unittest.TestCase):
    """Stella output is always wrapped in Woof. + Translation format."""

    def test_wrap_stella_normal_text(self):
        """Normal text gets wrapped into Woof. + Translation."""
        messages = [{"text": "I think there's a squirrel outside."}]
        result = chat._wrap_stella_output(messages)
        self.assertEqual(1, len(result))
        text = result[0]["text"]
        self.assertTrue(text.startswith("Woof."))
        self.assertIn("Translation:", text)
        self.assertIn("squirrel", text)

    def test_wrap_stella_already_correct(self):
        """Already-formatted output is left alone."""
        original = [{"text": "Woof.\n(Translation: Hi.)"}]
        result = chat._wrap_stella_output(original)
        self.assertEqual(1, len(result))
        self.assertEqual(original[0]["text"], result[0]["text"])

    def test_wrap_stella_empty(self):
        """Empty messages list returns empty."""
        result = chat._wrap_stella_output([])
        self.assertEqual(0, len(result))

    def test_wrap_stella_multiple_messages(self):
        """Multiple messages get joined and wrapped."""
        messages = [{"text": "First part."}, {"text": "Second part."}]
        result = chat._wrap_stella_output(messages)
        self.assertEqual(1, len(result))
        text = result[0]["text"]
        self.assertIn("First part", text)
        self.assertIn("Second part", text)
        self.assertTrue(text.startswith("Woof."))

    def test_stella_never_says_i_think_directly(self):
        """Stella's first line is always 'Woof.' — never 'I think...'"""
        test_inputs = [
            [{"text": "I think it's time for a walk."}],
            [{"text": "I believe you dropped something."}],
            [{"text": "I wonder if there are treats."}],
        ]
        for msgs in test_inputs:
            result = chat._wrap_stella_output(msgs)
            first_line = result[0]["text"].split("\n")[0]
            self.assertEqual("Woof.", first_line, f"First line should be Woof., got: {first_line}")


# ── Kickoff no-teaching-language rule ────────────────────────────────────────

class KickoffNoTeachingLanguageTests(unittest.TestCase):
    """First round kickoff instructions ban teaching vocabulary."""

    def setUp(self):
        self.banned = ["english", "practice", "lesson", "learn",
                       "expression", "target", "vocabulary", "study"]

    def test_kickoff_without_greeting_mentions_ban(self):
        """Kickoff without greeting tells model not to use teaching words."""
        card = {"opening_variants": ["Hey there!"]}
        kickoff = chat._kickoff_instruction(card, None)
        kickoff_lower = kickoff.lower()
        # The instruction itself mentions the words (to ban them)
        # The key is: the instruction EXISTS
        self.assertIn("first round rule", kickoff_lower)
        # Verify all banned words are listed in the rule
        for word in ["english", "practice", "lesson"]:
            self.assertIn(word, kickoff_lower)

    def test_kickoff_with_greeting_mentions_ban(self):
        """Kickoff with greeting also has the no-teaching rule."""
        greeting = {"setup": "Hey", "payoff": "Hi", "_idx": 0}
        kickoff = chat._kickoff_instruction({}, greeting)
        kickoff_lower = kickoff.lower()
        self.assertIn("first round rule", kickoff_lower)

    def test_kickoff_with_scene_mentions_ban(self):
        """Kickoff with scene has the no-teaching rule."""
        scene = {"situation": "in the kitchen", "setup": "Oh hey, you're just in time!"}
        kickoff = chat._kickoff_instruction({}, None, scene)
        kickoff_lower = kickoff.lower()
        # The ban rule is present (lists forbidden words)
        self.assertIn("do not say", kickoff_lower)
        self.assertIn("english", kickoff_lower)
        self.assertIn("practice", kickoff_lower)
        self.assertIn("in the kitchen", kickoff_lower)

    def test_kickoff_scene_includes_setup(self):
        """Scene setup text is passed through to the kickoff."""
        scene = {"situation": "test situation", "setup": "test opening line here"}
        kickoff = chat._kickoff_instruction({}, None, scene)
        self.assertIn("test opening line here", kickoff)
        self.assertIn("test situation", kickoff)


# ── Opening scene selection ──────────────────────────────────────────────────

class OpeningSceneSelectionTests(unittest.TestCase):
    """_pick_opening_scene selects scenes from card data."""

    def test_picks_scene_when_available(self):
        """Returns a scene dict when card has opening_scenes."""
        card = {
            "opening_scenes": [
                {"situation": "s1", "setup": "hi 1", "possible_targets": []},
                {"situation": "s2", "setup": "hi 2", "possible_targets": []},
            ]
        }
        result = chat._pick_opening_scene(card)
        self.assertIsNotNone(result)
        self.assertIn("situation", result)

    def test_returns_none_when_no_scenes(self):
        """Returns None when card has no opening_scenes."""
        result = chat._pick_opening_scene({"opening_scenes": []})
        self.assertIsNone(result)

    def test_returns_none_when_no_card(self):
        """Returns None when card is None."""
        result = chat._pick_opening_scene(None)
        self.assertIsNone(result)

    def test_returns_none_when_missing_key(self):
        """Returns None when card lacks opening_scenes key."""
        result = chat._pick_opening_scene({})
        self.assertIsNone(result)


# ── Sync built-in characters ─────────────────────────────────────────────────

class SyncBuiltinCharactersTests(unittest.TestCase):
    """sync_builtin_characters updates built-ins when version changes."""

    def setUp(self):
        """Use a temp DB for each test."""
        import sqlite3
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

        # Monkey-patch DB_PATH
        self.original_path = characters.DB_PATH
        characters.DB_PATH = self.db_path

        # Also patch settings module if it exists — or create app_settings table
        # The sync function uses app_settings table
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                source_show TEXT NOT NULL DEFAULT '',
                intro TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#4a4a4a',
                persona_prompt TEXT NOT NULL,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                hidden INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                card_json TEXT,
                card_tier TEXT NOT NULL DEFAULT 'legacy'
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def tearDown(self):
        characters.DB_PATH = self.original_path
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_creates_all_builtins(self):
        """On fresh DB, sync creates all 12 built-in characters."""
        from src.characters import sync_builtin_characters
        sync_builtin_characters(self.conn)
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT key FROM characters WHERE is_builtin = 1"
        ).fetchall()
        keys = {r["key"] for r in rows}
        self.assertEqual(12, len(keys))
        self.assertEqual(EXPECTED_BUILTINS, keys)

    def test_sync_sets_full_tier_with_card_json(self):
        """All synced built-ins have card_tier = 'full' and non-null card_json."""
        from src.characters import sync_builtin_characters
        sync_builtin_characters(self.conn)
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT key, card_tier, card_json FROM characters WHERE is_builtin = 1"
        ).fetchall()
        for row in rows:
            self.assertEqual("full", row["card_tier"], f"{row['key']} not full tier")
            self.assertIsNotNone(row["card_json"], f"{row['key']} has no card_json")
            import json
            card = json.loads(row["card_json"])
            self.assertIn("world_memory", card)
            self.assertIn("opening_scenes", card)

    def test_sync_is_idempotent(self):
        """Running sync twice doesn't duplicate or break anything."""
        from src.characters import sync_builtin_characters
        sync_builtin_characters(self.conn)
        self.conn.commit()
        count1 = self.conn.execute(
            "SELECT COUNT(*) as c FROM characters WHERE is_builtin = 1"
        ).fetchone()["c"]

        sync_builtin_characters(self.conn)
        self.conn.commit()
        count2 = self.conn.execute(
            "SELECT COUNT(*) as c FROM characters WHERE is_builtin = 1"
        ).fetchone()["c"]

        self.assertEqual(count1, count2)

    def test_sync_preserves_custom_characters(self):
        """Custom (non-builtin) characters are never touched."""
        from src.characters import sync_builtin_characters
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO characters (key, display_name, source_show, intro, "
            "color, persona_prompt, is_builtin, hidden, created_at) "
            "VALUES ('custom1', 'Custom Guy', 'Custom Show', 'hi', '#fff', "
            "'you are custom', 0, 0, ?)",
            (now,),
        )
        self.conn.commit()

        sync_builtin_characters(self.conn)
        self.conn.commit()

        custom = self.conn.execute(
            "SELECT * FROM characters WHERE key = 'custom1'"
        ).fetchone()
        self.assertIsNotNone(custom)
        self.assertEqual(0, custom["is_builtin"])
        self.assertEqual("Custom Guy", custom["display_name"])

    def test_sync_updates_when_version_changes(self):
        """When builtin_card_version is lower, sync updates existing built-ins."""
        from src.characters import sync_builtin_characters

        # First sync
        sync_builtin_characters(self.conn)
        self.conn.commit()

        # Manually change a built-in's display_name
        self.conn.execute(
            "UPDATE characters SET display_name = 'OLD NAME' WHERE key = 'fil'"
        )
        # Downgrade version to trigger re-sync
        self.conn.execute(
            "UPDATE app_settings SET value = '0' WHERE key = 'builtin_card_version'"
        )
        self.conn.commit()

        # Verify it was changed
        old = self.conn.execute(
            "SELECT display_name FROM characters WHERE key = 'fil'"
        ).fetchone()["display_name"]
        self.assertEqual("OLD NAME", old)

        # Run sync again
        sync_builtin_characters(self.conn)
        self.conn.commit()

        # Should be restored to correct name
        updated = self.conn.execute(
            "SELECT display_name FROM characters WHERE key = 'fil'"
        ).fetchone()["display_name"]
        self.assertNotEqual("OLD NAME", updated)
        self.assertIn("Fil", updated)


# ── flatten_card new fields ──────────────────────────────────────────────────

class FlattenCardNewFieldsTests(unittest.TestCase):
    """flatten_card renders world_memory, signature_situations, opening_scenes."""

    def test_flatten_includes_world_memory(self):
        card = {"world_memory": ["fact one", "fact two"]}
        flat = characters.flatten_card("Test", card)
        flat_lower = flat.lower()
        self.assertIn("world", flat_lower)
        self.assertIn("fact one", flat_lower)
        self.assertIn("fact two", flat_lower)

    def test_flatten_includes_signature_situations(self):
        card = {"signature_situations": ["doing a thing", "at a place"]}
        flat = characters.flatten_card("Test", card)
        flat_lower = flat.lower()
        self.assertIn("situations", flat_lower)
        self.assertIn("doing a thing", flat_lower)

    def test_flatten_includes_opening_scenes(self):
        card = {
            "opening_scenes": [
                {"situation": "test situation",
                 "setup": "test opening setup line",
                 "possible_targets": ["foo"]},
            ]
        }
        flat = characters.flatten_card("Test", card)
        flat_lower = flat.lower()
        self.assertIn("scene", flat_lower)
        self.assertIn("test situation", flat_lower)

    def test_flatten_empty_new_fields(self):
        """Empty or missing new fields don't crash flatten_card."""
        # Card with empty lists
        card = {"world_memory": [], "signature_situations": [], "opening_scenes": []}
        result = characters.flatten_card("Test", card)
        self.assertIsInstance(result, str)

        # Card without any of the new keys
        result2 = characters.flatten_card("Test", {})
        self.assertIsInstance(result2, str)


if __name__ == "__main__":
    unittest.main()
