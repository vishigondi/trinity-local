// Trinity Local — sync-pill.js (ISOLATED world)
//
// In-provider awareness UI. Polls the capture host for "how many
// threads are in your sidebar that aren't captured locally yet?"
// for the current host. If > 0, injects a small bottom-right pill:
//
//     ⠕ N to sync
//
// Click → opens the launchpad. Self-suppressing when count is 0 so
// the user only sees it when there's actually something to do.
//
// Per-provider sidebar acquisition runs separately:
//   - claude.ai / chatgpt.com: page-hook.js intercepts the network
//     fetch for the sidebar-list endpoint (kind="sidebar_list") and
//     forwards via "captured" channel.
//   - gemini.google.com: content-script.js scrapes the DOM and emits
//     the same sidebar_list payload (no batchexecute RPC carries it).
//
// This file is only the consumer: it asks the host for the diff
// (sidebar conv_ids - on-disk conv_ids) and renders the count.

(() => {
  const PROVIDER_HOSTS = {
    "claude.ai": "claude",
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
    "gemini.google.com": "gemini",
  };

  const provider = PROVIDER_HOSTS[location.hostname];
  if (!provider) return;

  // Don't re-install if another content-script instance already
  // injected this pill (defensive — Chrome usually injects each
  // content-script once per page, but iframes + history.pushState
  // navigations can replay it).
  if (document.getElementById("__trinity_sync_pill__")) return;

  const PILL_ID = "__trinity_sync_pill__";
  const POLL_INTERVAL_MS = 60_000;  // refresh diff every minute
  const FIRST_POLL_DELAY_MS = 3_000;  // wait for sidebar fetch/scrape to land

  function queryStatus() {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.id) return resolve(null);
      try {
        chrome.runtime.sendMessage(
          { type: "query", query_kind: "sync_status", provider },
          (response) => {
            // chrome.runtime.lastError surfaces here for invalidated
            // contexts + handler errors; treat both as null result.
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

  function ensurePillEl() {
    let el = document.getElementById(PILL_ID);
    if (el) return el;
    ensurePillStyles();
    el = document.createElement("div");
    el.id = PILL_ID;
    el.hidden = true;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", "Trinity sync status");
    el.title = "Trinity: open launchpad to sync missing threads locally";
    el.addEventListener("click", () => {
      // Ask background to open the launchpad. The launchpad path is
      // ~/.trinity/portal_pages/launchpad.html — the background relays
      // an `action: open-launchpad` to the host which knows the path.
      try {
        chrome.runtime.sendMessage(
          { type: "action", kind: "open-launchpad" },
          () => { /* fire-and-forget; user already left this tab logically */ },
        );
      } catch {
        // ignore — clicking shouldn't break anything even if dispatch fails
      }
    });
    (document.body || document.documentElement).appendChild(el);
    return el;
  }

  function renderPill(status) {
    if (!status || !status.ok) return;
    const count = Number(status.missing_count) || 0;
    const el = ensurePillEl();
    if (count <= 0) {
      el.hidden = true;
      return;
    }
    el.textContent = `⠕ ${count} to sync`;
    el.hidden = false;
  }

  async function tick() {
    const status = await queryStatus();
    renderPill(status);
  }

  // First tick after a short delay (let sidebar fetch/scrape land),
  // then refresh on a slow cadence so the pill stays accurate as
  // captures land without spamming the host.
  setTimeout(() => {
    tick();
    setInterval(tick, POLL_INTERVAL_MS);
  }, FIRST_POLL_DELAY_MS);
})();
