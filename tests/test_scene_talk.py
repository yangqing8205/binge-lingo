"""Scene Talk upgrade tests.

Covers:
- Built-in cast completeness (12 characters, all have world_memory + scene_anchors)
- Stella output format enforcement
- First-round no-teaching-language rule
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
        """Every built-in has a non-None card with all expected fields."""
        from src.characters import _BUILTIN_CARDS

        required_fields = [
            "voice", "signature_moves", "format_style",
            "opening_variants", "world_memory", "scene_anchors",
            "relationship_style", "avoid",
        ]

        for key, card in _BUILTIN_CARDS.items():
            for field in required_fields:
                self.assertIn(field, card, f"{key} missing {field}")

    def test_no_removed_fields_in_builtin_cards(self):
        """Removed fields (signature_greetings, opening_scenes) are not present."""
        from src.characters import _BUILTIN_CARDS

        removed_fields = [
            "signature_greetings", "opening_scenes",
        ]

        for key, card in _BUILTIN_CARDS.items():
            for field in removed_fields:
                self.assertNotIn(field, card, f"{key} still has removed field {field}")

    def test_voice_has_no_evidence(self):
        """voice dict no longer has evidence field."""
        from src.characters import _BUILTIN_CARDS
        for key, card in _BUILTIN_CARDS.items():
            self.assertNotIn("evidence", card["voice"], f"{key} voice still has evidence")

    def test_signature_moves_have_no_evidence_or_distinct_because(self):
        """signature_moves entries no longer have evidence or distinct_because."""
        from src.characters import _BUILTIN_CARDS
        for key, card in _BUILTIN_CARDS.items():
            for move in card["signature_moves"]:
                self.assertNotIn("evidence", move, f"{key} move has evidence")
                self.assertNotIn("distinct_because", move, f"{key} move has distinct_because")
                self.assertIn("name", move)
                self.assertIn("steps", move)
                self.assertIn("frequency", move)

    def test_world_memory_has_concrete_facts(self):
        """world_memory entries are concrete facts, not personality traits."""
        from src.characters import _BUILTIN_CARDS

        trait_words = ["friendly", "goofy", "optimistic", "sarcastic", "warm",
                       "shy", "smart", "kind", "funny", "awkward"]

        for key, card in _BUILTIN_CARDS.items():
            wm = card.get("world_memory", [])
            self.assertGreaterEqual(len(wm), 5, f"{key} too few world_memory entries")
            non_trait = [f for f in wm if not any(t in f.lower() for t in trait_words)]
            self.assertGreaterEqual(
                len(non_trait), len(wm) // 2,
                f"{key}: too many world_memory entries sound like personality traits"
            )

    def test_scene_anchors_exist(self):
        """Every character has 3+ scene_anchors (renamed from signature_situations)."""
        from src.characters import _BUILTIN_CARDS
        for key, card in _BUILTIN_CARDS.items():
            sa = card.get("scene_anchors", [])
            self.assertGreaterEqual(len(sa), 3, f"{key} too few scene_anchors")

    def test_opening_variants_have_no_teaching_language(self):
        """Opening variants don't contain explicit teaching language."""
        from src.characters import _BUILTIN_CARDS
        # Check for clearly teaching-oriented phrases, not every use of common words
        # (e.g. "I've learned" is fine in normal dialogue; "let's learn English" is not).
        banned_phrases = [
            "english", "vocabulary", "target expression",
            "let's practice", "want to practice", "practice your",
            "let's learn", "learn english", "study english",
            "today's lesson", "new lesson", "teaching",
        ]

        for key, card in _BUILTIN_CARDS.items():
            for ov in card.get("opening_variants", []):
                ov_lower = ov.lower()
                for phrase in banned_phrases:
                    self.assertNotIn(
                        phrase, ov_lower,
                        f"{key} opening_variant contains teaching phrase '{phrase}': {ov[:60]}"
                    )

    def test_alex_and_lily_are_new(self):
        """Alex and Lily exist as built-ins with proper data."""
        from src.characters import _BUILTIN_CARDS

        self.assertIn("alex", _BUILTIN_CARDS)
        self.assertIn("lily", _BUILTIN_CARDS)

        alex_wm = " ".join(_BUILTIN_CARDS["alex"]["world_memory"]).lower()
        self.assertTrue(any(w in alex_wm for w in ["science", "academic", "competition", "caltech"]))

        lily_wm = " ".join(_BUILTIN_CARDS["lily"]["world_memory"]).lower()
        self.assertTrue(any(w in lily_wm for w in ["deadpan", "cam", "mitchell", "dads"]))

    def test_stella_has_minimal_moves(self):
        """Stella has fewer signature_moves (she's a dog)."""
        from src.characters import _BUILTIN_CARDS
        stella_moves = len(_BUILTIN_CARDS["stella"]["signature_moves"])
        self.assertLessEqual(stella_moves, 3)

    def test_builtin_display_names_match_document(self):
        """Built-in display_names and intros match the reference document."""
        from src.characters import _BUILTINS

        expected = {
            "fil": ("Fil Funphy", "Jello! I've got a Fil-osophy for almost everything."),
            "clair": ("Clair-ification", "I have a plan. Naturally, nobody is following it."),
            "grumpa": ("Grumpa", "I built closets for forty years. I know when something doesn't fit."),
            "gloria": ("Gloria-ous", "If you're going to tell a story, tell it with feeling."),
            "cam": ("Cam the Ham", "Every ordinary story deserves proper lighting."),
            "mitch": ("Mitch-match", "I'm not overthinking it. I'm considering every reasonable disaster."),
            "halo": ("Hail-ley", "I know what people say. More importantly, I know what they mean."),
            "alex": ("Alex-plain", "I checked the data. Then I checked the data checking the data."),
            "lukini": ("The Great Lukini", "I have a theory. I also have tape."),
            "manuscipt": ("Manimal", "Poetry before breakfast is not excessive. It is civilized."),
            "lily": ("Lil-logical", "I'll wait until the adults finish making this complicated."),
            "stella": ("Stella-r", "Woof."),
        }

        builtin_dict = {b[0]: (b[1], b[2]) for b in _BUILTINS}
        for key, (exp_name, exp_intro) in expected.items():
            self.assertEqual(exp_name, builtin_dict[key][0], f"{key} display_name mismatch")
            self.assertEqual(exp_intro, builtin_dict[key][1], f"{key} intro mismatch")


