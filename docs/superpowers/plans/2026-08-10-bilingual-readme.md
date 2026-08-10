# BingeLingo Bilingual README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete Simplified Chinese README while keeping English as the default, and replace proficiency-based audience labels with needs-based positioning in both languages.

**Architecture:** Documentation remains split into two peer files: `README.md` is the default English landing page and `README_CN.md` is the Chinese counterpart. Repository tests enforce reciprocal language links, prohibit learner-level labels, and verify that the Chinese page documents the same current product and deployment contract.

**Tech Stack:** Markdown, Python 3.11 `unittest`, Node.js test runner, GitHub CLI

---

### Task 1: Lock the Bilingual Documentation Contract

**Files:**
- Modify: `tests/test_repository_accuracy.py`

- [x] **Step 1: Add failing bilingual README tests**

Add these methods to `RepositoryAccuracyTests`:

```python
    def test_readmes_link_to_each_other(self):
        english = self.read("README.md")
        self.assertTrue((ROOT / "README_CN.md").exists())
        chinese = self.read("README_CN.md")
        self.assertIn('href="./README_CN.md"', english)
        self.assertIn('href="./README.md"', chinese)

    def test_readmes_use_needs_based_positioning(self):
        self.assertTrue((ROOT / "README_CN.md").exists())
        combined = self.read("README.md") + self.read("README_CN.md")
        normalized = " ".join(combined.split())
        for label in (
            "advanced English learners",
            "advanced learners",
            "advanced learner",
            "中高阶英语学习者",
            "中高阶",
        ):
            self.assertNotIn(label.lower(), combined.lower())
        self.assertIn(
            "English learners who want to turn expressions from shows into "
            "language they can actively use",
            normalized,
        )
        self.assertIn(
            "希望把影视中的地道表达真正用起来的英语学习者",
            combined,
        )

    def test_chinese_readme_describes_the_current_product(self):
        self.assertTrue((ROOT / "README_CN.md").exists())
        text = self.read("README_CN.md")
        for required in (
            "Revision",
            "Scene Talk",
            "Practice to Go",
            "OpenAI-compatible Chat Completions",
            "火山引擎 Ark",
            "SQLite",
            "Render",
            "APP_PASSWORD",
            "SECRET_KEY",
            "当前限制",
        ):
            self.assertIn(required, text)
```

- [x] **Step 2: Run the new tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: the new tests fail because `README_CN.md` does not exist, the English README has no Chinese link, and it still contains `advanced learner` wording.

- [x] **Step 3: Commit the failing tests**

```bash
git add tests/test_repository_accuracy.py
git commit -m "test: define bilingual README contract"
```

---

### Task 2: Update the English Positioning and Add the Chinese README

**Files:**
- Modify: `README.md`
- Create: `README_CN.md`

- [x] **Step 1: Add the language switch to the English README**

Immediately below `# BingeLingo`, add:

```markdown
<div align="right">
  <strong>English</strong> | <a href="./README_CN.md">简体中文</a>
</div>
```

Keep the existing portfolio metadata directly below the tagline:

```markdown
[Portfolio](https://yangqingportfolio.com.cn) · Personal MVP · macOS-first capture workflow
```

- [x] **Step 2: Replace proficiency-based wording in the English README**

Replace the opening product sentence with:

```markdown
BingeLingo is an independent AI product experiment for English learners who want
to turn expressions from shows into language they can actively use. It starts with
a familiar habit—saving a subtitle screenshot—and carries the expression beyond
collection into contextual recall and speaking practice.
```

Replace the first paragraph under `## Why I built it` with:

```markdown
English learners often understand an idiom, phrasal verb, collocation, or slang
expression while watching a show but cannot retrieve it when speaking. Screenshots
accumulate, AI explanations disappear into chat history, and manually organizing
examples interrupts the viewing experience. BingeLingo connects those fragmented
steps into one workflow aimed at the gap between recognition and active use.
```

Replace the extraction bullet with:

