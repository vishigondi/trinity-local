// Trinity Local — sync-pill.js (ISOLATED world)
//
// In-provider awareness UI. Polls the capture host for "how many
// threads are in your sidebar but not captured locally?" — if > 0,
// shows a bottom-right pill. Click opens the launchpad (the actual
// sync mechanic lives there until the iframe-based per-provider
// auto-sync ships).
//
// History: 4b4b05f shipped a sync-on-click that fetched canonical
// URLs from content-script context. Verified 2026-05-23 against
// chatgpt.com — fetches returned 404 "conversation_inaccessible"
// because provider APIs require Bearer auth headers that the
// provider's own fetch wrapper injects; our content-script fetch
// bypasses that wrapper and so authenticates as logged-out. Same
// architecture for claude (different shape, same problem) and
// gemini (no direct fetch path at all).
//
// Correct fix is iframe-based: open hidden iframes pointed at each
// missing conv_id's canonical URL, let the provider's own bundle
// load (with its own auth-injecting fetch wrapper), page-hook in
// MAIN-world of the iframe (needs all_frames: true) catches the
// natural canonical fetch, captures land. Tracked as a follow-up.
//
// Until then: pill shows the count, click opens launchpad.
// Self-suppressing when count=0. Re-polls on every page load / 60s.

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

    const el = ensurePillEl(() => {
      // Click opens the launchpad — actual sync mechanic lives there
      // until the iframe-based per-provider auto-sync ships (the
      // direct-fetch approach failed because provider APIs require
      // Bearer auth headers their own bundles inject; our content-
      // script fetch bypasses that wrapper and so authenticates as
      // logged-out).
      try {
        chrome.runtime.sendMessage(
          { type: "action", kind: "open-launchpad" },
          () => { /* fire-and-forget */ },
        );
      } catch {
        // ignore — clicking shouldn't break anything even if dispatch fails
      }
    });

    if (count <= 0) {
      el.hidden = true;
      return;
    }
    el.textContent = `⠕ ${count} to sync`;
    el.title = "Trinity: open launchpad to sync missing threads";
    el.hidden = false;
  }

  async function tick() {
    const status = await queryStatus();
    renderPill(status);
  }

  setTimeout(() => {
    tick();
    setInterval(tick, POLL_INTERVAL_MS);
  }, FIRST_POLL_DELAY_MS);
})();
