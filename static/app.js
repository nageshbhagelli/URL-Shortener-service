/**
 * app.js — Frontend logic for Snip URL Shortener
 * Vanilla JS, no dependencies.
 */

const API_BASE = "";  // same origin

// ─── DOM References ────────────────────────────────────────────────────────────
const shortenForm    = document.getElementById("shorten-form");
const longUrlInput   = document.getElementById("long-url-input");
const aliasInput     = document.getElementById("alias-input");
const ttlInput       = document.getElementById("ttl-input");
const shortenBtn     = document.getElementById("shorten-btn");
const btnLabel       = document.getElementById("btn-label");
const btnSpinner     = document.getElementById("btn-spinner");
const resultBox      = document.getElementById("result-box");
const shortUrlDisplay = document.getElementById("short-url-display");
const copyBtn        = document.getElementById("copy-btn");
const copyIcon       = document.getElementById("copy-icon");
const expiryLabel    = document.getElementById("expiry-label");
const errorBox       = document.getElementById("error-box");
const errorMessage   = document.getElementById("error-message");
const viewStatsBtn   = document.getElementById("view-stats-btn");

const toggleAdvanced = document.getElementById("toggle-advanced");
const advancedPanel  = document.getElementById("advanced-panel");
const chevron        = toggleAdvanced.querySelector(".chevron");

const statsSection   = document.getElementById("stats-section");
const statsCodeInput = document.getElementById("stats-code-input");
const fetchStatsBtn  = document.getElementById("fetch-stats-btn");
const statsResult    = document.getElementById("stats-result");
const statsError     = document.getElementById("stats-error");

// ─── Advanced Panel Toggle ─────────────────────────────────────────────────────
toggleAdvanced.addEventListener("click", () => {
  const isOpen = !advancedPanel.classList.contains("hidden");
  advancedPanel.classList.toggle("hidden", isOpen);
  chevron.classList.toggle("open", !isOpen);
  toggleAdvanced.setAttribute("aria-expanded", String(!isOpen));
});

// ─── Shorten Form Submit ───────────────────────────────────────────────────────
shortenForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideResult();
  hideError();

  const longUrl = longUrlInput.value.trim();
  if (!longUrl) {
    showError("Please enter a URL.");
    return;
  }

  const alias   = aliasInput.value.trim() || null;
  const ttlDays = ttlInput.value ? parseInt(ttlInput.value, 10) : null;

  setLoading(true);

  try {
    const res = await fetch(`${API_BASE}/shorten`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ long_url: longUrl, alias, ttl_days: ttlDays }),
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Something went wrong. Please try again.");
      return;
    }

    showResult(data);
  } catch (err) {
    showError("Network error. Check your connection and try again.");
  } finally {
    setLoading(false);
  }
});

// ─── Copy to Clipboard ─────────────────────────────────────────────────────────
copyBtn.addEventListener("click", async () => {
  const url = shortUrlDisplay.textContent;
  try {
    await navigator.clipboard.writeText(url);
    copyIcon.textContent = "✓";
    copyBtn.classList.add("copied");
    setTimeout(() => {
      copyIcon.textContent = "⎘";
      copyBtn.classList.remove("copied");
    }, 2000);
  } catch {
    copyIcon.textContent = "✓";
    setTimeout(() => { copyIcon.textContent = "⎘"; }, 2000);
  }
});

// ─── View Stats Button ─────────────────────────────────────────────────────────
viewStatsBtn.addEventListener("click", () => {
  const code = shortUrlDisplay.dataset.code;
  if (!code) return;
  statsSection.classList.remove("hidden");
  statsCodeInput.value = code;
  statsSection.scrollIntoView({ behavior: "smooth" });
  fetchStats(code);
});

// ─── Stats Lookup ──────────────────────────────────────────────────────────────
fetchStatsBtn.addEventListener("click", () => {
  const code = statsCodeInput.value.trim();
  if (!code) return;
  fetchStats(code);
});

statsCodeInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const code = statsCodeInput.value.trim();
    if (code) fetchStats(code);
  }
});

// Reveal stats section when clicking nav link
document.getElementById("nav-stats").addEventListener("click", (e) => {
  e.preventDefault();
  statsSection.classList.remove("hidden");
  statsSection.scrollIntoView({ behavior: "smooth" });
});

async function fetchStats(code) {
  statsResult.classList.add("hidden");
  statsError.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/stats/${encodeURIComponent(code)}`);
    const data = await res.json();

    if (!res.ok) {
      statsError.textContent = data.error || "Short code not found.";
      statsError.classList.remove("hidden");
      return;
    }

    renderStats(data);
  } catch {
    statsError.textContent = "Network error. Could not fetch stats.";
    statsError.classList.remove("hidden");
  }
}

function renderStats(data) {
  document.getElementById("stat-clicks").textContent  = data.click_count.toLocaleString();
  document.getElementById("stat-created").textContent = formatDate(data.created_at);
  document.getElementById("stat-expires").textContent = data.expires_at ? formatDate(data.expires_at) : "Never";

  const longEl = document.getElementById("stat-long-url");
  longEl.textContent = data.long_url;
  longEl.href = data.long_url;

  const tbody = document.getElementById("clicks-tbody");
  tbody.innerHTML = "";
  const noClicks = document.getElementById("no-clicks-msg");
  const table = document.getElementById("clicks-table");

  if (!data.recent_clicks || data.recent_clicks.length === 0) {
    table.classList.add("hidden");
    noClicks.classList.remove("hidden");
  } else {
    table.classList.remove("hidden");
    noClicks.classList.add("hidden");
    data.recent_clicks.forEach((click) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${formatDate(click.accessed_at)}</td>
        <td>${escapeHtml(click.ip_address || "—")}</td>
        <td title="${escapeHtml(click.user_agent || "")}">${escapeHtml(truncate(click.user_agent || "—", 40))}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  statsResult.classList.remove("hidden");
}

// ─── UI Helpers ────────────────────────────────────────────────────────────────
function showResult(data) {
  const url = data.short_url;
  const code = data.alias || data.short_code;

  shortUrlDisplay.textContent = url;
  shortUrlDisplay.href = url;
  shortUrlDisplay.dataset.code = code;

  if (data.expires_at) {
    expiryLabel.textContent = `Expires ${formatDate(data.expires_at)}`;
    expiryLabel.classList.remove("hidden");
  } else {
    expiryLabel.classList.add("hidden");
  }

  resultBox.classList.remove("hidden");
  resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideResult() { resultBox.classList.add("hidden"); }

function showError(msg) {
  errorMessage.textContent = msg;
  errorBox.classList.remove("hidden");
}

function hideError() { errorBox.classList.add("hidden"); }

function setLoading(loading) {
  shortenBtn.disabled = loading;
  btnLabel.classList.toggle("hidden", loading);
  btnSpinner.classList.toggle("hidden", !loading);
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, len) {
  return str.length > len ? str.slice(0, len) + "…" : str;
}
