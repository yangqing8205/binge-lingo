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

    def test_env_example_matches_openai_compatible_ark_setup(self):
        text = self.read(".env.example")
        self.assertIn("https://ark.cn-beijing.volces.com/api/v3", text)
        self.assertIn("API_MODEL=your-model-or-endpoint-id", text)
        self.assertIn("APP_PASSWORD=choose-a-strong-shared-password", text)
        self.assertIn("SECRET_KEY=replace-with-a-long-random-value", text)
        self.assertNotIn("api.anthropic.com", text)
        self.assertNotIn("claude-sonnet", text)
        self.assertNotIn("Anthropic-native", text)

    def test_roadmap_does_not_claim_completed_features_are_future_work(self):
        text = self.read("TODO.md")
        self.assertNotIn("model.zhenguanyu.com", text)
        self.assertNotIn("sk-mg", text)
        self.assertNotIn("AI 对话、游戏化（明确留到更后面）", text)
        self.assertIn("间隔重复调度", text)
        self.assertIn("持久化存储", text)

    def test_repository_contains_real_mit_license(self):
        text = self.read("LICENSE")
        self.assertIn("MIT License", text)
        self.assertIn("Copyright (c) 2026 Yang Qing", text)
        self.assertIn("Permission is hereby granted", text)


if __name__ == "__main__":
    unittest.main()
