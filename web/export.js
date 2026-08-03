"use strict";

// 带走练习 — assemble a portable roleplay prompt from live options.
// Nothing here calls the model; we just fetch characters + expressions and
// string-build a prompt that the learner pastes into any AI chat tool.

const ex = {
  characters: [],
  expressions: [],
  sel: {
    character: "fil",
    expressions: new Set(),
    turns: "standard",
    guidance: "high",
    scene: "auto",
    sceneCustom: "",
    correction: "gentle",
    language: "en",
  },
};

// ---- option definitions (value → label + the phrase injected into the prompt)
const TURNS = [
  { v: "quick", label: "快速（3-4轮）", hint: "我只有两分钟", star: false, count: "3-4" },
  { v: "standard", label: "标准（6-8轮）", hint: "推荐", star: true, count: "6-8" },
  { v: "deep", label: "深度（10+轮）", hint: "今天想好好练", star: false, count: "10 or more" },
];
const GUIDANCE = [
  { v: "high", label: "多引导", hint: "适合刚学的表达", star: true,
    line: "Actively set up situations that create natural openings for me to use each target expression." },
  { v: "low", label: "少引导", hint: "适合快掌握的", star: false,
    line: "Chat normally without deliberately engineering openings — let the expressions come up only if they fit." },
  { v: "none", label: "不引导", hint: "最难", star: false,
    line: "Do not steer toward the expressions at all. Just have a free conversation and see whether I use them on my own." },
];
const SCENE = [
  { v: "auto", label: "让 AI 选", star: true, line: "Pick a fitting everyday setting yourself." },
  { v: "casual", label: "日常闲聊", star: false, line: "Set it in a casual hangout — friends chatting, venting, gossiping." },
  { v: "work", label: "职场", star: false, line: "Set it at work — a meeting or small talk with a coworker." },
  { v: "social", label: "社交", star: false, line: "Set it at a social event — a party, meeting new people." },
  { v: "family", label: "家庭", star: false, line: "Set it at home — chatting with family, a little household friction." },
  { v: "custom", label: "自定义", star: false, line: "" },
];
const CORRECTION = [
  { v: "gentle", label: "温和纠正", hint: "在角色内顺便带过", star: true,
    line: "If I misuse a target expression, gently correct me while staying in character." },
  { v: "explicit", label: "明确纠正", hint: "跳出角色指出再回来", star: false,
    line: "If I misuse a target expression, briefly step out of character to point out the correct usage, then resume." },
  { v: "none", label: "不纠正", hint: "最后统一点评", star: false,
    line: "Don't correct me mid-conversation; save all feedback for the debrief at the end." },
];
const LANGUAGE = [
  { v: "en", label: "全英文（沉浸式）", star: true,
    line: "Reply only in English the whole time." },
  { v: "mix", label: "英文为主偶尔中文解释", star: false,
    line: "Reply mostly in English, but you may add a brief Chinese explanation when something is tricky." },
];

const el = {
  notice: $("notice"),
  optCharacter: $("opt-character"),
  optExpr: $("opt-expressions"),
  exprAll: $("expr-all"),
  exprNone: $("expr-none"),
  optTurns: $("opt-turns"),
  optGuidance: $("opt-guidance"),
  optScene: $("opt-scene"),
  sceneCustom: $("scene-custom"),
  optCorrection: $("opt-correction"),
  optLanguage: $("opt-language"),
  out: $("prompt-out"),
  copyBtn: $("copy-btn"),
  copyNote: $("copy-note"),
};

// ---- generic single-select renderer
function renderChoices(container, items, selectedValue, onPick) {
  container.innerHTML = "";
  items.forEach((it) => {
    const b = document.createElement("button");
    b.className = "choice" + (it.v === selectedValue ? " is-on" : "");
    let html = esc(it.label);
    if (it.hint) html += ' <span class="choice-hint">' + esc(it.hint) + "</span>";
    if (it.star) html += ' <span class="choice-star">⭐</span>';
    b.innerHTML = html;
    b.addEventListener("click", () => onPick(it.v));
    container.appendChild(b);
  });
}

function renderCharacters() {
  renderChoices(
    el.optCharacter,
    ex.characters.map((c) => ({ v: c.key, label: c.name, hint: c.intro })),
    ex.sel.character,
    (v) => { ex.sel.character = v; renderCharacters(); build(); }
  );
}

function renderExpressions() {
  el.optExpr.innerHTML = "";
  ex.expressions.forEach((expr) => {
    const t = document.createElement("button");
    t.className = "tag" + (ex.sel.expressions.has(expr) ? " is-on" : "");
    t.textContent = expr;
    t.addEventListener("click", () => {
      if (ex.sel.expressions.has(expr)) ex.sel.expressions.delete(expr);
      else ex.sel.expressions.add(expr);
      renderExpressions();
      build();
    });
    el.optExpr.appendChild(t);
  });
}

