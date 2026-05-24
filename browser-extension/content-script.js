// Trinity Local — content-script.js (ISOLATED world)
//
// Bridge between the MAIN-world page-hook.js (which can intercept
// the page's fetch calls) and the extension's background service
// worker (which holds the chrome.runtime.connectNative connection
// to the local capture host).
//
// Why two scripts: MV3's ISOLATED-world content scripts cannot
// monkey-patch window.fetch (they get their own window object).
// The MAIN-world script can patch fetch but cannot use chrome.* APIs.
// So we relay: page-hook emits via window.postMessage → here →
// chrome.runtime.sendMessage → background.

window.addEventListener("message", (event) => {
  // Only accept messages from the same page and from our own hook.
  if (event.source !== window) return;
  if (!event.data || event.data.source !== "trinity-hook") return;

  const payload = event.data.payload;
  if (!payload) return;

  // Guard against "Extension context invalidated" — when the user
  // reloads the extension in chrome://extensions, every previously-
  // injected content-script keeps running in already-open tabs but
  // loses access to chrome.* APIs. Reading chrome.runtime.id is the
  // canonical check: it returns undefined once the context is gone.
  // Without this guard, every postMessage from page-hook throws and
  // spams the page console (caught 2026-05-23 on gemini.google.com
  // after reload).
  if (!chrome?.runtime?.id) return;

  try {
    chrome.runtime.sendMessage({ type: "captured", payload }).catch((err) => {
      // Service worker may be asleep; chrome wakes it on sendMessage.
      // Genuine errors land here — log but don't break the page.
      console.warn("[trinity-content] sendMessage failed", err);
    });
  } catch (e) {
    // sendMessage can throw synchronously on context invalidation
    // (vs returning a rejected promise) depending on Chrome version.
    // Both paths reach here; we swallow to keep the page clean.
  }
});
