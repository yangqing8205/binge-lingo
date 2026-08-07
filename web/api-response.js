"use strict";

(function exposeApiResponse(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.readApiResponse = api.readApiResponse;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildApiResponse() {
  async function readApiResponse(response) {
    let body = "";
    try {
      body = await response.text();
    } catch (_) {
      return { ok: false, error: "无法读取服务端响应，请稍后重试。" };
    }

    if (body.trim()) {
      try {
        const parsed = JSON.parse(body);
        if (parsed && typeof parsed === "object") return parsed;
      } catch (_) {
        // Render/Gunicorn may return an HTML error page. Convert it below.
      }
    }

    if (response.status === 504) {
      return { ok: false, error: "请求超时（HTTP 504），请稍后重试。" };
    }
    if (response.status >= 500) {
      return {
        ok: false,
        error: "服务端暂时不可用（HTTP " + response.status + "），请稍后重试。",
      };
    }
    return {
      ok: false,
      error: "服务端返回了无法识别的数据（HTTP " + response.status + "）。",
    };
  }

  return { readApiResponse };
});
