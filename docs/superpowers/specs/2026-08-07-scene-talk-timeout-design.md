# Scene Talk 角色生成超时修复设计

## 问题

线上 `POST /api/characters/for-show` 一次生成约六个角色及完整 persona。
实测《Breaking Bad》请求耗时 121.12 秒，超过 Gunicorn 的 120 秒
worker timeout。Gunicorn 随后返回 HTML 500，前端无条件调用
`response.json()`，最终只显示 `Unexpected token '<'`。

Ark 鉴权已经正常；当前故障不是 API Key 或 tool-call 字段不兼容。

## 目标

- 首次进入 Scene Talk 时，在 Gunicorn 超时前得到可用角色或明确的 JSON 错误。
- 保留按剧集逐步补齐约六个角色的体验。
- 前端不再把 HTML、空响应或非 JSON 响应显示为 `Unexpected…`。
- 不提高 Gunicorn timeout 来掩盖慢请求。
- 删除已经完成使命、会泄露 API Key 元数据的临时诊断接口。

## 方案

### 后端生成策略

每次 `/api/characters/for-show` 最多生成三个新角色，而不是一次生成完整六人组。
现有 `_CAST_TARGET = 6` 保持不变；后续再次进入页面时，接口根据已有数量继续补齐。
提示词明确传入本次所需数量，输出 token 上限也随之降低。

Ark 客户端为角色生成设置小于 Gunicorn 120 秒的请求超时，并关闭 SDK 自动重试。
这样上游过慢时 Flask 仍有时间捕获异常并返回 JSON 504，而不是被 Gunicorn 杀死。
普通 Scene Talk 对话行为不改变。

### API 错误处理

将上游超时映射为稳定、面向用户的 JSON 错误，例如：

```json
{"ok": false, "error": "角色生成超时，请稍后重试。"}
```

其他 Ark/解析异常继续记录完整 traceback，并返回 JSON 错误。

### 前端响应处理

增加一个小型响应解析函数：先读取文本，再依据 content type/内容尝试 JSON 解析。
若响应为 HTML、空内容或无效 JSON，则结合 HTTP 状态生成可读错误，避免暴露
`Unexpected token`。角色自动生成、手动创建和聊天接口复用该函数。

### 安全清理

删除 `/api/debug/ark-key`。该接口虽然需要登录，但会返回 key 长度及首尾字符，故障
定位完成后不应继续在线上保留。

## 测试

- 后端测试：单次 top-up 请求数量最多为三，并正确计算剩余数量。
- 后端测试：上游超时返回 JSON 504，而不是 HTML 500。
- 前端测试：JSON 错误正常显示；HTML 500、空响应和无效 JSON 转换为可读错误。
- 回归测试：合法 Ark tool-call 响应仍可保存角色；已有六个角色时不调用模型。
- 部署后验证：线上《Breaking Bad》首次请求在 120 秒内返回，角色列表可用；刷新后可继续补齐。
