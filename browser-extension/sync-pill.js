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
  // CRITICAL: bail in iframes. With manifest's `all_frames: true` we
  // also inject into iframes — including the ones THIS pill creates
  // during a sync. Without this guard, each sync iframe would mount
  // its own pill, query its own sync_status, kick off its own
  // sync iframes, etc. Infinite recursion.
  if (window !== window.top) return;

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
  const SYNC_CONCURRENCY = 2;             // parallel background tabs (gentle)
  const CONFIRM_POLL_MS = 500;            // disk-confirmation poll cadence
  const PER_TAB_TIMEOUT_MS = 12_000;      // give up if no capture lands in 12s
                                           // (tabs need longer than iframes —
                                           // full page-load including JS bundle)
  const SYNCED_FADE_AFTER_MS = 4_000;     // brief success banner before hide

  let syncing = false;

  function providerThreadUrl(conv_id) {
    if (provider === "claude") return `${location.origin}/chat/${conv_id}`;
    if (provider === "chatgpt") return `${location.origin}/c/${conv_id}`;
    if (provider === "gemini") return `${location.origin}/app/${conv_id}`;
    return null;
  }

  function openSyncTab(url) {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.id) return resolve(null);
      try {
        chrome.runtime.sendMessage({ type: "open_sync_tab", url }, (resp) => {
          if (chrome.runtime.lastError) return resolve(null);
          resolve(resp?.ok ? resp.tabId : null);
        });
      } catch {
        resolve(null);
      }
    });
  }

  function closeSyncTab(tabId) {
    if (tabId == null) return;
    try {
      chrome.runtime.sendMessage({ type: "close_sync_tab", tabId }, () => {});
    } catch { /* tab might already be gone */ }
  }

  // Open the conv_id in a background tab + poll capture-host every
  // CONFIRM_POLL_MS for it to land. Resolve true when it lands
  // (early-exit, destroy tab), false on timeout (destroy tab anyway).
  // Honest signal: success means a capture file exists on disk.
  //
  // Background tabs instead of iframes because gemini's bundle
  // detects iframe context and skips the canonical hNvQHb fetch
  // (verified 2026-05-23 — gemini iframes captured ZERO conv_ids
  // beyond the ones already on disk). Tabs use real top-level
  // navigation which fires the full page-load flow including all
  // auth-injected fetches. active:false keeps them out of focus.
  // Claude + chatgpt also moved off iframes to keep one code path.
  function syncOne(conv_id) {
    return new Promise(async (resolve) => {
      const url = providerThreadUrl(conv_id);
      if (!url) return resolve(false);
      const tabId = await openSyncTab(url);
      if (tabId == null) return resolve(false);

      let settled = false;
      const settle = (ok) => {
        if (settled) return;
        settled = true;
        closeSyncTab(tabId);
        resolve(ok);
      };

      const startedAt = Date.now();
      const poll = async () => {
        if (settled) return;
        const status = await queryStatus();
        const stillMissing = status && status.ok && Array.isArray(status.missing_ids)
          ? status.missing_ids.includes(conv_id)
          : true;
        if (!stillMissing) return settle(true);
        if (Date.now() - startedAt >= PER_TAB_TIMEOUT_MS) {
          return settle(false);
        }
        setTimeout(poll, CONFIRM_POLL_MS);
      };
      setTimeout(poll, CONFIRM_POLL_MS);
    });
  }

  async function runSync(missing_ids) {
    if (syncing) return;
    syncing = true;
    const el = document.getElementById(PILL_ID);
    if (el) {
      el.style.cursor = "default";
      el.removeAttribute("title");
    }
    const total = missing_ids.length;
    let landed = 0;
    let attempted = 0;
    const updatePill = () => {
      if (!el) return;
      el.textContent = `⠕ Syncing ${landed}/${total}…`;
    };
    updatePill();

    // Worker-pool pattern: SYNC_CONCURRENCY workers each pull from
    // the queue. Each call to syncOne() spawns one iframe + waits
    // for its capture to land (or times out). Workers exit when the
    // queue is empty.
    const queue = [...missing_ids];
    const workers = Array.from({ length: SYNC_CONCURRENCY }, async () => {
      while (queue.length > 0) {
        const conv_id = queue.shift();
        attempted += 1;
        const ok = await syncOne(conv_id);
        if (ok) landed += 1;
        updatePill();
      }
    });
    await Promise.all(workers);

    if (el) {
      el.textContent = landed === total
        ? `⠕ ✓ Synced ${landed}`
        : `⠕ ✓ Synced ${landed}/${total}`;
      setTimeout(() => {
        const live = document.getElementById(PILL_ID);
        if (live) live.hidden = true;
      }, SYNCED_FADE_AFTER_MS);
    }
    syncing = false;
  }

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
    const missing_ids = status.missing_ids || [];

    const el = ensurePillEl(() => {
      if (syncing) return;
      runSync(missing_ids);
    });

    if (count <= 0 || syncing) {
      if (!syncing) el.hidden = true;
      return;
    }
    el.textContent = `⠕ ${count} to sync`;
    el.title = "Trinity: click to sync missing threads locally";
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
