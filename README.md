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

The main product surfaces are `main.py`, `review.py`, `src/vision.py`,
`src/chat.py`, `src/review_log.py`, `src/characters.py`, `src/settings.py`,
`web/review.html`, `web/chat.html`, `web/export.html`, and `render.yaml`.

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
