# Scene Talk Timeout Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep automatic cast generation below Gunicorn's 120-second limit and turn non-JSON proxy failures into clear user-facing errors.

**Architecture:** Generate at most three missing cast members per request while retaining a six-character eventual target. Configure the OpenAI-compatible client to stop before Gunicorn, map upstream timeouts to JSON 504 responses, and centralize browser response parsing in a small dependency-free helper.

**Tech Stack:** Python 3.9, Flask, OpenAI Python SDK, `unittest`, vanilla JavaScript, Node's built-in test runner.

---

### Task 1: Limit each cast-generation batch

**Files:**
- Create: `tests/test_chat_cast.py`
- Modify: `src/chat.py:117-196,335-418`
- Modify: `review.py:292-343`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_cast.py` with isolated environment setup, a fake OpenAI tool-call response, and assertions that `generate_cast_for_show(..., requested_count=3)` includes `Generate exactly 3 new characters` in the prompt, uses a reduced token budget, and returns no more than three valid items. Add a Flask route test that patches `characters.list_characters`, calls `/api/characters/for-show`, and asserts the chat layer receives `requested_count=min(3, 6-len(existing))`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3 -m unittest tests.test_chat_cast -v`

Expected: FAIL because `generate_cast_for_show` does not accept `requested_count` and the route does not pass it.

- [ ] **Step 3: Implement the batch limit**

Add `requested_count: int = 3` to `generate_cast_for_show`, clamp it to `1..3`, add this exact instruction to the user prompt:

```python
prompt += f"\n\nGenerate exactly {requested_count} new characters in this call."
```

Reduce cast `max_tokens` from `3000` to `1600`, and stop collecting results at `requested_count`. In `review.py`, define `_CAST_BATCH_SIZE = 3`, compute `requested_count = min(_CAST_BATCH_SIZE, _CAST_TARGET - len(existing))`, and pass it to `generate_cast_for_show`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `python3 -m unittest tests.test_chat_cast -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_chat_cast.py src/chat.py review.py
git commit -m "fix: bound Scene Talk cast generation batches"
```

### Task 2: Return JSON before Gunicorn kills slow requests

**Files:**
- Modify: `src/chat.py:18-23`
- Modify: `review.py:295-343`
- Modify: `tests/test_chat_cast.py`

- [ ] **Step 1: Write the failing timeout test**

Patch `chat.generate_cast_for_show` to raise `openai.APITimeoutError` and assert the route returns status 504 with:

```python
{"ok": False, "error": "角色生成超时，请稍后重试。"}
```

- [ ] **Step 2: Run the timeout test and verify RED**

Run: `python3 -m unittest tests.test_chat_cast.CastRouteTests.test_timeout_returns_json_504 -v`

Expected: FAIL because the route currently returns generic status 502.

- [ ] **Step 3: Implement bounded client and timeout mapping**

Construct the shared client as:

```python
_client = OpenAI(
    base_url=config.API_BASE_URL,
    api_key=config.API_KEY,
    timeout=90.0,
    max_retries=0,
)
```

Import `APITimeoutError` in `review.py`, catch it before the generic exception, log the timeout, and return the specified JSON 504 response.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run: `python3 -m unittest tests.test_chat_cast -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chat.py review.py tests/test_chat_cast.py
git commit -m "fix: return JSON when Ark cast generation times out"
```

### Task 3: Parse API responses safely in the browser

**Files:**
- Create: `web/api-response.js`
- Create: `tests/api-response.test.js`
- Modify: `web/chat.html:118-119`
- Modify: `web/chat.js:39-365`

- [ ] **Step 1: Write failing JavaScript tests**

Use `node:test` to require `web/api-response.js` and test four cases: valid JSON success, JSON error preservation, HTML 500 becoming `服务端暂时不可用（HTTP 500），请稍后重试。`, and empty 504 becoming `请求超时（HTTP 504），请稍后重试。`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `node --test tests/api-response.test.js`

Expected: FAIL because `web/api-response.js` does not exist.

- [ ] **Step 3: Implement the parser**

Create a browser/CommonJS-compatible helper exporting `readApiResponse(response)`. It reads `await response.text()`, parses JSON when possible, returns parsed JSON unchanged, and otherwise returns `{ok:false,error:<readable message>}` based on status. Load it before `common.js` and `chat.js`, then replace every `await res.json()` in `web/chat.js` with `await readApiResponse(res)`.

- [ ] **Step 4: Run JavaScript tests and verify GREEN**

Run: `node --test tests/api-response.test.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/api-response.js web/chat.html web/chat.js tests/api-response.test.js
git commit -m "fix: show readable Scene Talk API errors"
```

### Task 4: Remove the temporary credential diagnostic

**Files:**
- Modify: `review.py:393-424`
- Modify: `tests/test_chat_cast.py`

- [ ] **Step 1: Write the failing security test**

Add a Flask test asserting authenticated `GET /api/debug/ark-key` returns 404.

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m unittest tests.test_chat_cast.SecurityCleanupTests -v`

Expected: FAIL with status 200 because the endpoint still exists.

- [ ] **Step 3: Delete the endpoint**

Remove `api_debug_ark_key` and its route from `review.py`.

- [ ] **Step 4: Run all local tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/api-response.test.js
python3 -m compileall -q src review.py
git diff --check
```

Expected: all tests pass, compilation succeeds, and `git diff --check` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add review.py tests/test_chat_cast.py
git commit -m "chore: remove Ark credential debug endpoint"
```

### Task 5: Deploy and verify production

**Files:**
- No additional source files.

- [ ] **Step 1: Push the completed commits**

Run: `git push origin main`

Expected: GitHub accepts the commits and Render starts a deployment.

- [ ] **Step 2: Wait for the GitHub deployment status**

Poll the latest GitHub deployment status until it reports `success`; record the new deployment ID and Render URL.

- [ ] **Step 3: Verify production behavior**

Authenticate to `https://binge-lingo.onrender.com`, call `POST /api/characters/for-show` with `{"show":"Breaking Bad"}`, and confirm it returns JSON before 120 seconds. Verify `GET /api/characters?show=Breaking%20Bad` contains created characters and `GET /api/debug/ark-key` returns 404.

- [ ] **Step 4: Report evidence**

Report exact test commands, production HTTP status/content type/elapsed time, created character count, commit hashes, and any remaining operational caveats.

