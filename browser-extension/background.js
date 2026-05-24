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
