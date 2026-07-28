"use strict";

const state = {
  cards: [],
  i: 0,
  mode: "cloze", // cloze | zh2en | en2zh
  revealed: false,
};

const $ = (id) => document.getElementById(id);
const el = {
  notice: $("notice"),
  card: $("card"),
  nav: $("nav"),
  shot: $("shot"),
  shotImg: $("shot-img"),
  shotEmpty: $("shot-empty"),
  difficulty: $("difficulty"),
  prompt: $("prompt"),
  answer: $("answer"),
  aExpr: $("a-expression"),
  aLine: $("a-line"),
  aCn: $("a-chinese"),
  aContext: $("a-context"),
  reveal: $("reveal"),
  prev: $("prev"),
  next: $("next"),
  counter: $("counter"),
  mask: $("subtitle-mask"),
  guess: $("guess"),
  guessInput: $("guess-input"),
  guessSubmit: $("guess-submit"),
  verdict: $("verdict"),
};

// Modes where the learner recalls the English expression, so a typed input helps.
const GUESS_MODES = new Set(["cloze", "zh2en"]);

// Loose normalization for judging: lowercase, collapse inner whitespace,
// trim, and drop trailing punctuation. So "You were off your game." matches
// "off your game".
function normalizeAnswer(s) {
  return String(s == null ? "" : s)
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.,!?;:'"“”‘’…]+$/g, "")
    .trim();
}

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

// The effective mode for the current card: cloze silently degrades to zh2en
// when the target expression couldn't be blanked out of the example line.
function effectiveMode(card) {
  if (state.mode === "cloze" && !card.cloze_ok) return "zh2en";
  return state.mode;
}

function renderShot(card) {
  if (card.image_url) {
    el.shotImg.src = card.image_url;
    el.shotImg.hidden = false;
    el.shotEmpty.hidden = true;
  } else {
    el.shotImg.removeAttribute("src");
    el.shotImg.hidden = true;
    el.shotEmpty.hidden = false;
  }
}

function clozeHTML(card) {
  // card.cloze_text already has the blank marker substituted server-side.
  return esc(card.cloze_text).replace(/＿＿＿/g, '<span class="blank">＿＿＿</span>');
}

function render() {
  const card = state.cards[state.i];
  if (!card) return;
  const mode = effectiveMode(card);

  renderShot(card);
  el.difficulty.textContent = card.difficulty || "";

  // Prompt (before reveal) differs per mode.
  if (mode === "cloze") {
    el.prompt.innerHTML = clozeHTML(card);
  } else if (mode === "zh2en") {
    el.prompt.innerHTML = '<span class="zh">' + esc(card.chinese) + "</span>";
  } else {
    el.prompt.innerHTML = esc(card.expression);
  }

  // Answer (after reveal) — same rich block for all modes.
  el.aExpr.textContent = card.expression;
  el.aLine.textContent = card.example || "";
  el.aCn.textContent = card.chinese || "";
  el.aContext.textContent = card.context || "";

  // In en2zh the screenshot is part of the *answer*, so hide it until reveal.
  const hideShotUntilReveal = mode === "en2zh";
  el.shot.style.display = hideShotUntilReveal && !state.revealed ? "none" : "";

  // Cloze mode: the burned-in subtitle spoils the blank, so mask the bottom
  // band until reveal. Other modes never show a spoiling subtitle.
  el.mask.hidden = !(mode === "cloze" && card.image_url && !state.revealed);

  // Typed guess appears only in the "recall the English" modes, before reveal.
  const wantGuess = GUESS_MODES.has(mode) && !state.revealed;
  el.guess.hidden = !wantGuess;
  if (wantGuess) el.guessInput.focus();

  el.answer.hidden = !state.revealed;
  el.reveal.hidden = state.revealed;

  el.counter.textContent = state.i + 1 + " / " + state.cards.length;
  el.prev.disabled = state.i === 0;
  el.next.disabled = state.i === state.cards.length - 1;
}

function clearGuess() {
  el.guessInput.value = "";
  el.verdict.hidden = true;
  el.verdict.className = "verdict";
  el.verdict.innerHTML = "";
}

function reveal() {
  if (state.revealed) return;
  state.revealed = true;
  render();
}

function submitGuess() {
  const card = state.cards[state.i];
  if (!card) return;
  const raw = el.guessInput.value;
  if (!normalizeAnswer(raw)) return; // empty — ignore, let them use 揭晓
  const correct = normalizeAnswer(raw) === normalizeAnswer(card.expression);
  el.verdict.hidden = false;
  if (correct) {
    el.verdict.className = "verdict ok";
    el.verdict.textContent = "正确 ✓";
  } else {
    el.verdict.className = "verdict miss";
    el.verdict.innerHTML =
      "差一点～ 你写的是 <span class=\"yours\">" +
      esc(raw.trim()) +
      "</span>，正确答案是 <span class=\"right\">" +
      esc(card.expression) +
      "</span>";
  }
  reveal();
}

function go(delta) {
  const n = state.i + delta;
  if (n < 0 || n >= state.cards.length) return;
  state.i = n;
  state.revealed = false;
  clearGuess();
  render();
}

function setMode(mode) {
  state.mode = mode;
  state.revealed = false;
  clearGuess();
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.mode === mode);
  });
  render();
}

function wire() {
  el.reveal.addEventListener("click", reveal);
  el.prev.addEventListener("click", () => go(-1));
  el.next.addEventListener("click", () => go(1));
  el.guessSubmit.addEventListener("click", submitGuess);
  document.querySelectorAll(".mode-btn").forEach((b) => {
    b.addEventListener("click", () => setMode(b.dataset.mode));
  });
  // Enter inside the input submits the guess; keep it out of the global handler
  // so it doesn't also fire 揭晓.
  el.guessInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      submitGuess();
    }
  });
  document.addEventListener("keydown", (e) => {
    // Don't hijack typing while the guess box has focus.
    if (document.activeElement === el.guessInput) return;
    if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      reveal();
    }
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
    if (state.cards.length < 5) {
      console.info("BingeLingo: only " + state.cards.length + " card(s) in Notion.");
    }
    render();
  } catch (err) {
    showNotice("无法连接本地服务：" + err.message, true);
  }
}

wire();
load();
