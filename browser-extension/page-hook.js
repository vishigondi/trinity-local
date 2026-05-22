// Trinity Local — page-hook.js (MAIN world)
//
// Wraps window.fetch so we can observe the page's own API calls to
// Anthropic / OpenAI / Google streaming endpoints. Per the v1.6 spec
// validation log (T-1, 2026-05-14): EventSource is NOT used by
// claude.ai — all streaming goes through fetch() + response.body
// .getReader() because the completion endpoints are POST and
// EventSource is GET-only per the W3C spec.
//
// This file runs in the MAIN world (per manifest.json content_scripts
// entry with "world": "MAIN", Chrome 111+). The ISOLATED-world
// content-script.js cannot intercept page-level network calls.
//
// Capture strategy: wrap fetch. On streaming responses, tee the body
// so the page sees the original stream AND we accumulate a copy.
// When the stream completes, postMessage the accumulated payload to
// the ISOLATED-world content script via window.postMessage. Content
// script forwards to the background service worker.

(() => {
  if (window.__TRINITY_HOOK_INSTALLED__) return;
  window.__TRINITY_HOOK_INSTALLED__ = true;

  const PROVIDER_PATTERNS = [
    { provider: "claude", host: "claude.ai", streamPath: "/completion" },
    { provider: "chatgpt", host: "chatgpt.com", streamPath: "/backend-api/conversation" },
    { provider: "chatgpt", host: "chat.openai.com", streamPath: "/backend-api/conversation" },
    { provider: "gemini", host: "gemini.google.com", streamPath: "/_/BardChatUi/data/batchexecute" },
  ];

  function classifyRequest(url, method) {
    try {
      const u = new URL(url, location.href);
      for (const pat of PROVIDER_PATTERNS) {
        if (u.hostname === pat.host || location.hostname === pat.host) {
          if (u.pathname.includes(pat.streamPath) || u.pathname === pat.streamPath) {
            return { provider: pat.provider, kind: "stream" };
          }
          // Canonical fetch endpoints — non-streaming GETs that return
          // the full conversation tree. claude.ai: /chat_conversations/<id>
          // (no trailing /completion). chatgpt.com: /backend-api/conversation/<id>.
          if (pat.provider === "claude" && /\/chat_conversations\/[^/]+$/.test(u.pathname)) {
            return { provider: "claude", kind: "canonical" };
          }
          if (pat.provider === "chatgpt" && /\/backend-api\/conversation\/[^/]+$/.test(u.pathname) && method === "GET") {
            return { provider: "chatgpt", kind: "canonical" };
          }
        }
      }
    } catch (e) {
      // URL parse failed; ignore
    }
    return null;
  }

  function emit(payload) {
    // Send to ISOLATED-world content script via window.postMessage.
    // The 'source' field is the discriminator the content script uses
    // to filter out unrelated postMessages (which are common on these
    // sites — they all use postMessage internally).
    window.postMessage({ source: "trinity-hook", payload }, location.origin);
  }

  const originalFetch = window.fetch;
  window.fetch = async function trinityFetch(input, init) {
    const url = typeof input === "string" ? input : input?.url;
    const method = (init?.method || (typeof input !== "string" && input?.method) || "GET").toUpperCase();
    const classification = classifyRequest(url, method);

    // Snapshot request body BEFORE awaiting the fetch — Gemini's
    // batchexecute RPC is reply-only on the response side, so the
    // user's prompt only lives in the request body. Best-effort:
    // serialize init.body if it's a string or URLSearchParams. Other
    // shapes (FormData, Blob, ReadableStream) are skipped — adapter
    // handles missing request_body gracefully.
    let request_body = null;
    if (classification && init && init.body !== undefined && init.body !== null) {
      try {
        if (typeof init.body === "string") {
          request_body = init.body;
        } else if (init.body instanceof URLSearchParams) {
          request_body = init.body.toString();
        }
      } catch {
        request_body = null;
      }
    }

    const response = await originalFetch.apply(this, arguments);

    if (!classification || !response.ok) {
      return response;
    }

    // Tee the body so the page reads the original; we read a clone.
    // response.clone() is the standard way; the clone has its own
    // independent reader pulling from the same underlying source.
    let captured;
    try {
      captured = response.clone();
    } catch (e) {
      // Some browsers refuse to clone once consumed; bail silently.
      return response;
    }

    // Don't block the page. Read the captured body in the background
    // and emit when it finishes. The page's response is returned
    // immediately and reads from its own buffered copy.
    (async () => {
      try {
        if (classification.kind === "stream") {
          const reader = captured.body.getReader();
          const decoder = new TextDecoder("utf-8");
          let buf = "";
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
          }
          const captured_at = new Date().toISOString();
          // Dispatch through the provider's adapter if loaded
          // (adapters/<provider>.js runs before page-hook.js and
          // registers on window.__TRINITY_ADAPTERS). The adapter
          // normalizes the SSE delta stream into a structured payload
          // the host can write directly. Fallback: emit raw if no
          // adapter is registered for this provider.
          const adapter = window.__TRINITY_ADAPTERS?.[classification.provider];
          if (adapter?.adapt) {
            // page_href lets gemini.js extract conv_id from the user's
            // open conversation (the batchexecute URL itself doesn't
            // carry one). request_body carries the user prompt for
            // gemini (whose response is reply-only). Other adapters
            // ignore extra fields.
            emit(adapter.adapt({ url, body_text: buf, method, captured_at, page_href: location.href, request_body }));
          } else {
            emit({
              provider: classification.provider,
              kind: "stream",
              url,
              method,
              body_text: buf,
              captured_at,
            });
          }
        } else if (classification.kind === "canonical") {
          const json = await captured.json();
          emit({
            provider: classification.provider,
            kind: "canonical",
            url,
            method,
            conversation: json,
            captured_at: new Date().toISOString(),
          });
        }
      } catch (e) {
        // Capture must never break the page. Swallow.
        console.warn("[trinity-hook] capture failed", e);
      }
    })();

    return response;
  };

  console.log("[trinity-hook] fetch wrapper installed on", location.hostname);
})();