```markdown
- The extraction prompt focuses on useful expressions that are easy to recognize
  but harder to produce naturally: idioms, phrasal verbs, fixed collocations,
  slang, and tone-carrying colloquialisms.
```

- [x] **Step 3: Create the complete Chinese README**

Create `README_CN.md` with:

```markdown
# BingeLingo

<div align="right">
  <a href="./README.md">English</a> | <strong>简体中文</strong>
</div>

**把字幕截图变成一个可以反复使用的英语学习闭环：收集表达、结合语境复习，再通过角色对话真正用出来。**

[个人作品集](https://yangqingportfolio.com.cn) · 个人 MVP · 以 macOS 截图流程为主

BingeLingo 是一个面向希望把影视中的地道表达真正用起来的英语学习者的个人 AI 产品实验。它从“保存一张字幕截图”这个熟悉的动作出发，让表达不再停留在收藏，而是继续进入情境回忆与开口练习。

## 为什么做这个项目

英语学习者在看剧时，经常能够理解习语、短语动词、固定搭配或俚语，却很难在真实表达中主动想起来。截图会不断堆积，AI 给出的解释容易消失在聊天记录里，手动整理又会打断观看体验。BingeLingo 将这些零散动作连接成一个完整流程，解决“看得懂”与“真正会用”之间的距离。

## 产品流程

```text
字幕截图
   ↓
多模态模型提取地道表达
   ↓
Notion 知识卡片 + 原始截图证据
   ↓
带渐进提示的情境 Revision
   ↓
Scene Talk 角色对话练习
   ↓
导出 Practice to Go 提示词，在其他 AI 工具中继续练习
```

## 核心功能

### 1. 截图捕捉与表达提取

- macOS 文件夹监听器自动检测专用截图目录中的新图片。
- 通过 OpenAI Python SDK 调用支持视觉的 OpenAI-compatible Chat Completions 接口。
- 提取重点是“容易看懂、但不容易自然说出来”的实用表达，包括习语、短语动词、固定搭配、俚语和带有语气色彩的口语表达。
- 使用 Tool Calling 返回结构化字段，不依赖自由文本解析。
- 每条 Notion 记录包含中文含义、语境、原始字幕、难度、复习句、搭配框架、剧集信息和原始截图。

### 2. Revision 情境复习

Revision 使用渐进式回忆流程，而不是早期的三种独立复习模式：

1. 根据新生成的对话语境回忆目标表达。
2. 如果第一次没有想起来，显示中文含义和首字母提示。
3. 最后揭晓答案、用法、常见搭配、原始台词和截图。

系统使用本地 SQLite 记录作答结果、耗时、历史记录、当天复习数量和首次答对率。目前它是复习记录层，还不是完整的间隔重复调度系统。

### 3. Scene Talk 角色对话

- 根据影视作品生成或选择角色人格。
- 在短对话中练习已经收藏的目标表达。
- 角色会创造自然的使用机会，但不会直接告诉学习者应该使用哪个表达。
- 对话结束后生成简短的使用情况总结。
- 角色资料存储在 SQLite 中；当前对话 Session 仍保存在进程内存中。

### 4. Practice to Go

用户可以选择角色、目标表达、对话长度、提示强度、场景、纠错方式和回复语言。BingeLingo 会在浏览器中组装一份可移植的练习提示词，可以复制到 ChatGPT、豆包、Kimi、Claude 或其他 AI 对话工具中继续练习。这个模块只生成提示词，不会额外调用模型接口。

### 5. 按剧集组织内容

截图监听器会询问当前影视作品和集数，将信息保存到 Notion，并按作品组织截图。Revision、Scene Talk 与 Practice to Go 共用当前作品切换器。

## 系统架构

```text
macOS 截图文件夹
        │
        ▼
watchdog → src/vision.py → OpenAI-compatible 模型接口
        │                         │
        │                         └─ Tool Calling 结构化输出
        ▼
src/notion_writer.py → Notion 卡片 + 原始截图
        │
        ▼
