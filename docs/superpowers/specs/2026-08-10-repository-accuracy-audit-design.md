# BingeLingo Repository Accuracy Audit Design

## Goal

Bring BingeLingo's public documentation, example configuration, security defaults, and Render process configuration into alignment with the current implementation without expanding the product into a new architecture.

## Confirmed Root Cause

The product evolved from a screenshot-to-Notion utility using an Anthropic-compatible gateway into a larger Flask application using the OpenAI Python SDK and an OpenAI-compatible Chat Completions API. The implementation was updated incrementally, but the README, environment template, roadmap, selected module comments, and one configuration fallback were not updated with it.

## Chosen Scope

This change uses the documentation-plus-configuration-plus-deployment approach. It fixes demonstrated inaccuracies and operational defects while deliberately avoiding unrelated feature development.

### In Scope

- Rewrite `README.md` around the current learning loop:
  screenshot capture → expression extraction → contextual Revision → Scene Talk → Practice to Go.
- Describe the current OpenAI-compatible API integration and the deployed use of Volcengine Ark.
- Update the feature list, architecture, setup, configuration, deployment instructions, limitations, and roadmap.
- Replace the outdated Anthropic example in `.env.example` with safe OpenAI-compatible Ark placeholders.
- Make `API_MODEL` an explicitly required setting instead of silently falling back to a Claude model identifier.
- Add `APP_PASSWORD` and `SECRET_KEY` to `.env.example` without exposing real credentials.
- Remove the public default application password from `review.py` and fail clearly when it is missing.
- Run Gunicorn with one worker because Scene Talk sessions are currently stored in process memory.
- Rewrite `TODO.md` so completed functionality is no longer listed as future work and old company-gateway details are removed.
- Correct stale package/module descriptions in `review.py`, `src/chat.py`, and `src/__init__.py` where they describe an earlier local-only product.
- Add a standard MIT `LICENSE` file to match the repository's stated license.
- Add regression and repository-consistency checks for the corrected behavior.

### Out of Scope

- Moving Scene Talk sessions from memory to SQLite or another shared store.
- Adding a persistent Render disk or migrating Notion/SQLite data to a hosted database.
- Building multi-user authentication or account isolation.
- Implementing spaced-repetition scheduling, TTS, speech recognition, or pronunciation scoring.
- Changing the product UI or adding new features.
- Removing references to Claude where Claude is correctly listed as an external tool that can receive a Practice to Go prompt.

## Configuration Design

### Model API

`src/config.py` will continue to require `API_BASE_URL` and `API_KEY`. `API_MODEL` will use the same `_require` path so an omitted model fails with a direct configuration error instead of selecting an unrelated Claude model.

`.env.example` will use a generic Ark-compatible example:

```dotenv
API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
API_MODEL=your-model-or-endpoint-id
```

The example will explain that the application uses the OpenAI Python SDK against an OpenAI-compatible Chat Completions endpoint. It will not claim that every compatible provider supports Ark's `thinking` extension used by Scene Talk.

### Web Authentication

`review.py` will read `APP_PASSWORD` as a stripped environment value. If it is absent, application startup will raise a clear `RuntimeError` explaining how to configure it. There will be no baked-in or fallback password.

`SECRET_KEY` will remain configurable and will be documented as required for stable deployed sessions. Render already generates it through `render.yaml`; local users will receive a placeholder in `.env.example`.

## Deployment Design

Both `render.yaml` and `Procfile` will run Gunicorn with one worker and the existing 120-second timeout. This matches the current in-memory `_sessions` design in `src/chat.py` and prevents a conversation from being created in one worker and looked up in another.

The README will explicitly state that this is a personal MVP. Local SQLite databases and settings are not durable on Render's free ephemeral filesystem, and Scene Talk sessions are not preserved across process restarts.

## Documentation Design

The README will be rewritten rather than patched paragraph by paragraph because nearly every major section describes an earlier product. The new structure will be:

1. Product statement and intended learner.
2. Why the product exists.
3. Current learning loop.
4. Core features.
5. Architecture and data flow.
6. Engineering highlights.
7. Technology stack.
8. Repository structure.
9. Local setup and environment configuration.
10. Watcher and web-app usage.
11. Render deployment notes.
12. Current limitations and roadmap.
13. License.

The documentation will distinguish between three concepts:

- the OpenAI Python SDK used by the code;
- the OpenAI-compatible API protocol used by the configured model provider;
- external chat products, including Claude, that may receive exported Practice to Go prompts.

## Testing and Verification

Automated checks will cover:

- importing configuration without `API_MODEL` produces a missing-variable error;
- importing the web application without `APP_PASSWORD` produces a clear missing-variable error;
- the Python application tests pass with explicit test environment variables;
- the JavaScript API-response tests pass;
- `render.yaml` and `Procfile` both specify one Gunicorn worker and a 120-second timeout;
- public docs and configuration contain no stale Anthropic-native or Claude-model claims;
- the correct external-tool reference to Claude in Practice to Go remains allowed;
- README paths and filenames match the repository tree;
- the final repository contains an MIT `LICENSE` file.

After local verification, the changes will be committed and pushed to `main`. The GitHub API will then be used to read back the public README and key configuration files to confirm that the published repository matches the reviewed version.
