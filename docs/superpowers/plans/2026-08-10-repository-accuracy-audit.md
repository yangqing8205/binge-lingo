# BingeLingo Repository Accuracy Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BingeLingo's public documentation, example configuration, authentication defaults, and Render process configuration accurately reflect the current OpenAI-compatible learning workflow.

**Architecture:** Preserve the existing application design and fix only verified inconsistencies. Configuration failures become explicit, Render uses one worker to match in-memory chat sessions, and repository-level tests enforce that public documentation cannot silently drift back to the obsolete Claude/Anthropic architecture.

**Tech Stack:** Python 3.11, Flask, OpenAI Python SDK, unittest, Node.js test runner, GitHub CLI, Render/Gunicorn

---

### Task 1: Establish the Executable Baseline

**Files:**
- No tracked files modified.

- [x] **Step 1: Create and populate a local virtual environment**

Run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Expected: all dependencies, including Flask and the OpenAI SDK, install successfully inside `.venv`.

- [x] **Step 2: Run the current Python tests**

Run:

```bash
API_BASE_URL=https://example.invalid/api/v3 \
API_KEY=test-key \
API_MODEL=test-model \
NOTION_TOKEN=test-notion-token \
NOTION_DATABASE_ID=test-database-id \
APP_PASSWORD=test-password \
SECRET_KEY=test-secret \
.venv/bin/python -m unittest discover -v
```

Expected: the existing Python tests pass before tracked implementation changes begin.

- [x] **Step 3: Run the current JavaScript tests**

Run:

```bash
node --test tests/api-response.test.js
```

Expected: 4 tests pass and 0 fail.

---

### Task 2: Require Explicit Model and Password Configuration

**Files:**
- Create: `tests/test_configuration_contract.py`
- Modify: `src/config.py`
- Modify: `review.py`

- [x] **Step 1: Add failing configuration-contract tests**

Create `tests/test_configuration_contract.py` with:

```python
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
```

- [x] **Step 2: Run the new tests and confirm the old fallbacks fail the contract**

Run:

```bash
.venv/bin/python -m unittest tests.test_configuration_contract -v
```

Expected: both tests fail because `API_MODEL` and `APP_PASSWORD` currently have fallback values.

- [x] **Step 3: Make `API_MODEL` required**

In `src/config.py`, replace:

```python
API_MODEL = os.getenv("API_MODEL", "anthropic/claude-sonnet-4-20250514").strip()
```

with:

```python
API_MODEL = _require("API_MODEL")
```

- [x] **Step 4: Remove the public fallback password**

In `review.py`, replace the existing password block with:

```python
# Single shared password; no accounts. This must be configured explicitly so a
# deployed copy can never fall back to a password published in source control.
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
if not APP_PASSWORD:
    raise RuntimeError(
        "Missing required environment variable 'APP_PASSWORD'. "
        "Set it in .env for local use or in the deployment environment."
    )

# Signs the session cookie. Render supplies a stable generated value; local
# development may use SECRET_KEY from .env or a process-local random fallback.
app.secret_key = os.getenv("SECRET_KEY", "").strip() or secrets.token_hex(32)
```

- [x] **Step 5: Run configuration and application tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_configuration_contract -v

API_BASE_URL=https://example.invalid/api/v3 \
API_KEY=test-key \
API_MODEL=test-model \
NOTION_TOKEN=test-notion-token \
NOTION_DATABASE_ID=test-database-id \
APP_PASSWORD=test-password \
SECRET_KEY=test-secret \
.venv/bin/python -m unittest discover -v
```

Expected: all tests pass.

- [x] **Step 6: Commit the configuration contract**

```bash
git add tests/test_configuration_contract.py src/config.py review.py
git commit -m "fix: require explicit model and app password"
```

---

### Task 3: Align Render with In-Memory Scene Talk Sessions

**Files:**
- Create: `tests/test_repository_accuracy.py`
- Modify: `render.yaml`
- Modify: `Procfile`

- [x] **Step 1: Add failing deployment-consistency tests**

Create `tests/test_repository_accuracy.py` with:

```python
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
```

- [x] **Step 2: Run the deployment test and verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: failure showing both deployment files still specify two workers.

- [x] **Step 3: Change both deployment entry points to one worker**

Use this exact command in `render.yaml`:

```yaml
startCommand: gunicorn review:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