review.py（Flask / Gunicorn）
        ├─ Revision       → Notion 卡片 + data/review_log.db
        ├─ Scene Talk     → data/characters.db + 内存 Session
        ├─ 当前作品设置   → data/app_settings.db
        └─ Practice to Go → 浏览器端组装可移植提示词
```

代码通过 OpenAI Python SDK 调用 OpenAI-compatible Chat Completions API。当前部署使用火山引擎 Ark，具体模型和接口地址通过环境变量配置，代码中不保存供应商密钥。

## 工程实现亮点

- 使用多模态 Tool Calling 进行结构化字幕截图分析。
- 通过 Prompt 筛选和词形归一化控制表达质量。
- 可以恢复格式异常或被字符串包裹的 Tool Calling 参数。
- 支持词形变化、同时检查词序的答案匹配。
- 将 HTML 或空的上游错误转换成前端可读的 JSON 错误。
- 完成 Ark 鉴权方式和兼容接口迁移。
- 通过缩小角色生成请求、关闭思考模式和保留 120 秒超时缓解 Render 请求超时。
- 使用共享密码保护个人演示，同时不收集用户账号信息。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 后端 | Python 3.11、Flask、Gunicorn |
| 模型客户端 | OpenAI Python SDK |
| 模型协议 | 支持视觉和 Tool Calling 的 OpenAI-compatible Chat Completions |
| 当前模型服务 | 火山引擎 Ark |
| 知识存储 | Notion API |
| 本地状态 | SQLite 和少量本地状态文件 |
| 截图捕捉 | watchdog、macOS 截图流程 |
| 前端 | HTML、CSS、原生 JavaScript、Fetch API |
| 部署 | Render |

## 仓库结构

主要文件包括 `main.py`、`review.py`、`src/vision.py`、`src/chat.py`、`src/review_log.py`、`src/characters.py`、`src/settings.py`、`web/review.html`、`web/chat.html`、`web/export.html` 和 `render.yaml`。

```text
binge-lingo/
├── main.py                    # 截图监听与单张图片入口
├── review.py                  # Flask 应用与需要登录的 API
├── render.yaml                # Render 服务配置
├── Procfile                   # Gunicorn 启动入口
├── requirements.txt
├── src/
│   ├── config.py              # 环境变量与路径配置
│   ├── watcher.py             # 截图文件夹监听
│   ├── vision.py              # 视觉分析与复习句生成
│   ├── models.py              # 提取结果数据结构
│   ├── notion_writer.py       # Notion 页面与图片写入
│   ├── notion_reader.py       # Web 应用读取 Notion 卡片
│   ├── matching.py            # 支持词形变化的答案匹配
│   ├── review_log.py          # SQLite 复习记录
│   ├── characters.py          # SQLite 角色资料
│   ├── chat.py                # Scene Talk 生成与 Session
│   └── settings.py            # SQLite 当前作品设置
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
└── data/                      # 运行时 SQLite 文件；数据库已被 gitignore
```

## 本地运行

```bash
git clone https://github.com/yangqing8205/binge-lingo.git
cd binge-lingo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

运行程序前需要配置 `.env`：

| 环境变量 | 用途 |
| --- | --- |
| `API_BASE_URL` | OpenAI-compatible Chat Completions 接口地址 |
| `API_KEY` | 模型服务 API Key |
| `API_MODEL` | 模型名称或 Endpoint ID，必填 |
| `NOTION_TOKEN` | Notion Integration Token |
| `NOTION_DATABASE_ID` | 目标 Notion Database ID |
| `APP_PASSWORD` | Web 应用共享密码，必填 |
| `SECRET_KEY` | Flask Session 签名密钥 |
| `WATCH_DIR` | 截图根目录，默认 `./screenshots` |
| `IMAGE_HOST` | `notion` 或 `imgur` |
| `IMGUR_CLIENT_ID` | 仅使用 Imgur 时需要 |
| `HTTPS_PROXY` | Notion 或图片上传的可选代理 |

