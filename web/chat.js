"use strict";

// 对话练习 — pick a character, chat in their voice, get a critique.
const chat = {
  characters: [],
  session: null, // { id, character, color, name, targets }
  currentShow: "",     // read directly from /api/current-show — never inferred
  generating: false,   // a background for-show generation is in flight
  sceneError: "",      // last for-show generation error, shown as a small note
};

const chatEl = {
  charSelect: $("char-select"),
  charGrid: $("char-grid"),
  room: $("chat-room"),
  avatar: $("chat-avatar"),
  name: $("chat-name"),
  back: $("chat-back"),
  targetsToggle: $("targets-toggle"),
  targetsCount: $("targets-count"),
  targetsList: $("targets-list"),
  log: $("chat-log"),
  inputbar: $("chat-inputbar"),
  input: $("chat-input"),
  send: $("chat-send"),
  end: $("chat-end"),
  critique: $("critique"),
  critiqueStamp: $("critique-stamp"),
  critiqueBody: $("critique-body"),
  critiqueAgain: $("critique-again"),
  modal: $("char-modal"),
  newShow: $("new-show"),
  newName: $("new-name"),
  newNote: $("new-note"),
  newErr: $("new-err"),
  newCancel: $("new-cancel"),
  newCreate: $("new-create"),
};

// Loads characters strictly filtered to chat.currentShow when it's set (built-ins
// included only if they belong to that show); unfiltered ("全部剧集") otherwise.
async function loadCharacters() {
  try {
    const qs = chat.currentShow ? "?show=" + encodeURIComponent(chat.currentShow) : "";
    const res = await fetch("/api/characters" + qs);
    const data = await res.json();
    if (!data.ok) return;
    chat.characters = data.characters || [];
    renderCharGrid();
  } catch (_) {
    /* leave grid empty */
  }
}

// Read current_show directly (never inferred from Notion Source — that guessing
// logic was the root cause of past mis-tagging bugs). The for-show endpoint is
// idempotent and top-up aware (see review.py), so it's safe to call every time
// — it's a no-op once the show already has a full cast.
async function prepareSceneCharacter() {
  try {
    const res = await fetch("/api/current-show");
    const data = await res.json();
    chat.currentShow = (data && data.ok && data.show) || "";
  } catch (_) {
    chat.currentShow = "";
  }
  if (!chat.currentShow) {
    await loadCharacters(); // "全部剧集" — unfiltered grid, no auto-generation
    return;
  }

  await loadCharacters(); // re-filter the grid to this show

  chat.generating = true;
  renderCharGrid();
  try {
    const res = await fetch("/api/characters/for-show", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show: chat.currentShow }),
    });
    const data = await res.json();
    chat.generating = false;
    if (data.ok) {
      chat.sceneError = "";
      if (data.created && data.created.length) {
        await loadCharacters(); // pull the newly generated cast into the list
      } else {
        renderCharGrid();
      }
    } else {
      chat.sceneError = data.error || "生成失败";
      renderCharGrid();
    }
  } catch (err) {
    chat.generating = false;
    chat.sceneError = err.message || "网络错误";
    renderCharGrid();
  }
}

function makeCharCard(c) {
  const card = document.createElement("button");
  card.className = "char-card" + (c.hidden ? " hidden-char" : "");
  card.innerHTML =
    '<span class="char-avatar" style="background:' + esc(c.color) + '">' +
    esc(initials(c.name)) +
    '</span><span class="char-text">' +
    '<span class="char-cardname">' + esc(c.name) +
    '</span><span class="char-intro">' + esc(c.intro) +
    "</span></span>";
  card.addEventListener("click", () => startChat(c));
  // Custom characters get a delete button; built-ins can't be removed.
  if (!c.is_builtin) {
    const del = document.createElement("span");
    del.className = "char-del";
    del.textContent = "×";
    del.title = "删除角色";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteCharacter(c);
    });
    card.appendChild(del);
  }
  return card;
}

function renderCharGrid() {
  chatEl.charGrid.innerHTML = "";

  // While a for-show cast is being generated/topped-up, show a loading
  // placeholder at the front — the rest of the list stays usable underneath.
  if (chat.generating) {
    const ph = document.createElement("div");
    ph.className = "char-card char-card--loading";
    ph.innerHTML =
      '<span class="char-avatar char-avatar--loading">…</span>' +
      '<span class="char-text">' +
      '<span class="char-cardname">正在准备角色…</span>' +
      '<span class="char-intro">根据你在看的剧自动生成，稍等片刻</span></span>';
    chatEl.charGrid.appendChild(ph);
  }

  // If auto-generation failed, say so quietly — built-ins are still usable.
  if (chat.sceneError && !chat.generating) {
    const note = document.createElement("div");
    note.className = "scene-error";
    note.textContent =
      "《" + chat.currentShow + "》的角色自动生成失败：" + chat.sceneError +
      "（可先用下面的角色，或点“+ 新建角色”重试）";
    chatEl.charGrid.appendChild(note);
  }

  chat.characters.forEach((c) => chatEl.charGrid.appendChild(makeCharCard(c)));

  // Trailing "+ 新建角色" card (manually add a character to the current show).
  const add = document.createElement("button");
  add.className = "char-card char-card--add";
  add.innerHTML =
    '<span class="char-avatar char-avatar--add">+</span>' +
    '<span class="char-text"><span class="char-cardname">新建角色</span>' +
    '<span class="char-intro">想加入新人物？手动加一个</span></span>';
  add.addEventListener("click", openCharModal);
  chatEl.charGrid.appendChild(add);
}

