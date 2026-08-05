"use strict";

// Shared helpers for all three pages (/review, /chat, /export).
// Loaded before each page's own script.

const $ = (id) => document.getElementById(id);

// If the session expired mid-use, any API call 401s — bounce to the login page
// rather than surfacing a confusing error. Wraps the native fetch.
const _rawFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await _rawFetch(...args);
  if (res.status === 401 && !location.pathname.startsWith("/login")) {
    location.href = "/login";
  }
  return res;
};

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

// Turn a hex color into an rgba tint string.
function tint(hex, alpha) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
  if (!m) return "rgba(45,27,105," + alpha + ")";
  const r = parseInt(m[1], 16), g = parseInt(m[2], 16), b = parseInt(m[3], 16);
  return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
}

// Two-letter avatar initials from a display name.
function initials(name) {
  return String(name || "").replace(/[^A-Za-z ]/g, "").trim().slice(0, 2).toUpperCase() || "?";
}

// Daily-streak counter (local only). Writes into #streak if present.
function updateStreak() {
  const node = $("streak");
  if (!node) return;
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
  node.textContent = "DAY " + day;
}

// Mark the active nav tab based on the current path.
function markActiveNav() {
  const path = location.pathname.replace(/\/$/, "") || "/review";
  document.querySelectorAll(".folder-tab").forEach((a) => {
    const href = a.getAttribute("href");
    a.classList.toggle("is-active", href === path);
  });
}

// ---- show switcher --------------------------------------------------------
// The one place every tab learns which show to filter by. Lives in the topbar
// next to DAY N. Reading current_show from here (instead of each tab guessing
// it from the newest card) is the whole point of this refactor.
const ALL_SHOWS_LABEL = "全部剧集";

// The switcher itself (the button element) is created ONCE and never torn
// down or re-rendered on switch — only its text content changes, and it
// changes immediately on click (optimistic), before the POST resolves. This
// is what keeps it from flickering: a page-wide reload used to rebuild the
// whole DOM (switcher included) on every switch. Each page instead listens
// for "bl:show-changed" and refreshes its own content independently, with its
// own loading state.
async function initShowSwitcher() {
  const root = $("show-switcher");
  if (!root) return;

  let current = "";
  let shows = [];
  try {
    const [curRes, showsRes] = await Promise.all([
      fetch("/api/current-show"),
      fetch("/api/shows"),
    ]);
    const curData = await curRes.json();
    const showsData = await showsRes.json();
    if (curData && curData.ok) current = curData.show || "";
    if (showsData && showsData.ok) shows = showsData.shows || [];
  } catch (_) {
    return; // best-effort; leave the switcher absent rather than broken
  }

  root.innerHTML = "";
  root.classList.add("show-switcher");

  const btn = document.createElement("button");
  btn.className = "show-switcher__btn";
  btn.textContent = current || ALL_SHOWS_LABEL;
  root.appendChild(btn);

  const menu = document.createElement("div");
  menu.className = "show-switcher__menu";
  menu.hidden = true;
  root.appendChild(menu);

  function renderMenu() {
    menu.innerHTML = "";
    const options = [""].concat(shows); // "" = 全部剧集
    options.forEach((show) => {
      const item = document.createElement("button");
      item.className = "show-switcher__item" + (show === current ? " is-on" : "");
      item.textContent = show || ALL_SHOWS_LABEL;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        menu.hidden = true;
        switchTo(show);
      });
      menu.appendChild(item);
    });
  }
  renderMenu();

  async function switchTo(show) {
    if (show === current) return;
    const prevShow = current;
    const prevLabel = btn.textContent;
    current = show;
    btn.textContent = show || ALL_SHOWS_LABEL;
    renderMenu();
    try {
      const res = await fetch("/api/current-show", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show }),
      });
      const data = await res.json();
      if (!data || !data.ok) throw new Error((data && data.error) || "切换失败");
    } catch (err) {
      // Never leave the button on an unconfirmed show — roll all the way back.
      current = prevShow;
      btn.textContent = prevLabel;
      renderMenu();
      alert("切换剧集失败：" + err.message);
      return;
    }
    document.dispatchEvent(new CustomEvent("bl:show-changed", { detail: { show } }));
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
  });

  document.addEventListener("click", () => {
    menu.hidden = true;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  markActiveNav();
  updateStreak();
  initShowSwitcher();
});