Use this exact command in `Procfile`:

```text
web: gunicorn review:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

Update the nearby `render.yaml` comment to explain that one worker is required while Scene Talk sessions remain process-local.

- [x] **Step 4: Run the deployment test and full Python tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v

API_BASE_URL=https://example.invalid/api/v3 \
API_KEY=test-key \
API_MODEL=test-model \
NOTION_TOKEN=test-notion-token \
NOTION_DATABASE_ID=test-database-id \
APP_PASSWORD=test-password \
SECRET_KEY=test-secret \
.venv/bin/python -m unittest discover -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the deployment fix**

```bash
git add tests/test_repository_accuracy.py render.yaml Procfile
git commit -m "fix: keep Scene Talk sessions on one worker"
```

---

### Task 4: Correct the Public Configuration and Repository Metadata Files

**Files:**
- Modify: `.env.example`
- Modify: `TODO.md`
- Modify: `src/__init__.py`
- Modify: `src/chat.py`
- Modify: `review.py`
- Create: `LICENSE`
- Modify: `tests/test_repository_accuracy.py`

- [x] **Step 1: Extend repository tests for public configuration and metadata**

Add these methods to `RepositoryAccuracyTests`:

```python
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
```

- [x] **Step 2: Run the expanded tests and verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: failures for the obsolete environment template, obsolete roadmap, and missing license.

- [x] **Step 3: Replace `.env.example` with accurate safe placeholders**

Use:

```dotenv
# OpenAI-compatible Chat Completions endpoint.
# The deployed version currently uses Volcengine Ark; another compatible
# provider can be used if it supports the required vision and tool-call features.
API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
API_MODEL=your-model-or-endpoint-id

# Notion integration token and target database id.
NOTION_TOKEN=ntn_your-token
NOTION_DATABASE_ID=your-database-id

# Shared password for the Flask web app. There are no individual user accounts.
APP_PASSWORD=choose-a-strong-shared-password

# Stable secret used to sign Flask session cookies.
# Generate one locally with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-a-long-random-value

# Folder watched for new screenshots. Empty means ./screenshots.
WATCH_DIR=

# Image host: notion (default) or imgur.
IMAGE_HOST=notion
IMGUR_CLIENT_ID=

# Optional proxy for Notion and image-host traffic. The model endpoint stays direct.
HTTPS_PROXY=
```

- [x] **Step 4: Replace `TODO.md` with the current roadmap**

Use:

```markdown
# BingeLingo Roadmap

BingeLingo is a personal MVP. The complete capture → review → speaking-practice
loop is working; the items below are the next improvements rather than missing
claims about already-shipped features.

## Next priorities

1. **Persistent deployment storage**
   - Move characters, review logs, and app settings from ephemeral local SQLite
     files to durable storage, or attach a persistent disk.
   - Persist Scene Talk sessions so they survive process restarts and can support
     more than one Gunicorn worker.

2. **True spaced-repetition scheduling**
   - Use the existing review-attempt history to select due expressions.
   - Add interval and mastery fields instead of treating the log as recording only.

3. **Current-show consistency**
   - Restrict Scene Talk target-expression selection to the active show instead
     of reading expressions from every Notion card.

4. **Voice practice**
   - Add optional speech input, TTS, and pronunciation feedback after the text
     interaction is stable.

5. **Multi-user readiness**
   - Replace the shared-password gate with account isolation only if the product
     grows beyond a personal demo or small seed-user test.