function openCharModal() {
  chatEl.newShow.value = "";
  chatEl.newName.value = "";
  chatEl.newNote.value = "";
  chatEl.newErr.hidden = true;
  chatEl.newErr.textContent = "";
  chatEl.newCreate.disabled = false;
  chatEl.newCreate.textContent = "生成角色";
  chatEl.modal.hidden = false;
  chatEl.newShow.focus();
}

function closeCharModal() {
  chatEl.modal.hidden = true;
}

async function createCharacter() {
  const show = chatEl.newShow.value.trim();
  const character = chatEl.newName.value.trim();
  const note = chatEl.newNote.value.trim();
  if (!show || !character) {
    chatEl.newErr.hidden = false;
    chatEl.newErr.textContent = "剧名和角色名都要填。";
    return;
  }
  chatEl.newErr.hidden = true;
  chatEl.newCreate.disabled = true;
  chatEl.newCreate.textContent = "生成中…（约十几秒）";
  try {
    const res = await fetch("/api/characters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show, character, note }),
    });
    const data = await res.json();
    if (!data.ok) {
      chatEl.newErr.hidden = false;
      chatEl.newErr.textContent = "生成失败：" + (data.error || "未知错误");
      chatEl.newCreate.disabled = false;
      chatEl.newCreate.textContent = "生成角色";
      return;
    }
    closeCharModal();
    await loadCharacters();
    // Jump straight into a chat with the freshly made character.
    startChat(data.character);
  } catch (err) {
    chatEl.newErr.hidden = false;
    chatEl.newErr.textContent = "无法连接：" + err.message;
    chatEl.newCreate.disabled = false;
    chatEl.newCreate.textContent = "生成角色";
  }
}

async function deleteCharacter(c) {
  if (!confirm("删除角色「" + c.name + "」？")) return;
  try {
    const res = await fetch("/api/characters/" + encodeURIComponent(c.key), {
      method: "DELETE",
    });
    const data = await res.json();
    if (!data.ok) {
      alert("删除失败：" + (data.error || "未知错误"));
      return;
    }
    await loadCharacters();
  } catch (err) {
    alert("无法连接：" + err.message);
  }
}

