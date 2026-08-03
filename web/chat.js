"use strict";

// 对话练习 — pick a character, chat in their voice, get a critique.
const chat = {
  characters: [],
  session: null, // { id, character, color, name, targets }
  currentShow: "",     // show inferred from Notion Source (from /api/scene-context)
  matchedKey: null,    // key of the character matching currentShow, if any
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

async function loadCharacters() {
  try {
    const res = await fetch("/api/characters");
    const data = await res.json();
    if (!data.ok) return;
    chat.characters = data.characters || [];
    renderCharGrid();
  } catch (_) {
    /* leave grid empty */
  }
}

// After the grid loads, figure out what shows the learner has been watching
// (from their Notion Source) and make sure each has a character ready. The
// newest show's character is surfaced first with a badge; any missing ones are
// generated in the background without blocking the rest of the list.
async function prepareSceneCharacter() {
  let ctx;
  try {
    const res = await fetch("/api/scene-context");
    ctx = await res.json();
  } catch (_) {
    return; // best-effort; the built-ins are always available as fallback
  }
  if (!ctx || !ctx.ok) return;
  const shows = ctx.shows && ctx.shows.length ? ctx.shows : (ctx.show ? [ctx.show] : []);
  if (!shows.length) return;

  chat.currentShow = shows[0]; // newest show — the one we badge and surface
  if (ctx.matched) chat.matchedKey = ctx.matched.key;
  renderCharGrid();

  // Ensure a character exists for every recent show. The primary (newest) one
  // is generated first so it can be surfaced; the rest just get prepared for
  // next time. for-show is idempotent, so an already-matched show is a no-op.
  for (const show of shows) {
    const isPrimary = show === chat.currentShow;
    if (isPrimary && chat.matchedKey) continue; // already have the badged one

    if (isPrimary) { chat.generating = true; renderCharGrid(); }
    try {
      const res = await fetch("/api/characters/for-show", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show }),
      });
      const data = await res.json();
      if (isPrimary) chat.generating = false;
      if (data.ok && data.character) {
        await loadCharacters(); // pull the new/reused character into the list
        if (isPrimary) { chat.sceneError = ""; chat.matchedKey = data.character.key; }
        renderCharGrid();
      } else if (isPrimary) {
        // Surface why the badged show failed; built-ins stay usable. Server logs
        // the full reason. Non-primary failures stay quiet — they're prep only.
        chat.sceneError = data.error || "生成失败";
        renderCharGrid();
      }
    } catch (err) {
      if (isPrimary) {
        chat.generating = false;
        chat.sceneError = err.message || "网络错误";
        renderCharGrid();
      }
    }
  }
}

function makeCharCard(c, matched) {
  const card = document.createElement("button");
  card.className = "char-card" + (c.hidden ? " hidden-char" : "") +
    (matched ? " char-card--matched" : "");
  const badge = matched
    ? '<span class="char-badge">来自你在看的《' + esc(chat.currentShow) + "》</span>"
    : "";
  card.innerHTML =
    '<span class="char-avatar" style="background:' + esc(c.color) + '">' +
    esc(initials(c.name)) +
    '</span><span class="char-text">' + badge +
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

  // Matched character (for the show being watched) leads the grid, then the
  // rest in their normal order.
  const list = chat.characters.slice();
  let matched = null;
  if (chat.matchedKey) {
    const i = list.findIndex((c) => c.key === chat.matchedKey);
    if (i !== -1) matched = list.splice(i, 1)[0];
  }
  if (matched) chatEl.charGrid.appendChild(makeCharCard(matched, true));

  // While a for-show character is being generated, show a loading placeholder
  // at the front — the rest of the list stays usable underneath.
  if (chat.generating) {
    const ph = document.createElement("div");
    ph.className = "char-card char-card--loading";
    ph.innerHTML =
      '<span class="char-avatar char-avatar--loading">…</span>' +
      '<span class="char-text"><span class="char-badge">来自你在看的《' +
      esc(chat.currentShow) + "》</span>" +
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

  list.forEach((c) => chatEl.charGrid.appendChild(makeCharCard(c, false)));

  // Trailing "+ 新建角色" card (secondary entry for adding other shows).
  const add = document.createElement("button");
  add.className = "char-card char-card--add";
  add.innerHTML =
    '<span class="char-avatar char-avatar--add">+</span>' +
    '<span class="char-text"><span class="char-cardname">新建角色</span>' +
    '<span class="char-intro">想练别的剧？手动加一个</span></span>';
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

function bubble(role, text) {
  const b = document.createElement("div");
  b.className = "bubble " + (role === "ai" ? "ai" : "me");
  b.textContent = text;
  chatEl.log.appendChild(b);
  chatEl.log.scrollTop = chatEl.log.scrollHeight;
  return b;
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
    bubble("ai", data.reply);
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
    bubble("ai", data.reply);
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
// Load the grid first (built-ins show immediately), then prepare the
// show-matched character — surfaced first, or generated in the background.
loadCharacters().then(prepareSceneCharacter);
