"use strict";

// Three-layer progressive review over a TV-archive UI.
//   layer 1 — new-context mini-scenario, no hints, type the answer
//   layer 2 — after a miss: Chinese meaning + first-letter hint, retry
//   layer 3 — after a second miss (or skip): full "original evidence" reveal
// A correct answer stamps COLD RECALL (layer 1) or RECALLED WITH A HINT (layer 2)
// and reveals; running out stamps REVEALED.
const state = {
  cards: [],
  i: 0,
  layer: 1,
  revealed: false,
  outcome: null, // "cold" | "hint" | "revealed"
};

const $ = (id) => document.getElementById(id);
const el = {
  notice: $("notice"),
  card: $("card"),
  nav: $("nav"),
  counter: $("counter"),
  streak: $("streak"),
  episodeLine: $("episode-line"),
  filetab: $("filetab"),
  difficulty: $("difficulty"),
  prompt: $("prompt"),
  hintblock: $("hintblock"),
  hintMeaning: $("hint-meaning"),
  hintInitials: $("hint-initials"),
  nudge: $("nudge"),
  answerbar: $("answerbar"),
  guessInput: $("guess-input"),
  guessSubmit: $("guess-submit"),
  skip: $("skip"),
  stampSlot: $("stamp-slot"),
  stamp: $("stamp"),
  stampNote: $("stamp-note"),
  evidence: $("evidence"),
  photo: $("photo"),
  shotImg: $("shot-img"),
  photoCaption: $("photo-caption"),
  evLine: $("ev-line"),
  evAnswer: $("ev-answer"),
  evCn: $("ev-cn"),
  evContext: $("ev-context"),
  evStructure: $("ev-structure"),
  prev: $("prev"),
  next: $("next"),
  pips: $("pips"),
};

const STAMPS = {
  cold: { cls: "gold", text: "COLD RECALL ✓", note: "You recognized it in a brand new context." },
  hint: { cls: "", text: "RECALLED WITH A HINT", note: "You got it with a little help." },
  revealed: { cls: "wine", text: "REVEALED", note: "Review this one again soon." },
};

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function showNotice(msg, isError) {
  el.notice.hidden = false;
  el.notice.textContent = msg;
  el.notice.classList.toggle("error", !!isError);
  el.card.hidden = true;
  el.nav.hidden = true;
}

// ----- daily streak (local only) -----
function updateStreak() {
  const today = new Date().toISOString().slice(0, 10);
  let day = 1;
  try {
    const last = localStorage.getItem("bl_last_day");
    const count = Number(localStorage.getItem("bl_streak") || "0");
    if (last === today) {
      day = count || 1;
    } else {
      const y = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      day = last === y ? count + 1 : 1;
      localStorage.setItem("bl_last_day", today);
      localStorage.setItem("bl_streak", String(day));
    }
  } catch (_) {
    day = 1;
  }
  el.streak.textContent = "DAY " + day;
}

function episodeText() {
  const n = state.cards.length;
  const src = (state.cards[state.i] && state.cards[state.i].source || "").trim();
  if (src) return src + " · " + n + " expressions due today";
  return "REVIEW SESSION · " + n + " expressions";
}

function clozeHTML(text) {
  return esc(text).replace(/＿＿＿/g, '<span class="blank">＿＿＿</span>');
}

function renderPrompt(card) {
  if (card.review_kind === "cloze" && card.review_prompt) {
    el.prompt.innerHTML = clozeHTML(card.review_prompt);
  } else {
    el.prompt.innerHTML =
      '<span class="zh">' + esc(card.chinese || card.expression) + "</span>";
  }
}

function setPips() {
  el.pips.querySelectorAll(".pip").forEach((p) => {
    p.classList.toggle("is-on", Number(p.dataset.layer) <= state.layer);
  });
}

function renderEvidence(card) {
  if (card.image_url) {
    el.shotImg.src = card.image_url;
    el.photo.hidden = false;
    const cap = [card.source, card.difficulty].filter(Boolean).join("  ·  ");
    el.photoCaption.textContent = cap || "FROM YOUR ARCHIVES";
  } else {
    el.shotImg.removeAttribute("src");
    el.photo.hidden = true;
  }
  el.evLine.textContent = card.example || "";
  el.evAnswer.textContent = card.expression || "";
  el.evCn.textContent = card.chinese || "";
  el.evContext.textContent = card.context || "";
  el.evStructure.textContent = card.common_structure
    ? "常见结构：" + card.common_structure
    : "";
}