6. **Reliability and observability**
   - Expand automated coverage for the watcher, Notion mapping, and review flow.
   - Add structured production logging and clearer health checks.

## Completed product loop

- Screenshot-folder monitoring and multimodal expression extraction.
- Structured Notion storage with the original screenshot as evidence.
- Show and episode organization.
- Three-layer contextual Revision with attempt history.
- Scene Talk character generation and roleplay practice.
- Practice to Go prompt export for external AI chat tools.
- Shared-password access control and Render deployment.
```

- [x] **Step 5: Correct stale module descriptions**

Set `src/__init__.py` to:

```python
"""BingeLingo — capture, review, and practise English expressions from TV."""
```

Replace the opening `src/chat.py` docstring with:

```python
"""Scene Talk roleplay practice and AI-generated character personas.

The learner selects a character and practises saved expressions through a short
conversation. Character records live in SQLite, while active chat sessions are
process-local and therefore require a single Gunicorn worker in the current MVP.
All model calls reuse the OpenAI-compatible client and configuration from the
capture pipeline.
"""
```

Replace the opening `review.py` docstring with:

```python
"""BingeLingo Flask application for Revision, Scene Talk, and Practice to Go.

Run locally with `python review.py`, or deploy the `app` object through Gunicorn.
Notion credentials and model API keys stay server-side; browsers receive only
the application data returned by authenticated API routes.
"""
```

- [x] **Step 6: Add the MIT license**

Create `LICENSE` with the standard MIT license text beginning:

```text
MIT License

Copyright (c) 2026 Yang Qing

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
```

Continue with the complete standard MIT terms through the warranty and liability disclaimer.

- [x] **Step 7: Run repository tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: all repository-accuracy tests pass.

- [x] **Step 8: Commit public configuration and metadata corrections**

```bash
git add .env.example TODO.md LICENSE src/__init__.py src/chat.py review.py tests/test_repository_accuracy.py
git commit -m "docs: align public configuration with current product"
```

---

### Task 5: Rewrite the README Around the Current Product

**Files:**
- Modify: `README.md`
- Modify: `tests/test_repository_accuracy.py`

- [x] **Step 1: Add failing README-accuracy tests**

Add these methods to `RepositoryAccuracyTests`:

```python
    def test_readme_describes_the_current_product(self):
        text = self.read("README.md")
        for required in (
            "Revision",
            "Scene Talk",
            "Practice to Go",
            "OpenAI-compatible Chat Completions",
            "Volcengine Ark",
            "SQLite",
            "Render",
            "APP_PASSWORD",
            "SECRET_KEY",
            "Current limitations",
        ):
            self.assertIn(required, text)

    def test_readme_does_not_describe_the_obsolete_architecture(self):
        text = self.read("README.md")
        for obsolete in (
            "Claude (native",
            "Anthropic-native Messages API",
            "`anthropic`",
            "claude-sonnet-4-5",
            "three recall modes",
            "web/index.html",
            "web/app.js",
        ):
            self.assertNotIn(obsolete, text)

    def test_readme_references_existing_core_paths(self):
        text = self.read("README.md")
        for path in (
            "main.py",
            "review.py",
            "src/vision.py",
            "src/chat.py",
            "src/review_log.py",
            "src/characters.py",
            "src/settings.py",
            "web/review.html",
            "web/chat.html",
            "web/export.html",
            "render.yaml",
        ):
            self.assertIn(path, text)
            self.assertTrue((ROOT / path).exists(), path)
```

- [x] **Step 2: Run the README tests and verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: failures for missing current features and obsolete architecture claims.

- [x] **Step 3: Replace `README.md` with the approved current structure**

Write a concise English README containing these exact sections and facts:

```markdown
# BingeLingo

**Turn subtitle screenshots into a reusable English learning loop — capture
expressions, review them in context, and practise through character conversations.**

