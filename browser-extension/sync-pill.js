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
  const IFRAME_LOAD_MS = 6_000;          // wait per-iframe for canonical fetch to fire
  const IFRAME_GAP_MS = 500;             // pause between iframes — gentle on provider API
  const SYNCED_FADE_AFTER_MS = 4_000;    // brief success banner before hide

  let syncing = false;

  function providerThreadUrl(conv_id) {
    if (provider === "claude") return `${location.origin}/chat/${conv_id}`;
    if (provider === "chatgpt") return `${location.origin}/c/${conv_id}`;
    if (provider === "gemini") return `${location.origin}/app/${conv_id}`;
    return null;
  }

  function spawnSyncIframe(conv_id) {
    return new Promise((resolve) => {
      const url = providerThreadUrl(conv_id);
      if (!url) return resolve(false);
      const iframe = document.createElement("iframe");
      iframe.style.cssText =
        "position:absolute;width:1px;height:1px;opacity:0;visibility:hidden;pointer-events:none;border:0;top:-9999px;";
      iframe.setAttribute("aria-hidden", "true");
      iframe.dataset.trinitySync = "1";

      let finished = false;
      const finish = (ok) => {
        if (finished) return;
        finished = true;
        try { iframe.remove(); } catch {}
        resolve(ok);
      };

      iframe.onload = () => {
        // Provider's bundle loads, fires its own auth-injected canonical
        // fetch which page-hook (now in this iframe via all_frames:true)
        // catches. Give it a window to land, then destroy.
        setTimeout(() => finish(true), IFRAME_LOAD_MS);
      };
      iframe.onerror = () => finish(false);
      // Safety timeout in case onload never fires (X-Frame-Options / CSP)
      setTimeout(() => finish(false), IFRAME_LOAD_MS + 4_000);

      iframe.src = url;
      document.body.appendChild(iframe);
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
    let done = 0;
    const updatePill = () => {
      if (!el) return;
      el.textContent = `⠕ Syncing ${done}/${total}…`;
    };
    updatePill();

    // Concurrency = 1 (gentle, looks like a single normal user
    // browsing thread-by-thread). For 20-30 threads that's 2-3 minutes;
    // acceptable for a one-click backfill.
    for (const conv_id of missing_ids) {
      await spawnSyncIframe(conv_id);
      done += 1;
      updatePill();
      if (done < total) {
        await new Promise((r) => setTimeout(r, IFRAME_GAP_MS));
      }
    }

    // Re-query the host to see how many ACTUALLY landed (in case some
    // iframes failed silently — X-Frame, network, etc.). The honest
    // success count is the diff between before/after.
    const after = await queryStatus();
    const actualSynced = after && after.ok
      ? Math.max(0, total - Number(after.missing_count || 0))
      : total;

    if (el) {
      el.textContent = actualSynced === total
        ? `⠕ ✓ Synced ${total}`
        : `⠕ ✓ Synced ${actualSynced}/${total}`;
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
