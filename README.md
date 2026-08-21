# BingeLingo｜把"看懂了"变成"说得出来"

BingeLingo 是一个围绕影视英语学习设计的 AI 产品。

它从一个很常见的学习习惯开始：

**看剧时遇到一句很地道的表达，截图、查意思、觉得自己记住了——但下一次真正想说的时候，还是想不起来。**

BingeLingo 想解决的，正是从"我见过这个表达"到"我能够主动使用它"之间的距离。

它把原本分散的几个动作连接成一条学习闭环：

**截图捕捉 → AI 提取表达 → 情境回忆 → 角色对话 → 主动使用**

## 在线体验

👉 `https://binge-lingo.onrender.com/`

> Render 免费实例可能存在冷启动，首次打开时需要稍等片刻。

## 为什么做 BingeLingo

看英文剧时，我们经常会遇到一些特别想记住的表达：

一个俚语、一个短语动词、一种很自然的搭配，或者一句角色说出来特别有语气的表达。

最常见的做法是截图。

然后查一下意思，可能顺手问问 AI，再把截图留在相册里。

问题是，这套流程很容易停在"收藏"。

截图越来越多，AI 的解释沉进聊天记录里，真正说英语时，却还是只能认出来，想不起来。

我发现真正缺少的不是更多解释，而是：

**让一个表达在不同情境里被反复主动调取。**

于是 BingeLingo 把一次字幕截图，变成了一条完整的学习路径。

## 从截图到主动使用

### 01｜Capture：先把值得学的表达留下来

用户截下字幕画面后，AI 会识别其中值得学习的表达，例如：

* idiom
* phrasal verb
* collocation
* slang
* 带有明显语气和使用场景的口语表达

系统不仅保存释义，还会记录原句、上下文、剧集信息和截图本身。

这样，表达不会脱离它第一次出现的真实语境。

### 02｜Revision：不是"再看一遍"，而是尝试回忆

传统单词卡常常先展示答案。

BingeLingo 的复习从新的对话情境开始，让用户先尝试主动想起原表达。

如果想不起来，再逐步提供：

**语义提示 → 首字母提示 → 完整答案与原始语境**

核心不是判断"认识不认识"，而是训练：

**在需要表达一个意思的时候，能不能把它从记忆里调出来。**

### 03｜Scene Talk：把表达放回真实对话

记住一个表达并不意味着会用。

因此 BingeLingo 会基于影视角色生成短对话，让用户在角色互动中寻找自然使用目标表达的机会。

角色不会直接告诉用户"现在请使用某个词组"，而是创造一个适合它出现的情境。

学习从：

**"这句话是什么意思？"**

进一步变成：

**"在什么情况下，我会自然地说出这句话？"**

### 04｜Practice to Go：把练习带到任何 AI 对话里

BingeLingo 还可以把：

* 角色
* 目标表达
* 对话长度
* 提示强度
* 场景
* 纠错方式

组合成一段可直接使用的 Prompt。

用户可以把它带到 ChatGPT、Claude、Kimi、豆包等 AI 对话工具中继续练习。

## BingeLingo 的核心学习闭环

**Capture → Recall → Use**

不是收集更多表达，而是让表达经历三次变化：

**看到它 → 想起它 → 用出来**

这是 BingeLingo 最核心的产品假设：

> 一个表达真正进入主动词汇，不是在用户第一次理解它的时候，而是在不同语境里成功把它调出来的时候。

## 我负责的工作

这个项目从产品概念到可运行 MVP 均由我独立完成，包括：

* 英语学习场景与核心问题定义
* 从截图收藏到主动输出的学习闭环设计
* 多模态字幕识别与表达筛选逻辑
* 情境回忆与渐进式提示机制
* 影视角色对话练习设计
* 可迁移 AI Prompt 的生成逻辑
* Notion 知识卡结构设计
* 模型结构化输出与异常恢复
* Flask Web 应用与前端交互实现
* SQLite 本地学习记录设计
* Render 部署与线上 Demo

## AI 在这里做什么

BingeLingo 并不是简单地让 AI "解释一句英文"。

AI 主要承担三个角色：

### 从画面中理解表达

通过多模态模型读取字幕截图，并从中筛选真正值得主动学习的表达。

### 为表达生成新的回忆情境

复习时不直接重复原句，而是生成新的自然语境，让用户重新调取同一个表达。

### 创造可使用表达的对话机会

Scene Talk 根据目标表达与角色设定生成对话，让用户在语境中完成主动输出。

这使 AI 不只是"答案生成器"，而成为学习过程中的**情境生成器**。

## 产品流程

**字幕截图**

↓

**多模态识别值得学习的表达**

↓

**保存释义、上下文、原句和截图**

↓

**在新情境中进行主动回忆**

↓

**通过角色对话练习真实使用**

↓

**将练习 Prompt 带到其他 AI 对话工具**

## 技术实现

### Tech Stack

* Python 3.11
* Flask / Gunicorn
* OpenAI Python SDK
* OpenAI-compatible multimodal model
* Notion API
* SQLite
* HTML / CSS / Vanilla JavaScript
* watchdog
* Render

### Architecture

```text
macOS screenshot folder
        │
        ▼
watchdog → vision model
        │
        ▼
structured expression extraction
        │
        ▼
Notion knowledge cards
        │
        ├── Revision → SQLite review history
        │
        ├── Scene Talk → character sessions
        │
        └── Practice to Go → portable prompt
```

## 工程实现亮点

* 多模态字幕截图解析
* Structured Tool Calling，避免依赖自由文本解析
* 表达词形归一化与筛选
* Tool arguments 异常恢复
* 支持词形变化的答案匹配
* API 错误统一处理
* 模型与 Provider 通过环境变量配置
* 小型 Demo 的共享密码访问机制

## 本地运行

```bash
git clone https://github.com/yangqing8205/binge-lingo.git
cd binge-lingo

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

配置 `.env` 后：

```bash
python main.py
```

启动 Web 应用：

```bash
python review.py
```

本地访问：

```text
http://127.0.0.1:5001
```

## 当前限制

当前版本仍是个人 MVP：

* 自动截图流程目前以 macOS 为主
* 尚未实现完整 SRS 调度
* Scene Talk session 暂存在进程内存中
* Render 免费实例可能存在冷启动
* 暂无语音输入、发音评分和 TTS
* 当前不是多人账户系统
* 部分状态依赖 SQLite 与本地文件

详细路线图见 `TODO.md`。

## License

MIT