[Portfolio](https://yangqingportfolio.com.cn) · Personal MVP · macOS-first capture workflow

BingeLingo is an independent AI product experiment for advanced English learners.
It starts with a familiar habit—saving a subtitle screenshot—and carries the
expression beyond collection into contextual recall and speaking practice.

## Why I built it

Advanced learners often understand an idiom, phrasal verb, collocation, or slang
expression while watching a show but cannot retrieve it when speaking. Screenshots
accumulate, AI explanations disappear into chat history, and manually organizing
examples interrupts the viewing experience. BingeLingo connects those fragmented
steps into one workflow aimed at the gap between recognition and active use.

## Product workflow

```text
Subtitle screenshot
        ↓
Multimodal expression extraction
        ↓
Notion knowledge card + original image evidence
        ↓
Contextual Revision with progressive hints
        ↓
Scene Talk character conversation
        ↓
Practice to Go prompt for another AI chat tool
```

## Core features

### 1. Screenshot capture and expression extraction

- A macOS watcher monitors a dedicated screenshot folder.
- A vision-capable model is called through the OpenAI Python SDK and an
  OpenAI-compatible Chat Completions endpoint.
- The extraction prompt focuses on expressions an advanced learner understands
  but may not actively produce: idioms, phrasal verbs, fixed collocations, slang,
  and tone-carrying colloquialisms.
- Tool Calling returns structured fields instead of relying on free-form text.
- Each Notion entry stores meaning, context, original subtitle, difficulty,
  review sentence, collocation frame, show, episode, and the source screenshot.

### 2. Revision

Revision uses a progressive recall flow rather than the early three-mode design:

1. Recall the expression from a newly generated conversational context.
2. Try again with Chinese meaning and initial-letter hints.
3. Reveal the answer, usage details, collocation frame, original line, and screenshot.

Attempts are recorded in local SQLite with result type, elapsed time, history,
today's count, and first-try accuracy. This is currently a recording layer, not
a complete spaced-repetition scheduler.

### 3. Scene Talk

- Generate or select show-based character personas.
- Practise target expressions through short roleplay conversations.
- The character creates natural openings without directly revealing which phrase
  the learner should use.
- End each session with a short usage debrief.
- Character records are stored in SQLite; active sessions remain in process memory.

### 4. Practice to Go

Choose a character, target expressions, conversation length, guidance level,
setting, correction style, and response language. BingeLingo assembles a portable
prompt that can be pasted into ChatGPT, Doubao, Kimi, Claude, or another AI chat
tool. This module builds the prompt locally and does not make another model call.

### 5. Show-based organization

The watcher asks for the current show and episode, saves them into Notion, and
organizes screenshots by show. Revision, Scene Talk, and Practice to Go share a
current-show switcher.

## Architecture

```text
macOS screenshot folder
        │
        ▼
watchdog → src/vision.py → OpenAI-compatible model endpoint
        │                         │
        │                         └─ structured Tool Calling output
        ▼
src/notion_writer.py → Notion cards + source screenshot
        │
        ▼
review.py (Flask / Gunicorn)
        ├─ Revision       → Notion cards + data/review_log.db
        ├─ Scene Talk     → data/characters.db + in-memory sessions
        ├─ Show settings  → data/app_settings.db
        └─ Practice to Go → portable prompt assembled in the browser
```

The code uses the OpenAI Python SDK against an OpenAI-compatible Chat Completions
API. The deployed version currently uses Volcengine Ark. The model and endpoint
are configured through environment variables rather than hard-coded provider
credentials.

## Engineering highlights

- Structured multimodal Tool Calling for screenshot analysis.
- Prompt-level filtering and dictionary-form normalization of expressions.
- Recovery for malformed or string-wrapped tool arguments.
- Inflection-tolerant answer matching with word-order checks.
- JSON API error normalization so HTML/empty upstream errors become readable UI messages.
- Ark authentication migration from an incompatible SDK/header format.
- Render timeout mitigation through smaller character-generation requests and disabled thinking.
- Shared-password access gate for a small demo without collecting user accounts.

## Tech stack

| Area | Technology |
| --- | --- |
| Backend | Python 3.11, Flask, Gunicorn |
| Model client | OpenAI Python SDK |
| Model protocol | OpenAI-compatible Chat Completions with vision and Tool Calling |
| Current provider | Volcengine Ark |
| Knowledge store | Notion API |
| Local state | SQLite and small local state files |
| Capture | watchdog, macOS screenshot workflow |
| Frontend | HTML, CSS, vanilla JavaScript, Fetch API |
| Deployment | Render |

## Repository structure

```text
binge-lingo/
├── main.py                    # watcher and single-image entry point
├── review.py                  # Flask app and authenticated API routes
├── render.yaml                # Render service definition
├── Procfile                   # Gunicorn entry point
├── requirements.txt
├── src/
│   ├── config.py              # environment and path configuration
│   ├── watcher.py             # screenshot-folder observer
│   ├── vision.py              # vision analysis and review-sentence generation
│   ├── models.py              # extraction data structures
│   ├── notion_writer.py       # Notion page and image writes
│   ├── notion_reader.py       # Notion cards for the web application
│   ├── matching.py            # inflection-tolerant answer checking
│   ├── review_log.py          # Revision history in SQLite
│   ├── characters.py          # character personas in SQLite
│   ├── chat.py                # Scene Talk generation and sessions
│   └── settings.py            # current-show state in SQLite
├── web/
│   ├── login.html
│   ├── review.html
│   ├── chat.html
│   ├── export.html
│   ├── common.js
│   ├── review.js
│   ├── chat.js
│   ├── export.js
│   ├── api-response.js
│   └── style.css
├── tests/
│   ├── test_chat_cast.py
│   ├── test_configuration_contract.py
│   ├── test_repository_accuracy.py
│   └── api-response.test.js
└── data/                      # runtime SQLite files; databases are git-ignored
```

## Local setup

```bash
git clone https://github.com/yangqing8205/binge-lingo.git
cd binge-lingo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Configure `.env` before importing or running the application:

| Variable | Purpose |
| --- | --- |
| `API_BASE_URL` | OpenAI-compatible Chat Completions base URL |
| `API_KEY` | API key for the configured provider |
| `API_MODEL` | Provider model name or endpoint ID; required |
| `NOTION_TOKEN` | Notion integration token |
| `NOTION_DATABASE_ID` | Target Notion database ID |
| `APP_PASSWORD` | Shared password for the web app; required |
| `SECRET_KEY` | Stable Flask session-signing secret |
| `WATCH_DIR` | Screenshot root; defaults to `./screenshots` |
| `IMAGE_HOST` | `notion` or `imgur` |
| `IMGUR_CLIENT_ID` | Required only for Imgur uploads |
| `HTTPS_PROXY` | Optional proxy for Notion/image-host traffic |

For the base Notion schema, create `Expression` as the title property and
`Chinese`, `Context`, `Difficulty`, `Example`, and `Screenshot` as rich-text
properties. The application can add `ReviewSentence`, `CommonStructure`, `Source`,
`Show`, and `Episode` when they are missing.

## Usage

Start the screenshot watcher:

```bash
python main.py
```

It asks for the show and optional episode, then watches the corresponding folder.
To process one image directly:

```bash
python main.py path/to/screenshot.png
```

Start the web application locally:

```bash
python review.py
# http://127.0.0.1:5001
```

Available pages:

- `/review` — contextual Revision
- `/chat` — Scene Talk
- `/export` — Practice to Go

## Render deployment

`render.yaml` installs the Python requirements and serves `review:app` through
Gunicorn. The current deployment intentionally uses one worker because active
Scene Talk sessions are stored in process memory. Keep the existing 120-second
timeout for model-backed character generation.

Configure `API_BASE_URL`, `API_KEY`, `API_MODEL`, `NOTION_TOKEN`,
`NOTION_DATABASE_ID`, and `APP_PASSWORD` in Render. `render.yaml` generates a
stable `SECRET_KEY`.

## Current limitations

- The automatic capture workflow is macOS-first.
- This is a personal MVP with a shared password, not a multi-tenant account system.
- Cards depend on the owner's Notion database.
- SQLite data and current-show settings are ephemeral on Render without a persistent disk.
- Scene Talk sessions are lost on process restart and currently require one worker.
- Revision records attempts but does not yet schedule a full SRS queue.
- Scene Talk target selection still reads the full card set instead of only the active show.
- There is no speech input, pronunciation scoring, or TTS yet.
- Render free instances may cold-start or time out during model requests.

See [TODO.md](TODO.md) for the current roadmap.

## License

MIT — see [LICENSE](LICENSE).
```

- [x] **Step 4: Run README and repository tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: all repository-accuracy tests pass.

- [x] **Step 5: Commit the README rewrite**

```bash
git add README.md tests/test_repository_accuracy.py
git commit -m "docs: rewrite README for current learning workflow"
```

---

### Task 6: Run Complete Verification and Publish

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-repository-accuracy-audit.md` (checkboxes only)

- [x] **Step 1: Run all Python tests with explicit configuration**

Run:

```bash
API_BASE_URL=https://example.invalid/api/v3 \
API_KEY=test-key \
API_MODEL=test-model \
NOTION_TOKEN=test-notion-token \
NOTION_DATABASE_ID=test-database-id \
APP_PASSWORD=test-password \
SECRET_KEY=test-secret \
.venv/bin/python -m unittest discover -v
```

Expected: every Python test passes with 0 failures and 0 errors.

- [x] **Step 2: Run all JavaScript tests**

Run:

```bash
node --test tests/api-response.test.js
```

Expected: 4 tests pass and 0 fail.

- [x] **Step 3: Run static repository checks**

Run:

```bash
git diff --check

rg -n -i \
  'Anthropic-native|api\.anthropic\.com|claude-sonnet|model\.zhenguanyu\.com|sk-mg|--workers 2' \
  README.md .env.example TODO.md src review.py render.yaml Procfile
```

Expected: `git diff --check` succeeds and the `rg` command returns no matches.

Then confirm the intentional external-tool reference still exists:

```bash
rg -n 'ChatGPT / 豆包 / Kimi / Claude' web/export.html
```

Expected: exactly the existing Practice to Go explanatory line is returned.

- [x] **Step 4: Review the complete diff and commit plan completion**

Run:

```bash
git status --short
git diff HEAD~3 --stat
git log --oneline -6
```

Mark all completed checkboxes in this plan, then run:

```bash
git add docs/superpowers/plans/2026-08-10-repository-accuracy-audit.md
git commit -m "docs: record repository audit completion"
```

- [x] **Step 5: Push the reviewed commits**

Run:

```bash
git push origin main
```

Expected: GitHub accepts the new commits on `main`.

- [x] **Step 6: Verify published repository content through GitHub**

Run:

```bash
gh api repos/yangqing8205/binge-lingo/readme \
  -H 'Accept: application/vnd.github.raw+json' \
  | rg -n 'OpenAI-compatible Chat Completions|Scene Talk|Practice to Go|Current limitations'

gh api repos/yangqing8205/binge-lingo/contents/.env.example \
  -H 'Accept: application/vnd.github.raw+json' \
  | rg -n 'ark.cn-beijing.volces.com|APP_PASSWORD|SECRET_KEY'

gh api repos/yangqing8205/binge-lingo/contents/render.yaml \
  -H 'Accept: application/vnd.github.raw+json' \
  | rg -n -- '--workers 1 --timeout 120'
```

Expected: every command returns the new published content.
