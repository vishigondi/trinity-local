// Trinity Local — sync-pill.js (ISOLATED world)
//
// In-provider sync UI. On each page load:
//
//   1) Ask background.js whether a current-tab sync is in flight
//      (background owns the state machine — it survives our content-
//      script being destroyed on every navigation).
//   2) If yes: render the in-flight progress pill.
//   3) If no: query capture-host for sidebar-vs-on-disk diff. If
//      missing > 0, render the "⠕ N to sync" pill. Click starts the
//      current-tab sync.
//
// History:
// - 4b4b05f: direct fetch from content-script (failed — auth headers)
// - b09dadb: iframes (failed for gemini — bundle detects iframe ctx)
// - c11dc9e: background tabs (works but visible tab thrashing)
// - THIS:    current-tab orchestrated by background.js (no tab spam;
//            user watches their own tab tour their conversations,
//            ends back where they started)

(() => {
  // Bail in iframes — all_frames:true means we inject everywhere,
  // including any embedded provider frames. Pill only belongs in
  // the top-level page.
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
  const SYNC_PROGRESS_POLL_MS = 750;     // when sync is in-flight, refresh pill
  const SYNCED_FADE_AFTER_MS = 4_000;

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
      } catch { resolve(null); }
    });
  }

  function getCurrentSyncState() {
    return new Promise((resolve) => {
      if (!chrome?.runtime?.id) return resolve(null);
      try {
        chrome.runtime.sendMessage(
          { type: "get_current_tab_sync_state" },
          (response) => {
            if (chrome.runtime.lastError) return resolve(null);
            resolve(response || null);
          },
        );
      } catch { resolve(null); }
    });
  }

  function startCurrentTabSync(missing_ids) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(
          { type: "start_current_tab_sync", provider, missing_ids },
          (response) => resolve(!!response?.ok),
        );
      } catch { resolve(false); }
    });
  }

  function cancelCurrentTabSync() {
    try {
      chrome.runtime.sendMessage({ type: "cancel_current_tab_sync" }, () => {});
    } catch { /* ignore */ }
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
        display: inline-flex; align-items: center; gap: 8px;
      }
      #${PILL_ID}:hover { opacity: 1.0; }
      #${PILL_ID}[hidden] { display: none !important; }
      #${PILL_ID} .__trinity_cancel {
        background: rgba(245, 239, 227, 0.15); border: 0; color: inherit;
        font: inherit; padding: 0 8px; border-radius: 999px; cursor: pointer;
      }
      #${PILL_ID} .__trinity_cancel:hover { background: rgba(245, 239, 227, 0.3); }
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
    el.setAttribute("role", "status");
    (document.body || document.documentElement).appendChild(el);
    return el;
  }

  function renderIdle(missingCount, missingIds) {
    const el = ensurePillEl();
    if (missingCount <= 0) { el.hidden = true; return; }
    el.replaceChildren();  // clear (no innerHTML; XSS-safe)
    el.textContent = `⠕ ${missingCount} to sync`;
    el.title = "Trinity: click to sync missing threads into this tab";
    el.style.cursor = "pointer";
    el.onclick = async () => {
      el.onclick = null;
      el.textContent = `⠕ Starting…`;
      await startCurrentTabSync(missingIds);
      // Background will navigate this tab almost immediately; pill
      // re-renders in the next page-load lifecycle.
    };
    el.hidden = false;
  }

  function renderActive(state) {
    const el = ensurePillEl();
    el.replaceChildren();
    el.style.cursor = "default";
    el.removeAttribute("title");
    el.appendChild(document.createTextNode(
      `⠕ Syncing ${state.landed}/${state.total}…`,
    ));
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "__trinity_cancel";
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = (e) => { e.stopPropagation(); cancelCurrentTabSync(); };
    el.appendChild(cancelBtn);
    el.hidden = false;
  }

  function renderJustFinished(state) {
    const el = ensurePillEl();
    el.replaceChildren();
    el.style.cursor = "default";
    el.textContent = state.landed === state.total
      ? `⠕ ✓ Synced ${state.landed}`
      : `⠕ ✓ Synced ${state.landed}/${state.total}`;
    el.hidden = false;
    setTimeout(() => {
      const live = document.getElementById(PILL_ID);
      if (live) live.hidden = true;
    }, SYNCED_FADE_AFTER_MS);
  }

  async function tick() {
    // 1) Sync in flight? Render progress, schedule fast re-tick.
    const syncState = await getCurrentSyncState();
    if (syncState && syncState.active && syncState.provider === provider) {
      renderActive(syncState);
      setTimeout(tick, SYNC_PROGRESS_POLL_MS);
      return;
    }
    // 1b) Recently finished? Show the success banner briefly, once.
    if (
      syncState && !syncState.active && syncState.provider === provider &&
      syncState.finished_at && (Date.now() - syncState.finished_at < 10_000) &&
      syncState.total > 0
    ) {
      renderJustFinished(syncState);
      return;
    }
    // 2) No sync in flight — render the idle "N to sync" pill from
    //    the sidebar-vs-on-disk diff.
    const status = await queryStatus();
    if (!status || !status.ok) return;
    renderIdle(Number(status.missing_count) || 0, status.missing_ids || []);
  }

  setTimeout(() => {
    tick();
    setInterval(tick, POLL_INTERVAL_MS);
  }, FIRST_POLL_DELAY_MS);
})();
