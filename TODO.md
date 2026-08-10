# BingeLingo Roadmap

BingeLingo is a personal MVP. The complete capture → review → speaking-practice
loop is working; the items below are the next improvements rather than missing
claims about already-shipped features.

## Next priorities

1. **持久化存储 (Persistent deployment storage)**
   - Move characters, review logs, and app settings from ephemeral local SQLite
     files to durable storage, or attach a persistent disk.
   - Persist Scene Talk sessions so they survive process restarts and can support
     more than one Gunicorn worker.

2. **间隔重复调度 (True spaced-repetition scheduling)**
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