// Renders text as safe HTML: escape everything first, then re-enable ONLY
// **bold** (the one markup characters are allowed to use per format_style).
// Never build this from raw string concatenation of untrusted input — esc()
// runs first, so anything the model wrote lands as inert text, and only the
// **...** delimiters we insert ourselves become <strong> tags.
function formatBubbleHtml(text) {
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function bubble(role, text) {
  const b = document.createElement("div");
  b.className = "bubble " + (role === "ai" ? "ai" : "me");
  if (role === "ai") {
    b.innerHTML = formatBubbleHtml(text);
  } else {
    b.textContent = text; // learner's own input is never treated as markup
  }
  chatEl.log.appendChild(b);
  chatEl.log.scrollTop = chatEl.log.scrollHeight;
  return b;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Renders an ordered [{text, pause_before_ms}] reply as separate AI bubbles,
// pausing before each one that asks for it. Caps the pause so a bad/huge
// value from the model can't stall the UI for an absurd amount of time.
const MAX_PAUSE_MS = 3000;

async function showReplyMessages(messages) {
  for (const m of messages || []) {
    const pause = Math.min(Math.max(0, Number(m.pause_before_ms) || 0), MAX_PAUSE_MS);
    if (pause > 0) {
      const t = typingBubble();
      await sleep(pause);
      t.remove();
    }
    bubble("ai", m.text || "");
  }
}

function typingBubble() {
  const b = document.createElement("div");
  b.className = "bubble ai typing";
  b.textContent = "…";
  chatEl.log.appendChild(b);
  chatEl.log.scrollTop = chatEl.log.scrollHeight;
  return b;
}

function renderTargets() {
  const t = chat.session.targets || [];
  chatEl.targetsCount.textContent = "(" + t.length + ")";
  chatEl.targetsList.innerHTML = "";
  t.forEach((x) => {
    const chip = document.createElement("span");
    chip.className = "target-chip";
    chip.textContent = x;
    chip.dataset.expr = x;
    chatEl.targetsList.appendChild(chip);
  });
}

async function startChat(c) {
  chatEl.charSelect.hidden = true;
  chatEl.room.hidden = false;
  chatEl.critique.hidden = true;
  chatEl.log.innerHTML = "";
  chatEl.inputbar.hidden = false;
  chatEl.end.hidden = false;
  chatEl.avatar.style.background = c.color;
  chatEl.avatar.textContent = initials(c.name);
  chatEl.name.textContent = c.name;
  chatEl.room.style.setProperty("--ai-tint", tint(c.color, 0.1));
  chatEl.room.style.setProperty("--ai-line", tint(c.color, 0.28));

  const t = typingBubble();
  try {
    const res = await fetch("/api/chat/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character: c.key }),
    });
    const data = await res.json();
    t.remove();
    if (!data.ok) {
      bubble("ai", "开场失败：" + (data.error || "未知错误"));
      return;
    }
    chat.session = { id: data.session_id, character: c.key, color: c.color, name: c.name, targets: data.targets };
    renderTargets();
    await showReplyMessages(data.messages);
    chatEl.input.focus();
  } catch (err) {
    t.remove();
    bubble("ai", "无法连接：" + err.message);
  }
}

async function sendChat() {
  if (!chat.session) return;
  const msg = chatEl.input.value.trim();
  if (!msg) return;
  bubble("me", msg);
  chatEl.input.value = "";
  const t = typingBubble();
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: chat.session.id, message: msg }),
    });
    const data = await res.json();
    t.remove();
    if (!data.ok) {
      bubble("ai", "出错了：" + (data.error || "未知错误"));
      return;
    }
    await showReplyMessages(data.messages);
    markUsedTargets();
    if (data.suggest_end) {
      const hint = document.createElement("div");
      hint.className = "bubble ai typing";
      hint.textContent = "（聊得差不多啦，随时可以点“结束对话，看点评”）";
      chatEl.log.appendChild(hint);
      chatEl.log.scrollTop = chatEl.log.scrollHeight;
    }
  } catch (err) {
    t.remove();
    bubble("ai", "无法连接：" + err.message);
  }
}

function markUsedTargets() {
  const said = Array.from(chatEl.log.querySelectorAll(".bubble.me"))
    .map((b) => b.textContent.toLowerCase().replace(/-/g, " "))
    .join(" ");
  chatEl.targetsList.querySelectorAll(".target-chip").forEach((chip) => {
    const e = chip.dataset.expr.toLowerCase().replace(/-/g, " ");
    if (said.includes(e)) chip.classList.add("done");
  });
}

async function endChat() {
  if (!chat.session) return;
  chatEl.inputbar.hidden = true;
  chatEl.end.hidden = true;
  const t = typingBubble();
  try {
    const res = await fetch("/api/chat/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: chat.session.id }),
    });
    const data = await res.json();
    t.remove();
    if (!data.ok) {
      bubble("ai", "点评失败：" + (data.error || "未知错误"));
      return;
    }
    chatEl.critiqueStamp.textContent = data.used_count + " / " + data.total + " USED";
    chatEl.critiqueBody.textContent = data.critique;
    chatEl.critique.hidden = false;
    chatEl.critique.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    t.remove();
    bubble("ai", "无法连接：" + err.message);
  }
}

function backToChars() {
  chat.session = null;
  chatEl.room.hidden = true;
  chatEl.critique.hidden = true;
  chatEl.charSelect.hidden = false;
}

function wireChat() {
  chatEl.send.addEventListener("click", sendChat);
  chatEl.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); sendChat(); }
  });
  chatEl.end.addEventListener("click", endChat);
  chatEl.back.addEventListener("click", backToChars);
  chatEl.critiqueAgain.addEventListener("click", backToChars);
  chatEl.targetsToggle.addEventListener("click", () => {
    chatEl.targetsList.hidden = !chatEl.targetsList.hidden;
  });
  chatEl.newCancel.addEventListener("click", closeCharModal);
  chatEl.newCreate.addEventListener("click", createCharacter);
  chatEl.modal.addEventListener("click", (e) => {
    if (e.target === chatEl.modal) closeCharModal(); // click backdrop to dismiss
  });
  chatEl.newNote.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); createCharacter(); }
  });
}

wireChat();
// Read current_show, then load the (possibly filtered) grid, then make sure a
// full cast exists for the current show — topping it up in the background if not.
prepareSceneCharacter();
// Switcher stays put and updates its own label; only the content area reloads.
document.addEventListener("bl:show-changed", () => {
  backToChars();
  prepareSceneCharacter();
});
