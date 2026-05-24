// Trinity Local — background.js (service worker)
//
// Receives captured payloads from content-script.js and forwards
// them to the native messaging host (trinity-local-capture-host)
// via chrome.runtime.connectNative.
//
// Chrome spawns the host process on the first connect; the host
// reads length-prefixed JSON from stdin and writes captured turns
// to ~/.trinity/conversations/<provider>/<conv_id>.json. When the
// service worker goes idle and the port disconnects, Chrome reaps
// the host process.
//
// Day 1 (this tick): no adapters yet. We forward the raw captured
// payload to the host with kind="raw"; the host logs it. Day 5
// claude.js adapter normalizes the stream/canonical payloads into
// Trinity's conversation schema before forwarding.

const NATIVE_HOST = "local.trinity.capture";

let port = null;

// ─── Current-tab sync state (survives content-script reloads) ─────────
// The sync orchestrator drives the user's current tab through each
// missing conv_id. State lives here in the service worker because
// content-script context is destroyed on each navigation. The pill
// re-queries us for state when it re-injects via get_current_tab_sync_state.
const CURRENT_TAB_SYNC_STATE = {
  active: false,
  provider: null,
  total: 0,
  landed: 0,
  currentIndex: 0,
  tabId: null,
  originalUrl: null,
  canceled: false,
  finishedAt: 0,
};

const SYNC_NAV_TIMEOUT_MS = 12_000;
const SYNC_CAPTURE_POLL_MS = 500;

function providerThreadUrl(provider, conv_id) {
  if (provider === "claude") return `https://claude.ai/chat/${conv_id}`;
  if (provider === "chatgpt") return `https://chatgpt.com/c/${conv_id}`;
  if (provider === "gemini") return `https://gemini.google.com/app/${conv_id}`;
  return null;
}

function querySyncStatus(provider) {
  return new Promise((resolve) => {
    const payload = { kind: "query", query_kind: "sync_status", provider };
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, payload, (resp) => {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    } catch {
      resolve(null);
    }
  });
}

function pollForCapture(provider, conv_id, deadline) {
  return new Promise((resolve) => {
    (async function poll() {
      if (Date.now() >= deadline || CURRENT_TAB_SYNC_STATE.canceled) {
        return resolve(false);
      }
      const status = await querySyncStatus(provider);
      const stillMissing = status && status.ok && Array.isArray(status.missing_ids)
        ? status.missing_ids.includes(conv_id)
        : true;
      if (!stillMissing) return resolve(true);
      setTimeout(poll, SYNC_CAPTURE_POLL_MS);
    })();
  });
}

async function runCurrentTabSync({ tabId, originalUrl, provider, missing_ids }) {
  Object.assign(CURRENT_TAB_SYNC_STATE, {
    active: true, provider, total: missing_ids.length, landed: 0,
    currentIndex: 0, tabId, originalUrl, canceled: false, finishedAt: 0,
  });

  for (let i = 0; i < missing_ids.length; i++) {
    if (CURRENT_TAB_SYNC_STATE.canceled) break;
    const conv_id = missing_ids[i];
    CURRENT_TAB_SYNC_STATE.currentIndex = i;
    const url = providerThreadUrl(provider, conv_id);
    if (!url) continue;
    try {
      await chrome.tabs.update(tabId, { url });
    } catch {
      break;  // tab probably closed
    }
    const ok = await pollForCapture(
      provider, conv_id, Date.now() + SYNC_NAV_TIMEOUT_MS,
    );
    if (ok) CURRENT_TAB_SYNC_STATE.landed += 1;
  }

  // Restore the user's original URL
  try {
    if (!CURRENT_TAB_SYNC_STATE.canceled) {
      await chrome.tabs.update(tabId, { url: originalUrl });
    }
  } catch { /* tab closed */ }

  CURRENT_TAB_SYNC_STATE.active = false;
  CURRENT_TAB_SYNC_STATE.finishedAt = Date.now();
}

