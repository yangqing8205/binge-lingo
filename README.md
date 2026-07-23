# BingeLingo

**Turn the shows you binge into an English vocabulary notebook — automatically.**

BingeLingo watches a screenshot folder on your Mac. The moment you grab a frame
from an English TV show or film, it reads the subtitle, decides whether the line
contains an expression worth learning, and files a structured flashcard — Chinese
gloss, usage note, the original line, difficulty, and the screenshot itself — into
a Notion database. No copy-pasting, no manual lookups. Screenshot, keep watching,
review in Notion later.

It is built for **advanced learners**: the extraction bar is not "words you don't
know" but "expressions you understand yet couldn't produce yourself" — idioms,
phrasal verbs, fixed collocations, and tone-carrying colloquialisms that textbooks
skip.

## How it works

```
  Ctrl+Shift+L                                                    Notion
  (custom screenshot) ──▶ screenshots/ ──▶ watchdog ──▶ vision ──▶ database
                                             │            │           ▲
                                     new-file event   Claude (native  │
                                                       Messages API)   │
                                                            │          │
                                                       structured      │
                                                       extraction ─────┘
                                                                   image upload
```

1. **Capture** — a dedicated hotkey saves a selection screenshot into the watched
   folder, keeping it separate from your everyday `Cmd+Shift+4` captures.
2. **Detect** — a `watchdog` observer fires on each new image and waits for the
   file to finish writing before processing.
3. **Understand** — the screenshot is sent to a multimodal Claude model through the
   Anthropic-native Messages API. A forced tool call returns a strict schema:
   expression, Chinese meaning, usage scenario, the verbatim original line, and a
   difficulty rating.
4. **Store** — one Notion row is created per expression, with the screenshot
   embedded in the page body. Images are uploaded via Notion's own File Upload API
   (no third-party host required), with an Imgur fallback.

## Features

- **Zero-friction capture** — screenshot with a hotkey, everything else is automatic.
- **Advanced-learner filtering** — a carefully tuned prompt rejects the obvious and
  surfaces the idiomatic. A deliberate screenshot always yields at least one card.
- **Structured Notion output** — writes directly into typed database columns
  (Expression / Chinese / Context / Difficulty / Example / Source / Screenshot),
  not a wall of text.
- **Resilient parsing** — tolerates a gateway that occasionally returns malformed,
  string-wrapped, or unescaped JSON, salvaging valid records field-by-field.
- **Private by design** — no autostart, no background daemon. You launch it before
  watching and quit it after. Nothing runs unless you ask.
- **Network-aware** — routes only Notion traffic through an optional proxy while
  keeping the LLM call direct, and retries the intermittent TLS failures seen on
  older system SSL stacks.

## Tech stack

| Concern            | Choice                                              |
| ------------------ | --------------------------------------------------- |
| Language           | Python 3.9+                                          |
| Folder watching    | [`watchdog`](https://pypi.org/project/watchdog/)    |
| LLM                | [`anthropic`](https://pypi.org/project/anthropic/) (native Messages API, multimodal, tool-use) |
| Notion             | [`notion-client`](https://pypi.org/project/notion-client/) (2025-09-03 data-source API) |
| Image upload       | Notion File Upload API, with an Imgur fallback      |
| Config             | [`python-dotenv`](https://pypi.org/project/python-dotenv/) |
| HTTP               | [`requests`](https://pypi.org/project/requests/)    |

## Architecture

```
binge-lingo/
├── main.py                 Entry point: watch mode, or single-image test mode
├── start-watching.command  Double-click launcher (foreground, quit to stop)
├── requirements.txt
├── .env                    Your secrets — git-ignored, never committed
├── .env.example            Config template
├── .gitignore
├── screenshots/            Watched folder (contents git-ignored)
└── src/
    ├── config.py           Loads and validates .env; central settings
    ├── models.py           Expression / ScreenshotAnalysis dataclasses
    ├── vision.py           Multimodal LLM call + tolerant structured parsing
    ├── uploader.py         Image upload to Notion (or Imgur), with SSL retry
    ├── notion_writer.py    Resolves the data source, writes one row per card
    └── watcher.py          watchdog observer + end-to-end pipeline orchestration
```

Each screenshot flows through `watcher → vision → notion_writer → uploader`, and a
local `.processed_screenshots.json` records what's already been handled so a
restart never double-files a card.

## Setup

```bash
git clone <your-repo-url> binge-lingo
cd binge-lingo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the template and fill in your own values:

```bash
cp .env.example .env
```

| Variable            | Description                                                      |
| ------------------- | ---------------------------------------------------------------- |
| `API_BASE_URL`      | Anthropic-native Messages API endpoint (or a compatible gateway) |
| `API_KEY`           | API key for the endpoint above                                   |
| `API_MODEL`         | Multimodal model id, e.g. `claude-sonnet-4-5`                    |
| `NOTION_TOKEN`      | Notion integration token                                         |
| `NOTION_DATABASE_ID`| Target database id                                               |
| `WATCH_DIR`         | Folder to watch (defaults to `./screenshots`)                    |
| `IMAGE_HOST`        | `notion` (default) or `imgur`                                    |
| `IMGUR_CLIENT_ID`   | Only needed when `IMAGE_HOST=imgur`                              |
| `HTTPS_PROXY`       | Optional proxy for Notion traffic; leave blank for direct access |

**Notion setup:** share the target database with your integration, and give it
these properties — a `title` column named **Expression**, plus rich-text columns
**Chinese**, **Context**, **Difficulty**, **Example**, **Source**, **Screenshot**.

## Usage

```bash
# Watch the folder continuously (Ctrl-C to stop)
python main.py

# Or process a single screenshot to test the full pipeline
python main.py path/to/screenshot.png
```

On macOS, double-click `start-watching.command` to launch the watcher in a Terminal
window and see live logs; closing the window stops it.

### Dedicated screenshot hotkey

To feed only the frames you choose into the pipeline, bind a hotkey to a selection
screenshot that saves into the watched folder — separate from your default
`Cmd+Shift+4`. Create an Automator **Quick Action** ("Run Shell Script") with:

```bash
FILE="$HOME/binge-lingo/screenshots/binge-$(date +%Y%m%d-%H%M%S).png"
/usr/sbin/screencapture -i "$FILE"
```

Save it, then assign a shortcut under **System Settings → Keyboard → Keyboard
Shortcuts → Services**.

## License

MIT

