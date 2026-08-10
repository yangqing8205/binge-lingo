from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class RepositoryAccuracyTests(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_gunicorn_uses_one_worker_and_120_second_timeout(self):
        for path in ("render.yaml", "Procfile"):
            text = self.read(path)
            self.assertIn("--workers 1", text, path)
            self.assertIn("--timeout 120", text, path)
            self.assertNotIn("--workers 2", text, path)


if __name__ == "__main__":
    unittest.main()