function ensurePort() {
  if (port) return port;
  try {
    port = chrome.runtime.connectNative(NATIVE_HOST);
    port.onMessage.addListener((msg) => {
      console.log("[trinity-bg] host ack", msg);
    });
    port.onDisconnect.addListener(() => {
      const err = chrome.runtime.lastError;
      if (err) {
        console.warn("[trinity-bg] host disconnected:", err.message);
      }
      port = null;
    });
  } catch (e) {
    console.warn("[trinity-bg] connectNative failed", e);
    port = null;
  }
  return port;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // ─── v1.6 capture flow (existing) ─────────────────────────────
  // Content scripts on claude.ai/chatgpt.com/gemini.google.com send
  // {type: "captured", payload: ...} when they observe a conversation.
  if (message?.type === "captured") {
    const p = ensurePort();
    if (!p) {
      console.warn("[trinity-bg] no native host; payload dropped",
                   message.payload?.provider);
      sendResponse({ ok: false, reason: "no-host" });
      return false;
    }
    try {
      p.postMessage({
        kind: "captured",
        payload: message.payload,
        origin_tab_url: sender?.tab?.url,
        received_at: new Date().toISOString(),
      });
      sendResponse({ ok: true });
    } catch (e) {
      console.warn("[trinity-bg] postMessage to host failed", e);
      sendResponse({ ok: false, reason: String(e) });
    }
    return false;
  }

  // ─── Current-tab sync orchestrator (used by sync pill) ──────────────
  // The pill sends start_current_tab_sync; this handler takes over the
  // user's current tab, navigates it through each missing conv_id,
  // polls capture-host for each capture to land, then restores the
  // original URL. State lives here (the service worker survives navi-
  // gations; the pill's content-script context is destroyed on each
  // page load and re-queries us for state when it re-injects).
  //
  // Why current-tab instead of background tabs: user sees the sync
  // happen visually (informative + trustworthy) and there's no tab-bar
  // thrashing. Trade-off: user's tab is "borrowed" during sync. The
  // pill renders a "Syncing N/M — cancel" overlay during the run.
  if (message?.type === "start_current_tab_sync") {
    const senderTabId = sender?.tab?.id;
    const originalUrl = sender?.tab?.url;
    if (!senderTabId || !originalUrl) {
      sendResponse({ ok: false, error: "no-tab-context" });
      return false;
    }
    if (CURRENT_TAB_SYNC_STATE.active) {
      sendResponse({ ok: false, error: "sync-already-running" });
      return false;
    }
    const { provider, missing_ids } = message;
    if (!Array.isArray(missing_ids) || !missing_ids.length) {
      sendResponse({ ok: false, error: "no-missing-ids" });
      return false;
    }
    runCurrentTabSync({
      tabId: senderTabId,
      originalUrl,
      provider,
      missing_ids,
    });
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === "get_current_tab_sync_state") {
    sendResponse({
      ok: true,
      active: CURRENT_TAB_SYNC_STATE.active,
      provider: CURRENT_TAB_SYNC_STATE.provider,
      total: CURRENT_TAB_SYNC_STATE.total,
      landed: CURRENT_TAB_SYNC_STATE.landed,
      current_index: CURRENT_TAB_SYNC_STATE.currentIndex,
      finished_at: CURRENT_TAB_SYNC_STATE.finishedAt,
    });
    return false;
  }
  if (message?.type === "cancel_current_tab_sync") {
    CURRENT_TAB_SYNC_STATE.canceled = true;
    sendResponse({ ok: true });
    return false;
  }

  // ─── Background-tab sync (kept for callers that prefer it) ───────────
  // Gemini blocks iframe-based sync (the bundle detects iframe context
  // and doesn't fire its canonical hNvQHb fetch). Background tabs
  // bypass this: real top-level navigation that triggers the full
  // page-load flow including all auth-injected fetches, while
  // active:false keeps them out of the user's focus.
  if (message?.type === "open_sync_tab") {
    try {
      chrome.tabs.create({ url: message.url, active: false }, (tab) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        sendResponse({ ok: true, tabId: tab?.id });
      });
    } catch (e) {
      sendResponse({ ok: false, error: String(e) });
    }
    return true;
  }
  if (message?.type === "close_sync_tab") {
    try {
      chrome.tabs.remove(message.tabId, () => {
        sendResponse({ ok: !chrome.runtime.lastError });
      });
    } catch {
      sendResponse({ ok: false });
    }
    return true;
  }

  // ─── Read-only query path (new — used by the in-provider sync pill) ──
  // Content scripts ask the host for cheap read-only info like
  // "how many threads in the sidebar aren't captured locally?" Same
  // sendNativeMessage one-shot pattern as actions; the host's
  // QUERY_HANDLERS dispatches on `query_kind`.
  if (message?.type === "query") {
    const { type: _ignore, ...hostPayload } = message;
    hostPayload.kind = "query";  // host gates by kind="query" + query_kind
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, hostPayload, (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: "native-host-unavailable",
                         detail: chrome.runtime.lastError.message });
          return;
        }
        sendResponse(response);
      });
    } catch (e) {
      sendResponse({ ok: false, error: "send-failed", detail: String(e) });
    }
    return true;  // signal async sendResponse
  }

  // ─── Phase 1+3 action-dispatch (new — launchpad bridge) ───────
  // Popup/launchpad sends {type: "action", kind: "launch-council",
  // task: "..."} to invoke a CLI command via Native Messaging. The
  // host's ACTION_ALLOWLIST gates which kinds are runnable; this
  // service worker is a transparent forwarder.
  if (message?.type === "action") {
    const { type: _ignore, ...hostPayload } = message;
    // One-shot request/response (sendNativeMessage spawns a fresh
    // host process per call, exits when message returns). Cleaner
    // for actions than a persistent port — action != streaming.
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, hostPayload, (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({
            ok: false,
            error: "native-host-unavailable",
            detail: chrome.runtime.lastError.message,
            hint: "Run `trinity-local install-extension --extension-id <ID>` to register the Native Messaging manifest.",
          });
          return;
        }
        sendResponse(response);
      });
    } catch (e) {
      sendResponse({ ok: false, error: "send-failed", detail: String(e) });
    }
    return true;  // signal async sendResponse
  }

  return false;
});

