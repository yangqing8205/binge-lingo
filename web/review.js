"use strict";

// Three-layer progressive review over a TV-archive UI.
//   layer 1 — new-context mini-scenario, no hints, type the answer
//   layer 2 — after a miss: Chinese meaning + first-letter hint, retry
//   layer 3 — after a second miss (or skip): full "original evidence" reveal
const state = {
  cards: [],
  i: 0,
  layer: 1,
  revealed: false,
  outcome: null, // "cold" | "hint" | "revealed"
};

const el = {
  notice: $("notice"),
  card: $("card"),
  nav: $("nav"),
  counter: $("counter"),
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

function showNotice(msg, isError) {
  el.notice.hidden = false;
  el.notice.textContent = msg;
  el.notice.classList.toggle("error", !!isError);
  el.card.hidden = true;
  el.nav.hidden = true;
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
    resetCard();
    render();
  } catch (err) {
    showNotice("无法连接本地服务：" + err.message, true);
  }
}

wire();
load();