# ── Stella output format ─────────────────────────────────────────────────────

class StellaFormatTests(unittest.TestCase):
    """Stella output is always wrapped in Woof. + Translation format."""

    def test_wrap_stella_normal_text(self):
        """Normal text gets wrapped into Woof. + Translation."""
        messages = [{"text": "I think there's a squirrel outside."}]
        result = chat._wrap_stella(messages)
        self.assertEqual(1, len(result))
        text = result[0]["text"]
        self.assertTrue(text.startswith("Woof."))
        self.assertIn("Translation:", text)
        self.assertIn("squirrel", text)

    def test_wrap_stella_strips_accidental_woof(self):
        """If model accidentally generated 'Woof.' already, it gets stripped and re-wrapped."""
        messages = [{"text": "Woof. I'm hungry."}]
        result = chat._wrap_stella(messages)
        text = result[0]["text"]
        self.assertTrue(text.startswith("Woof."))
        self.assertNotIn("Woof. Woof.", text)
        self.assertIn("hungry", text)

    def test_wrap_stella_strips_accidental_translation_wrapper(self):
        """If model generated '(Translation: ...)' already, it gets stripped and re-wrapped."""
        messages = [{"text": "(Translation: Jay is home.)"}]
        result = chat._wrap_stella(messages)
        text = result[0]["text"]
        self.assertEqual(text.count("Translation:"), 1)
        self.assertIn("Jay is home", text)

    def test_wrap_stella_empty(self):
        """Empty messages list returns a default translation."""
        result = chat._wrap_stella([])
        self.assertEqual(1, len(result))
        self.assertTrue(result[0]["text"].startswith("Woof."))

    def test_wrap_stella_multiple_messages(self):
        """Multiple messages get joined and wrapped."""
        messages = [{"text": "First part."}, {"text": "Second part."}]
        result = chat._wrap_stella(messages)
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
            result = chat._wrap_stella(msgs)
            first_line = result[0]["text"].split("\n")[0]
            self.assertEqual("Woof.", first_line, f"First line should be Woof., got: {first_line}")


# ── Kickoff no-teaching-language rule ────────────────────────────────────────

