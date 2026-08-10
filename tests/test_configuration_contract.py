from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "API_BASE_URL": "https://example.invalid/api/v3",
            "API_KEY": "test-key",
            "API_MODEL": "test-model",
            "NOTION_TOKEN": "test-notion-token",
            "NOTION_DATABASE_ID": "test-database-id",
            "APP_PASSWORD": "test-password",
            "SECRET_KEY": "test-secret",
        }
    )
    return env


def _run_import(module: str, missing: str) -> subprocess.CompletedProcess[str]:
    env = _base_env()
    env.pop(missing, None)
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class ConfigurationContractTests(unittest.TestCase):
    def test_api_model_is_required(self):
        result = _run_import("src.config", "API_MODEL")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("API_MODEL", result.stderr)

    def test_app_password_is_required(self):
        result = _run_import("review", "APP_PASSWORD")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("APP_PASSWORD", result.stderr)


if __name__ == "__main__":
    unittest.main()