function renderStatic() {
  renderChoices(el.optTurns, TURNS, ex.sel.turns, (v) => { ex.sel.turns = v; renderStatic(); build(); });
  renderChoices(el.optGuidance, GUIDANCE, ex.sel.guidance, (v) => { ex.sel.guidance = v; renderStatic(); build(); });
  renderChoices(el.optScene, SCENE, ex.sel.scene, (v) => {
    ex.sel.scene = v;
    el.sceneCustom.hidden = v !== "custom";
    renderStatic();
    build();
  });
  renderChoices(el.optCorrection, CORRECTION, ex.sel.correction, (v) => { ex.sel.correction = v; renderStatic(); build(); });
  renderChoices(el.optLanguage, LANGUAGE, ex.sel.language, (v) => { ex.sel.language = v; renderStatic(); build(); });
}

// ---- prompt assembly (matches the approved template) ----
function build() {
  const char = ex.characters.find((c) => c.key === ex.sel.character);
  const targets = [...ex.sel.expressions];
  const turns = TURNS.find((t) => t.v === ex.sel.turns);
  const guidance = GUIDANCE.find((g) => g.v === ex.sel.guidance);
  const correction = CORRECTION.find((c) => c.v === ex.sel.correction);
  const language = LANGUAGE.find((l) => l.v === ex.sel.language);

  let sceneLine;
  if (ex.sel.scene === "custom") {
    const custom = ex.sel.sceneCustom.trim();
    sceneLine = custom ? "Setting: " + custom : "Setting: pick a fitting everyday setting yourself.";
  } else {
    sceneLine = "Setting: " + SCENE.find((s) => s.v === ex.sel.scene).line;
  }

  // Include the source show so an external AI can better reconstruct the
  // character. The persona already opens with "You are <name>, ...", so prepend
  // the show as context rather than duplicating the name.
  let personaLine;
  if (char) {
    const show = (char.source_show || "").trim();
    personaLine = show
      ? "Roleplay as this character from " + show + ".\n" + char.persona
      : char.persona;
  } else {
    personaLine = "You are a friendly conversation partner.";
  }

  const targetBlock = targets.length
    ? targets.map((t) => "- " + t).join("\n")
    : "- (choose at least one expression above)";

  const out = [
    personaLine,
    "",
    "I'm an English learner practicing speaking. Role-play as this character and chat with me naturally in English.",
    "",
    "Today I want to practice these expressions:",
    targetBlock,
    "",
    "Rules:",
    "- Stay fully in character the whole time.",
    "- " + guidance.line,
    "- Aim for about " + turns.count + " back-and-forth exchanges.",
    "- " + sceneLine,
    "- " + correction.line,
    "- " + language.line,
    "- Never tell me which words to use — invite them through the situation.",
    "",
    "At the end, step out of character and give me a short debrief: list which target expressions I used correctly, which I missed (with a concrete suggestion for each — e.g. \"when you said '...', you could have said '...'\"), one line of encouragement, and a final count like \"3/" + (targets.length || 5) + " expressions used\".",
    "",
    "Start now with your first message, in character.",
  ].join("\n");

  el.out.value = out;
}

async function loadData() {
  el.notice.hidden = true;
  try {
    const [cRes, kRes] = await Promise.all([
      fetch("/api/characters"),
      fetch("/api/cards"),
    ]);
    const cData = await cRes.json();
    const kData = await kRes.json();
    ex.characters = (cData.characters || []);
    ex.expressions = [...new Set((kData.cards || []).map((c) => c.expression).filter(Boolean))];
    // default: most-recent 5 (cards come newest-first from the API)
    ex.expressions.slice(0, 5).forEach((e) => ex.sel.expressions.add(e));
    if (ex.characters.length) ex.sel.character = ex.characters[0].key;

    renderCharacters();
    renderExpressions();
    renderStatic();
    build();
  } catch (err) {
    el.notice.hidden = false;
    el.notice.classList.add("error");
    el.notice.textContent = "读取数据失败：" + err.message;
  }
}

function wire() {
  el.exprAll.addEventListener("click", () => {
    ex.expressions.forEach((e) => ex.sel.expressions.add(e));
    renderExpressions(); build();
  });
  el.exprNone.addEventListener("click", () => {
    ex.sel.expressions.clear();
    renderExpressions(); build();
  });
  el.sceneCustom.addEventListener("input", () => {
    ex.sel.sceneCustom = el.sceneCustom.value;
    build();
  });
  el.copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el.out.value);
      el.copyNote.textContent = "已复制到剪贴板 ✓";
    } catch (_) {
      el.out.select();
      el.copyNote.textContent = "已选中，按 Cmd/Ctrl+C 复制";
    }
    setTimeout(() => { el.copyNote.textContent = ""; }, 2500);
  });
}

wire();
loadData();
