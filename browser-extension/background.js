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

console.log("[trinity-bg] service worker started (v0.2 — capture + actions)");
