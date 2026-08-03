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
  shownAt: 0, // ms timestamp of when the current card's prompt appeared
  whToken: 0, // guards async word-history renders against paging races
};

const el = {
  notice: $("notice"),
  card: $("card"),
  nav: $("nav"),
  counter: $("counter"),
  episodeLine: $("episode-line"),
  filetab: $("case-kicker"),
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
  wordhist: $("wordhist"),
  whProg: $("wh-prog"),
  whPct: $("wh-pct"),
  whTip: $("wh-tip"),
  today: $("today"),
  prev: $("prev"),
  next: $("next"),
  pips: $("pips"),
};

const STAMPS = {
  cold: { cls: "gold", text: "FIRST TRY ✓", note: "You recognized it in a brand new context." },
  hint: { cls: "", text: "CUED RECALL", note: "You got it with a little help." },
  revealed: { cls: "wine", text: "REVEALED", note: "Review this one again soon." },
};

// Chinese verb phrases for "上次…" in the ring tooltip. The UI never shows the
// uppercase enum names themselves.
const LAST_RESULT_ZH = {
  FIRST_TRY_CORRECT: "一次答对",
  CUED_CORRECT: "提示后答对",
  INCORRECT: "答错了",
  REVEALED: "看了答案",
};

// r=21 in the 48-viewBox ring; keep in sync with .wordhist circles' r.
const RING_CIRC = 2 * Math.PI * 21;

// "今天" / "昨天" / "N 天前" from a UTC ISO timestamp, by local calendar day.
function daysAgoZh(iso) {
  const then = new Date(iso);
  if (isNaN(then)) return "";
  const startOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((startOf(new Date()) - startOf(then)) / 86400000);
  if (days <= 0) return "今天";
  if (days === 1) return "昨天";
  return days + " 天前";
}

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
  return esc(text).replace(/＿＿＿/g, '<span class="blank" aria-hidden="true"></span>');
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

// Draw the ratio ring: filled arc = first_try/total, clockwise from 12 o'clock.
function drawRing(ratio) {
  const filled = Math.max(0, Math.min(1, ratio)) * RING_CIRC;
  el.whProg.setAttribute("stroke-dasharray", filled + " " + RING_CIRC);
  el.whProg.setAttribute("stroke-dashoffset", "0");
}

// Fetch and render the per-expression practice history beside the title.
// Hidden entirely when the expression has no recorded attempts. Its own render
// is async and race-guarded so paging away mid-fetch can't paint stale data.
async function renderWordHistory(card) {
  el.wordhist.hidden = true;
  const pageId = card && card.id;
  if (!pageId) return;
  const token = ++state.whToken;
  let h = null;
  try {
    const res = await fetch("/api/word-history?page_id=" + encodeURIComponent(pageId));
    const data = await res.json();
    h = data && data.history;
  } catch (_) {
    return; // recording-only feature; stay silent on failure
  }
  if (token !== state.whToken) return; // paged away while fetching
  if (!h || !h.total) return;

  const ratio = h.total ? h.first_try / h.total : 0;
  drawRing(ratio);
  el.whPct.textContent = Math.round(ratio * 100) + "%";
  // Everything lives in the hover tooltip now — the ring stays uncluttered.
  const when = daysAgoZh(h.last_at);
  const verb = LAST_RESULT_ZH[h.last_result] || "";
  const last = "上次 " + when + (verb ? " " + verb : "");
  el.whTip.textContent =
    "练过 " + h.total + " 次 · 一次答对 " + h.first_try + " 次 · " + last;
  el.wordhist.hidden = false;
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
  } else {
    // Keep the async word-history from lingering on the next (unrevealed) card.
    el.wordhist.hidden = true;
  }

  el.counter.textContent = state.i + 1 + " / " + state.cards.length;
  el.prev.disabled = state.i === 0;
  el.next.disabled = state.i === state.cards.length - 1;
}

function resetCard() {
  state.layer = 1;
  state.revealed = false;
  state.outcome = null;
  state.shownAt = Date.now();
  el.guessInput.value = "";
  el.nudge.hidden = true;
  el.nudge.textContent = "";
}

// Append one attempt to the local SQLite review log. `result` is an uppercase
// enum: FIRST_TRY_CORRECT | CUED_CORRECT | INCORRECT | REVEALED. Recording only
// — failures are ignored so they can never interrupt the review flow. Returns
// the request promise so callers can refresh the word-history after it lands.
function logAttempt(result) {
  const card = state.cards[state.i];
  if (!card) return Promise.resolve();
  const elapsed = (Date.now() - state.shownAt) / 1000;
  return fetch("/api/review-log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_id: card.id || "",
      expression: card.expression || "",
      result,
      elapsed_seconds: elapsed,
    }),
  }).catch(() => {});
}

// Log the attempt, then reveal the answer and refresh both the word-history
// (now including this attempt) and the TODAY counter.
function logThenReveal(result, outcome) {
  const card = state.cards[state.i];
  logAttempt(result).then(() => {
    if (state.cards[state.i] === card) renderWordHistory(card);
    refreshTodayCount();
  });
  revealWith(outcome);
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
    // Log the uppercase enum; the visual stamp still uses "cold"/"hint".
    logThenReveal(
      state.layer >= 2 ? "CUED_CORRECT" : "FIRST_TRY_CORRECT",
      state.layer >= 2 ? "hint" : "cold"
    );
    return;
  }

  if (state.layer === 1) {
    state.layer = 2;
    el.nudge.hidden = false;
    el.nudge.textContent = "Not quite — try again?";
    el.guessInput.value = "";
    render();
  } else {
    // Wrong again after the hint layer — a genuine miss, distinct from a skip.
    logThenReveal("INCORRECT", "revealed");
  }
}

function skip() {
  if (state.revealed) return;
  logThenReveal("REVEALED", "revealed");
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

// Update the top-bar TODAY counter (attempts logged today). Count only — no
// accuracy, by design: showing a live hit-rate nudges users away from hard cards.
async function refreshTodayCount() {
  if (!el.today) return;
  try {
    const res = await fetch("/api/today-count");
    const data = await res.json();
    if (data && data.ok) el.today.textContent = "TODAY " + data.count;
  } catch (_) {
    // leave whatever was there; the counter is non-critical
  }
}

async function load() {
  showNotice("正在从 Notion 读取…", false);
  refreshTodayCount();
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
