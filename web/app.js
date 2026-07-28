"use strict";

// Three-layer progressive review:
//   layer 1 — new-context cloze sentence, no hints, type the answer
//   layer 2 — after a wrong answer: semantic (Chinese) + initial-letter hints, retry
//   layer 3 — after two wrong answers: full reveal (screenshot, original line, …)
// A correct answer at any layer jumps straight to the reveal.
const state = {
  cards: [],
  i: 0,
  layer: 1,      // 1 | 2 | 3
  revealed: false,
};

const $ = (id) => document.getElementById(id);
const el = {
  notice: $("notice"),
  card: $("card"),
  nav: $("nav"),
  difficulty: $("difficulty"),
  layerBanner: $("layer-banner"),
  prompt: $("prompt"),
  hints: $("hints"),
  hintMeaning: $("hint-meaning"),
  hintInitials: $("hint-initials"),
  guess: $("guess"),
  guessInput: $("guess-input"),
  guessSubmit: $("guess-submit"),
  verdict: $("verdict"),
  answer: $("answer"),
  shot: $("shot"),
  shotImg: $("shot-img"),
  aExpr: $("a-expression"),
  aLine: $("a-line"),
  aCn: $("a-chinese"),
  aContext: $("a-context"),
  aStructure: $("a-structure"),
  reveal: $("reveal"),
  prev: $("prev"),
  next: $("next"),
  counter: $("counter"),
  pips: $("layer-pips"),
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

function clozeHTML(text) {
  return esc(text).replace(/＿＿＿/g, '<span class="blank">＿＿＿</span>');
}

// Render the layer-1 prompt. In "zh2en" fallback (no blankable sentence) we
// show the Chinese meaning and ask the learner to recall the English.
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
    const n = Number(p.dataset.layer);
    p.classList.toggle("is-on", n <= state.layer);
  });
}

const BANNERS = {
  1: "新语境挑战 · 看句子填空",
  2: "再试一次 · 给你两个提示",
  3: "原始记忆唤醒 · 完整答案",
};

function renderReveal(card) {
  if (card.image_url) {
    el.shotImg.src = card.image_url;
    el.shot.hidden = false;
  } else {
    el.shotImg.removeAttribute("src");
    el.shot.hidden = true;
  }
  el.aExpr.textContent = card.expression || "";
  el.aLine.textContent = card.example || "";
  el.aCn.textContent = card.chinese || "";
  el.aContext.textContent = card.context || "";
  el.aStructure.textContent = card.common_structure
    ? "常见结构：" + card.common_structure
    : "";
}

function render() {
  const card = state.cards[state.i];
  if (!card) return;

  el.difficulty.textContent = card.difficulty || "";
  renderPrompt(card);
  setPips();

  const showHints = state.layer >= 2 && !state.revealed;
  el.hints.hidden = !showHints;
  if (showHints) {
    el.hintMeaning.textContent = card.chinese || "（暂无中文释义）";
    el.hintInitials.textContent = card.initials_hint || "";
  }

  // Input stays available until the card is revealed (layers 1 and 2).
  const showGuess = !state.revealed && state.layer <= 2;
  el.guess.hidden = !showGuess;
  if (showGuess) el.guessInput.focus();

  el.answer.hidden = !state.revealed;
  if (state.revealed) renderReveal(card);

  el.layerBanner.textContent = state.revealed
    ? BANNERS[3]
    : BANNERS[state.layer];

  el.reveal.hidden = state.revealed;
  el.reveal.textContent = state.layer >= 2 ? "放弃 · 看答案" : "直接揭晓";

  el.counter.textContent = state.i + 1 + " / " + state.cards.length;
  el.prev.disabled = state.i === 0;
  el.next.disabled = state.i === state.cards.length - 1;
}

function clearVerdict() {
  el.verdict.hidden = true;
  el.verdict.className = "verdict";
  el.verdict.innerHTML = "";
}

function resetCard() {
  state.layer = 1;
  state.revealed = false;
  el.guessInput.value = "";
  clearVerdict();
}

function reveal() {
  if (state.revealed) return;
  state.revealed = true;
  render();
}

function showVerdict(kind, html) {
  el.verdict.hidden = false;
  el.verdict.className = "verdict " + kind;
  el.verdict.innerHTML = html;
}

async function submitGuess() {
  const card = state.cards[state.i];
  if (!card || state.revealed) return;
  const raw = el.guessInput.value;
  if (!raw.trim()) return; // empty — let them use 揭晓 instead

  let correct = false;
  try {
    const res = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guess: raw, expression: card.expression }),
    });
    const data = await res.json();
    correct = !!data.correct;
  } catch (err) {
    showVerdict("miss", "判分服务连接失败：" + esc(err.message));
    return;
  }

  if (correct) {
    const msg = state.layer >= 2 ? "答对了！✓" : "正确！✓";
    showVerdict("ok", msg);
    reveal();
    return;
  }

  // Wrong: advance a layer. First miss → hints; second miss → full reveal.
  if (state.layer === 1) {
    state.layer = 2;
    showVerdict(
      "miss",
      "还差一点～ 你写的是 <span class=\"yours\">" +
        esc(raw.trim()) +
        "</span>。看看下面的提示，再试一次。"
    );
    el.guessInput.value = "";
    render();
  } else {
    showVerdict(
      "miss",
      "你写的是 <span class=\"yours\">" +
        esc(raw.trim()) +
        "</span>，正确答案是 <span class=\"right\">" +
        esc(card.expression) +
        "</span>。别灰心，多看几遍就记住了。"
    );
    state.layer = 3;
    reveal();
  }
}

function go(delta) {
  const n = state.i + delta;
  if (n < 0 || n >= state.cards.length) return;
  state.i = n;
  resetCard();
  render();
}

function wire() {
  el.reveal.addEventListener("click", reveal);
  el.prev.addEventListener("click", () => go(-1));
  el.next.addEventListener("click", () => go(1));
  el.guessSubmit.addEventListener("click", submitGuess);
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
    resetCard();
    render();
  } catch (err) {
    showNotice("无法连接本地服务：" + err.message, true);
  }
}

wire();
load();
