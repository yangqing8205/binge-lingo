"use strict";

// 对话练习 — pick a character, chat in their voice, get a critique.
const chat = {
  characters: [],
  session: null, // { id, character, color, name, targets }
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

function renderCharGrid() {
  chatEl.charGrid.innerHTML = "";
  chat.characters.forEach((c) => {
    const card = document.createElement("button");
    card.className = "char-card" + (c.hidden ? " hidden-char" : "");
    card.innerHTML =
      '<span class="char-avatar" style="background:' + esc(c.color) + '">' +
      esc(initials(c.name)) +
      '</span><span class="char-text"><span class="char-cardname">' +
      esc(c.name) +
      '</span><span class="char-intro">' +
      esc(c.intro) +
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
    chatEl.charGrid.appendChild(card);
  });

  // Trailing "+ 新建角色" card.
  const add = document.createElement("button");
  add.className = "char-card char-card--add";
  add.innerHTML =
    '<span class="char-avatar char-avatar--add">+</span>' +
    '<span class="char-text"><span class="char-cardname">新建角色</span>' +
    '<span class="char-intro">用剧名和角色名生成一个</span></span>';
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
loadCharacters();
