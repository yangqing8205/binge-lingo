# BingeLingo — Roadmap / TODO

接下来要完善的功能，按优先级排列。方便开新对话直接从这里接着做。

## 1. 提取质量（优先，先做这个）

把 `src/vision.py` 的 prompt 筛选标准改成：

> 只提取中低频（mid-to-low frequency）、有实际语义的地道表达——包括 idioms、
> phrasal verbs、collocations、slang。排除所有高频词、功能词、感叹词和填充词
> （如 huh、oh、um、well、you know）。判断标准：一个受过良好教育的英语学习者
> 是否"看得懂但自己主动表达时想不到用它"。

**具体验收案例：**
- 字幕 `"Oh, she's a bummer, huh?"` → 应只提取 `bummer`，不要提取 `huh?`。

## 2. 复习闭环（第二期核心）

- Notion 遮挡式复习：先看英文 + 剧照，点开才看中文。
- 导出 Anki 卡片，用间隔重复（SRS）对抗遗忘。
- 支持填空、看图提示、重现截图做场景唤醒。

## 3. 产品健壮性

- 失败重试、日志、错误提示。

## 4. 离职迁移（重要）

- 当前用公司网关 `model.zhenguanyu.com`，离职后 `sk-mg` key 会失效。
- 试通非公司模型供应商（如通义千问 VL，国内直连），确认可行。
- 代码已配置外置：只需改 `.env` 的 `API_BASE_URL` 和 `API_KEY`，无需改代码。

---

## 已完成（第一期 MVP）

- 快捷键 `Ctrl+Shift+L` 截图 → 多模态模型提取地道表达 → 写入 Notion
  （配图 / 释义 / 语境 / 例句）。
- 隐私可控，不常驻后台（手动启动 / 停止）。
- 已推送 github.com/yangqing8205/binge-lingo。