Notion 的基础 Schema 需要将 `Expression` 设置为标题字段，并创建 `Chinese`、`Context`、`Difficulty`、`Example` 和 `Screenshot` 富文本字段。缺少时，程序可以自动添加 `ReviewSentence`、`CommonStructure`、`Source`、`Show` 和 `Episode`。

## 使用方法

启动截图监听器：

```bash
python main.py
```

程序会询问当前影视作品和可选集数，然后监听对应文件夹。也可以直接处理单张图片：

```bash
python main.py path/to/screenshot.png
```

本地启动 Web 应用：

```bash
python review.py
# http://127.0.0.1:5001
```

可用页面：

- `/review` — Revision 情境复习
- `/chat` — Scene Talk
- `/export` — Practice to Go

## Render 部署

`render.yaml` 会安装 Python 依赖，并通过 Gunicorn 启动 `review:app`。当前部署有意只使用一个 worker，因为 Scene Talk 的活动 Session 仍存储在进程内存中。模型角色生成继续保留 120 秒超时。

需要在 Render 中配置 `API_BASE_URL`、`API_KEY`、`API_MODEL`、`NOTION_TOKEN`、`NOTION_DATABASE_ID` 和 `APP_PASSWORD`。`render.yaml` 会自动生成稳定的 `SECRET_KEY`。

## 当前限制

- 自动截图流程目前以 macOS 为主。
- 当前是使用共享密码的个人 MVP，不是多租户账号系统。
- 卡片依赖项目所有者的 Notion 数据库。
- 如果 Render 没有挂载持久磁盘，SQLite 数据和当前作品设置属于临时数据。
- Scene Talk Session 会在进程重启后丢失，因此当前只能使用一个 worker。
- Revision 会记录作答情况，但还没有完整的 SRS 调度队列。
- Scene Talk 选择目标表达时，仍会读取全部卡片，而不是只读取当前作品。
- 暂时没有语音输入、发音评分或 TTS。
- Render 免费实例可能出现冷启动，模型请求也可能超时。

当前路线图见 [TODO.md](TODO.md)。

## License

MIT，详见 [LICENSE](LICENSE)。
```

- [x] **Step 4: Run the repository tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_repository_accuracy -v
```

Expected: all repository-accuracy tests pass.

- [x] **Step 5: Commit the bilingual README**

```bash
git add README.md README_CN.md
git commit -m "docs: add Simplified Chinese README"
```

---

### Task 3: Verify and Publish

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-bilingual-readme.md` (checkboxes only)

- [x] **Step 1: Run all Python tests**

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

Expected: all Python tests pass with 0 failures and 0 errors.

- [x] **Step 2: Run all JavaScript tests and static checks**

```bash
node --test tests/api-response.test.js
git diff --check
rg -n -i 'advanced English learners|advanced learners|advanced learner|中高阶' README.md README_CN.md
```

Expected: JavaScript reports 4 passes, `git diff --check` succeeds, and the final `rg` command returns no matches.

- [x] **Step 3: Commit the test contract and completed plan**

Mark completed checkboxes, then run:

```bash
git add tests/test_repository_accuracy.py docs/superpowers/plans/2026-08-10-bilingual-readme.md
git commit -m "test: protect bilingual README positioning"
```

- [x] **Step 4: Push to GitHub**

```bash
git push origin main
```

Expected: GitHub accepts the commits on `main`.

- [x] **Step 5: Verify the published bilingual README files**

```bash
gh api repos/yangqing8205/binge-lingo/readme \
  -H 'Accept: application/vnd.github.raw+json' \
  | rg -n '简体中文|English learners who want to turn expressions from shows'

gh api repos/yangqing8205/binge-lingo/contents/README_CN.md \
  -H 'Accept: application/vnd.github.raw+json' \
  | rg -n 'English|希望把影视中的地道表达真正用起来|当前限制'
```

Expected: both commands return the new reciprocal language links and needs-based positioning.
