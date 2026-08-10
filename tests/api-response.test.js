"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { readApiResponse } = require("../web/api-response.js");

function response(status, body, contentType = "") {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => name.toLowerCase() === "content-type" ? contentType : null },
    text: async () => body,
  };
}

test("returns valid JSON responses unchanged", async () => {
  const data = await readApiResponse(
    response(200, '{"ok":true,"characters":[]}', "application/json")
  );
  assert.deepEqual(data, { ok: true, characters: [] });
});

test("preserves JSON API error messages", async () => {
  const data = await readApiResponse(
    response(502, '{"ok":false,"error":"Ark rejected the request"}', "application/json")
  );
  assert.deepEqual(data, { ok: false, error: "Ark rejected the request" });
});

test("turns an HTML 500 page into a readable error", async () => {
  const data = await readApiResponse(
    response(500, "<html><h1>Internal Server Error</h1></html>", "text/html")
  );
  assert.deepEqual(data, {
    ok: false,
    error: "服务端暂时不可用（HTTP 500），请稍后重试。",
  });
});

test("turns an empty 504 response into a timeout error", async () => {
  const data = await readApiResponse(response(504, ""));
  assert.deepEqual(data, {
    ok: false,
    error: "请求超时（HTTP 504），请稍后重试。",
  });
});
