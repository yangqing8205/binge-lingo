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

document.addEventListener("DOMContentLoaded", () => {
  markActiveNav();
  updateStreak();
});