// ─── Phase 4: external messaging from the file:// launchpad ───────
// The file launchpad at ~/.trinity/portal_pages/launchpad.html calls
// chrome.runtime.sendMessage(TRINITY_EXTENSION_ID, ...) directly. That
// path uses `onMessageExternal`, NOT `onMessage` — internal popups +
// content scripts use onMessage, externally-connectable pages use the
// External variant. They are NOT interchangeable.
//
// Security gates (codex's Phase 4 verdict, council_fb374b01311885cc):
//   1. sender.url must be the launchpad file URL
//   2. message.type must be in {trinity-ping, action}
//   3. action.kind must clear capture_host's ACTION_ALLOWLIST anyway
//      (defense in depth — the host is the final enforcement)
// Phase 8 hardening (council_bf1ab3f4dd70f75e, codex verdict): the prior
// `url.includes("/.trinity/portal_pages/launchpad.html")` check was
// spoofable by any local file matching the substring, e.g.
// `~/Downloads/.trinity/portal_pages/launchpad.html`. Tighten to require
// the path to END with the launchpad path AND be the user's home
// directory's `.trinity` subtree. Chrome populates `sender.url` itself
// (cannot be forged in the message payload), so a strict suffix match
// closes the spoof window without needing a per-install token (deferred
// until settings actions land — they'd promote the gate to a stronger
// authentication layer).
const LAUNCHPAD_URL_SUFFIX = "/.trinity/portal_pages/launchpad.html";

function isLaunchpadSender(sender) {
  const url = sender?.url || "";
  if (!url.startsWith("file://")) return false;
  // Strip any query/hash so a crafted ?foo=… can't tail the path.
  const cleaned = url.split("?")[0].split("#")[0];
  return cleaned.endsWith(LAUNCHPAD_URL_SUFFIX);
}

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (!isLaunchpadSender(sender)) {
    sendResponse({ ok: false, error: "rejected-sender",
                   detail: "external messages accepted only from the file:// launchpad" });
    return false;
  }
  const messageType = message?.type;

  if (messageType === "trinity-ping") {
    sendResponse({
      ok: true,
      type: "trinity-pong",
      extensionVersion: chrome.runtime.getManifest().version,
    });
    return false;
  }

  if (messageType === "action") {
    const { type: _ignore, ...hostPayload } = message;
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, hostPayload, (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({
            ok: false,
            error: "native-host-unavailable",
            detail: chrome.runtime.lastError.message,
            hint: "Run `trinity-local install-extension --extension-id <ID>` to register the Native Messaging manifest.",
          });
          return;
        }
        sendResponse(response);
      });
    } catch (e) {
      sendResponse({ ok: false, error: "send-failed", detail: String(e) });
    }
    return true;
  }

  sendResponse({ ok: false, error: "unknown-message-type", detail: String(messageType) });
  return false;
});

console.log("[trinity-bg] service worker started (v0.2 — capture + actions + external)");
