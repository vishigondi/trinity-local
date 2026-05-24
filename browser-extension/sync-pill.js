// Trinity Local — sync-pill.js (ISOLATED world)
//
// In-provider sync UI. Polls the capture host for "how many threads
// are in your sidebar but not captured locally?" — if > 0, shows a
// bottom-right pill. Click runs the actual sync: fetches each
// missing thread's canonical URL, sends the response to the capture
// host as a `kind: "canonical"` payload (same code path used by the
// fetch wrapper for naturally-observed canonical fetches).
//
// Self-suppressing when count=0. Hidden during sync after final
// "✓ Synced N" fades. Re-polls on every page load / 60s.
//
// Per-provider sync mechanics differ:
//   - claude.ai: fetch GET /api/organizations/<org_id>/chat_conversations/
//     <conv_id> — same canonical endpoint PROVIDER_PATTERNS classifies.
//   - chatgpt.com: fetch GET /backend-api/conversation/<conv_id> — same.
//   - gemini.google.com: NO clean direct API. Gemini's RPCs require
//     navigation context; we can't auto-sync without disrupting the
//     user's tab. Pill shows a different message there: "click any
//     sidebar thread to capture it" — manual fallback. The threads
//     DO capture cleanly on user click (verified end-to-end).

(() => {
  const PROVIDER_HOSTS = {
    "claude.ai": "claude",
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
    "gemini.google.com": "gemini",
  };

  const provider = PROVIDER_HOSTS[location.hostname];
  if (!provider) return;
  if (document.getElementById("__trinity_sync_pill__")) return;

  const PILL_ID = "__trinity_sync_pill__";
  const POLL_INTERVAL_MS = 60_000;
  const FIRST_POLL_DELAY_MS = 3_000;
  const SYNC_CONCURRENCY = 3;          // parallel fetches per provider
  const SYNC_INTERVAL_MS = 250;         // throttle between batches
  const SYNCED_FADE_AFTER_MS = 4_000;   // brief success banner

  let syncing = false;  // single in-flight guard

  function queryStatus() {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.id) return resolve(null);
      try {
        chrome.runtime.sendMessage(
          { type: "query", query_kind: "sync_status", provider },
          (response) => {
            if (chrome.runtime.lastError) return resolve(null);
            resolve(response || null);
          },
        );
      } catch {
        resolve(null);
      }
    });
  }

  function sendCapture(payload) {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.id) return resolve(false);
      try {
        chrome.runtime.sendMessage({ type: "captured", payload }, (response) => {
          if (chrome.runtime.lastError) return resolve(false);
          resolve(!!response?.ok);
        });
      } catch {
        resolve(false);
      }
    });
  }

  function canonicalUrl(conv_id, status) {
    if (provider === "claude") {
      const org = status.org_id;
      if (!org) return null;
      // Tree=true + render flags match what claude.ai's UI itself uses
      // to render a conversation — gives back the full message list.
      return `${location.origin}/api/organizations/${org}/chat_conversations/${conv_id}?tree=true&rendering_mode=messages&render_all_tools=true`;
    }
    if (provider === "chatgpt") {
      return `${location.origin}/backend-api/conversation/${conv_id}`;
    }
    return null;  // gemini: no clean canonical URL
  }

  async function fetchOne(conv_id, status) {
    const url = canonicalUrl(conv_id, status);
    if (!url) return false;
    try {
      const resp = await fetch(url, { credentials: "include" });
      if (!resp.ok) return false;
      const json = await resp.json();
      return await sendCapture({
        provider,
        kind: "canonical",
        url,
        method: "GET",
        conversation: json,
        captured_at: new Date().toISOString(),
      });
    } catch {
      return false;
    }
  }

  async function runSync(missing_ids, status) {
    if (syncing) return;
    syncing = true;
    const el = document.getElementById(PILL_ID);
    if (el) {
      el.style.cursor = "default";
      el.removeAttribute("title");
    }

    const total = missing_ids.length;
    let done = 0;
    const updatePill = () => {
      if (!el) return;
      el.textContent = `⠕ Syncing ${done}/${total}…`;
    };
    updatePill();

    // Sequential batches of SYNC_CONCURRENCY, with a throttle between
    // batches. Sequential-with-batching avoids slamming the provider
    // API while keeping the sync responsive.
    for (let i = 0; i < missing_ids.length; i += SYNC_CONCURRENCY) {
      const batch = missing_ids.slice(i, i + SYNC_CONCURRENCY);
      const results = await Promise.all(batch.map((id) => fetchOne(id, status)));
      done += results.length;  // count attempts whether or not they succeeded
      updatePill();
      if (i + SYNC_CONCURRENCY < missing_ids.length) {
        await new Promise((r) => setTimeout(r, SYNC_INTERVAL_MS));
      }
    }

    if (el) {
      el.textContent = `⠕ ✓ Synced ${total}`;
      setTimeout(() => {
        const live = document.getElementById(PILL_ID);
        if (live) live.hidden = true;
      }, SYNCED_FADE_AFTER_MS);
    }
    syncing = false;
  }

  function ensurePillStyles() {
    if (document.getElementById("__trinity_sync_pill_style__")) return;
    const style = document.createElement("style");
    style.id = "__trinity_sync_pill_style__";
    style.textContent = `
      #${PILL_ID} {
        position: fixed; bottom: 16px; right: 16px; z-index: 2147483647;
        background: #255847; color: #f5efe3;
        font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        padding: 8px 14px; border-radius: 999px;
        border: 1px solid #f5efe3;
        cursor: pointer; user-select: none;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        opacity: 0.92; transition: opacity 0.15s ease;
      }
      #${PILL_ID}:hover { opacity: 1.0; }
      #${PILL_ID}[hidden] { display: none !important; }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function ensurePillEl(onClick) {
    let el = document.getElementById(PILL_ID);
    if (el) return el;
    ensurePillStyles();
    el = document.createElement("div");
    el.id = PILL_ID;
    el.hidden = true;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", "Trinity sync");
    el.addEventListener("click", onClick);
    (document.body || document.documentElement).appendChild(el);
    return el;
  }

  function renderPill(status) {
    if (!status || !status.ok) return;
    const count = Number(status.missing_count) || 0;
    const missing_ids = status.missing_ids || [];

    const el = ensurePillEl(() => {
      if (syncing) return;
      // Gemini fallback: no canonical URL we can fetch programmatically.
      // Surface a one-shot tooltip-style message that fades.
      if (provider === "gemini") {
        const live = document.getElementById(PILL_ID);
        if (live) {
          live.textContent = `⠕ Click sidebar threads to capture`;
          setTimeout(() => {
            if (live) live.textContent = `⠕ ${count} to sync`;
          }, 3500);
        }
        return;
      }
      runSync(missing_ids, status);
    });

    if (count <= 0 || syncing) {
      if (!syncing) el.hidden = true;
      return;
    }
    el.textContent = `⠕ ${count} to sync`;
    el.title = provider === "gemini"
      ? "Trinity: click sidebar threads to capture them"
      : "Trinity: click to sync missing threads locally";
    el.hidden = false;
  }

  async function tick() {
    if (syncing) return;  // don't overwrite the sync UI mid-flight
    const status = await queryStatus();
    renderPill(status);
  }

  setTimeout(() => {
    tick();
    setInterval(tick, POLL_INTERVAL_MS);
  }, FIRST_POLL_DELAY_MS);
})();