function render() {
  const card = state.cards[state.i];
  if (!card) return;

  el.difficulty.textContent = card.difficulty || "";
  el.episodeLine.textContent = episodeText();
  renderPrompt(card);
  setPips();

  // file tab label reflects the layer
  el.filetab.textContent =
    state.layer === 1 ? "TRANSFER TEST" : state.layer === 2 ? "HINT ROUND" : "CASE FILE";

  const showHints = state.layer >= 2 && !state.revealed;
  el.hintblock.hidden = !showHints;
  if (showHints) {
    el.hintMeaning.textContent = card.chinese || "（暂无中文释义）";
    el.hintInitials.textContent = card.initials_hint || "";
  }

  const showGuess = !state.revealed && state.layer <= 2;
  el.answerbar.hidden = !showGuess;
  el.skip.hidden = !showGuess;
  el.skip.textContent = state.layer >= 2 ? "我放弃了（看答案）" : "跳过（直接看答案）";
  if (showGuess) el.guessInput.focus();

  // stamp + evidence only after reveal
  el.stampSlot.hidden = !state.revealed;
  el.evidence.hidden = !state.revealed;
  if (state.revealed) {
    const s = STAMPS[state.outcome] || STAMPS.revealed;
    el.stamp.className = "stamp " + s.cls;
    el.stamp.textContent = s.text;
    el.stampNote.textContent = s.note;
    renderEvidence(card);
  }

  el.counter.textContent = state.i + 1 + " / " + state.cards.length;
  el.prev.disabled = state.i === 0;
  el.next.disabled = state.i === state.cards.length - 1;
}

function resetCard() {
  state.layer = 1;
  state.revealed = false;
  state.outcome = null;
  el.guessInput.value = "";
  el.nudge.hidden = true;
  el.nudge.textContent = "";
}

function revealWith(outcome) {
  state.revealed = true;
  state.outcome = outcome;
  render();
}

async function judge(guess, expression) {
  const res = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guess, expression }),
  });
  const data = await res.json();
  return !!data.correct;
}

async function submitGuess() {
  const card = state.cards[state.i];
  if (!card || state.revealed) return;
  const raw = el.guessInput.value;
  if (!raw.trim()) return;

  let correct = false;
  try {
    correct = await judge(raw, card.expression);
  } catch (err) {
    el.nudge.hidden = false;
    el.nudge.textContent = "判分服务连接失败：" + err.message;
    return;
  }

  if (correct) {
    revealWith(state.layer >= 2 ? "hint" : "cold");
    return;
  }

  if (state.layer === 1) {
    state.layer = 2;
    el.nudge.hidden = false;
    el.nudge.textContent = "Not quite — try again?";
    el.guessInput.value = "";
    render();
  } else {
    revealWith("revealed");
  }
}

function skip() {
  if (state.revealed) return;
  revealWith("revealed");
}

function go(delta) {
  const n = state.i + delta;
  if (n < 0 || n >= state.cards.length) return;
  state.i = n;
  resetCard();
  render();
}

function wire() {
  el.guessSubmit.addEventListener("click", submitGuess);
  el.skip.addEventListener("click", skip);
  el.prev.addEventListener("click", () => go(-1));
  el.next.addEventListener("click", () => go(1));
  el.guessInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      submitGuess();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (document.activeElement === el.guessInput) return;
    if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
  });
}

async function load() {
  showNotice("正在从 Notion 读取…", false);
  try {
    const res = await fetch("/api/cards");
    const data = await res.json();
    if (!data.ok) {
      showNotice("读取 Notion 失败：" + (data.error || "未知错误"), true);
      return;
    }
    state.cards = data.cards || [];
    if (state.cards.length === 0) {
      showNotice("Notion 数据库里还没有卡片。先用截图流程存几条，再回来复习。", false);
      return;
    }
    el.notice.hidden = true;
    el.card.hidden = false;
    el.nav.hidden = false;
    updateStreak();
    resetCard();
    render();
  } catch (err) {
    showNotice("无法连接本地服务：" + err.message, true);
  }
}

// ===================== 对话练习 (chat mode) =====================
const chat = {
  characters: [],
  loaded: false,
  session: null, // { id, character, color, name, targets }
};
const chatEl = {
  reviewView: $("review-view"),
  chatView: $("chat-view"),
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
};

function setMode(mode) {
  document.querySelectorAll(".mode-tab").forEach((t) => {
    t.classList.toggle("is-active", t.dataset.mode === mode);
  });
  const isChat = mode === "chat";
  chatEl.reviewView.hidden = isChat;
  chatEl.chatView.hidden = !isChat;
  el.notice.hidden = true;
  if (isChat && !chat.loaded) loadCharacters();
}

function initials(name) {
  return name.replace(/[^A-Za-z ]/g, "").trim().slice(0, 2).toUpperCase() || "?";
}

async function loadCharacters() {
  try {
    const res = await fetch("/api/characters");
    const data = await res.json();
    if (!data.ok) return;
    chat.characters = data.characters || [];
    chat.loaded = true;
    renderCharGrid();
  } catch (_) {
    /* leave grid empty; user can retry by re-toggling */
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
    chatEl.charGrid.appendChild(card);
  });
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
  chatEl.room.style.setProperty("--ai-tint", tint(c.color, 0.10));
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

// Light client-side highlight of which targets the learner has said so far.
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

// Turn a hex color into an rgba tint string for bubble backgrounds.
function tint(hex, alpha) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
  if (!m) return "rgba(45,27,105," + alpha + ")";
  const r = parseInt(m[1], 16), g = parseInt(m[2], 16), b = parseInt(m[3], 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

function wireChat() {
  document.querySelectorAll(".mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => setMode(tab.dataset.mode));
  });
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
}

wire();
wireChat();
load();