class KickoffNoTeachingLanguageTests(unittest.TestCase):
    """First round kickoff instructions ban teaching vocabulary."""

    def setUp(self):
        self.banned = ["english", "practice", "lesson", "learn",
                       "expression", "target", "vocabulary", "study"]

    def test_kickoff_has_first_turn_rule(self):
        """Kickoff has FIRST-TURN RULE banning teaching words."""
        card = {"opening_variants": ["Hey there!"], "world_memory": ["fact one"]}
        kickoff = chat._kickoff_instruction(card, None)
        kickoff_lower = kickoff.lower()
        self.assertIn("first-turn rule", kickoff_lower)
        for word in ["english", "practice", "lesson"]:
            self.assertIn(word, kickoff_lower)

    def test_kickoff_includes_world_memory(self):
        """Kickoff includes world_memory items as 'Possible pieces of your world'."""
        card = {
            "opening_variants": ["Hey there!"],
            "world_memory": ["fact about job", "fact about family"],
        }
        kickoff = chat._kickoff_instruction(card, None)
        self.assertIn("Possible pieces of your world", kickoff)
        self.assertIn("fact about job", kickoff)
        self.assertIn("fact about family", kickoff)

    def test_kickoff_includes_opening_variants_as_inspiration(self):
        """Opening variants are presented as inspiration, not as script."""
        card = {
            "opening_variants": ["Sample opening line here"],
            "world_memory": [],
        }
        kickoff = chat._kickoff_instruction(card, None)
        self.assertIn("inspiration", kickoff.lower())
        self.assertIn("Sample opening line here", kickoff)
        self.assertIn("not as a script to repeat verbatim", kickoff)

    def test_kickoff_without_card(self):
        """Kickoff works with None card."""
        kickoff = chat._kickoff_instruction(None, None)
        self.assertIn("FIRST-TURN RULE", kickoff)
        self.assertIn("Begin as if the learner", kickoff)

    def test_kickoff_no_greeting_param_used(self):
        """The old greeting parameter is accepted but no longer drives logic."""
        card = {"opening_variants": ["hi"], "world_memory": []}
        kickoff1 = chat._kickoff_instruction(card, None)
        kickoff2 = chat._kickoff_instruction(card, greeting=None)
        self.assertEqual(kickoff1, kickoff2)


# ── Sync built-in characters ─────────────────────────────────────────────────

class SyncBuiltinCharactersTests(unittest.TestCase):
    """sync_builtin_characters updates built-ins when version changes."""

    def setUp(self):
        """Use a temp DB for each test."""
        import sqlite3
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")

        self.original_path = characters.DB_PATH
        characters.DB_PATH = self.db_path

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
            self.assertIn("scene_anchors", card)

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

        sync_builtin_characters(self.conn)
        self.conn.commit()

        self.conn.execute(
            "UPDATE characters SET display_name = 'OLD NAME' WHERE key = 'fil'"
        )
        self.conn.execute(
            "UPDATE app_settings SET value = '0' WHERE key = 'builtin_card_version'"
        )
        self.conn.commit()

        old = self.conn.execute(
            "SELECT display_name FROM characters WHERE key = 'fil'"
        ).fetchone()["display_name"]
        self.assertEqual("OLD NAME", old)

        sync_builtin_characters(self.conn)
        self.conn.commit()

        updated = self.conn.execute(
            "SELECT display_name FROM characters WHERE key = 'fil'"
        ).fetchone()["display_name"]
        self.assertNotEqual("OLD NAME", updated)
        self.assertIn("Fil", updated)


# ── flatten_card new fields ──────────────────────────────────────────────────

class FlattenCardNewFieldsTests(unittest.TestCase):
    """flatten_card renders world_memory and scene_anchors."""

    def test_flatten_includes_world_memory(self):
        card = {"world_memory": ["fact one", "fact two"]}
        flat = characters.flatten_card("Test", card)
        flat_lower = flat.lower()
        self.assertIn("world", flat_lower)
        self.assertIn("fact one", flat_lower)
        self.assertIn("fact two", flat_lower)

    def test_flatten_includes_scene_anchors(self):
        card = {"scene_anchors": ["doing a thing", "at a place"]}
        flat = characters.flatten_card("Test", card)
        flat_lower = flat.lower()
        self.assertIn("scene", flat_lower)
        self.assertIn("doing a thing", flat_lower)

    def test_flatten_empty_new_fields(self):
        """Empty or missing new fields don't crash flatten_card."""
        card = {"world_memory": [], "scene_anchors": []}
        result = characters.flatten_card("Test", card)
        self.assertIsInstance(result, str)

        result2 = characters.flatten_card("Test", {})
        self.assertIsInstance(result2, str)

    def test_flatten_has_no_signature_greetings(self):
        """flatten_card no longer mentions signature greetings."""
        card = {"opening_variants": ["hi"]}
        flat = characters.flatten_card("Test", card)
        self.assertNotIn("Signature greetings", flat)
        self.assertNotIn("signature_greetings", flat)

    def test_flatten_has_no_opening_scenes(self):
        """flatten_card no longer mentions opening scenes."""
        card = {"opening_variants": ["hi"]}
        flat = characters.flatten_card("Test", card)
        self.assertNotIn("opening_scenes", flat)
        self.assertNotIn("Opening scene", flat)


if __name__ == "__main__":
    unittest.main()
