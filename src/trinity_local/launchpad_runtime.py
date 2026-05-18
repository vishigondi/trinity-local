from __future__ import annotations


def launchpad_runtime_js() -> str:
    """Shared JS runtime block injected into Launchpad and live council pages."""
    return """
window.__TRINITY_COUNCIL_STATUS__ = window.__TRINITY_COUNCIL_STATUS__ || {};

window.addEventListener('pageshow', (event) => {
  const navEntry = typeof performance.getEntriesByType === 'function'
    ? performance.getEntriesByType('navigation')[0]
    : null;
  if (event.persisted || navEntry?.type === 'back_forward') {
    window.location.reload();
  }
});

// buildShortcutUrl: retired no-op as of 2026-05-18 (W — Pass B JS).
// The macOS Shortcut dispatcher was killed in Pass A (commit 53db635);
// Tier-2 branch in __TRINITY_DISPATCH__.dispatch is gone (Chrome
// extension is the only live dispatch path). buildShortcutUrl()
// survives as a no-op that returns '' so that callsites in
// launchpad_template.py and council_review.py keep parsing — they
// pass the empty string into dispatch() which now ignores it.
function buildShortcutUrl(payload) { return ''; }

function navigateToReviewPath(path) {
  if (!path) {
    return;
  }
  if (/^(file|https?):\\/\\//.test(path)) {
    window.location.replace(path);
    return;
  }
  if (window.location.protocol === 'file:') {
    window.location.replace(`file://${path}`);
    return;
  }
  if (path.includes('/review_pages/')) {
    const parts = path.split('/review_pages/');
    window.location.replace(`../review_pages/${parts[parts.length - 1]}`);
    return;
  }
  window.location.replace(path);
}

function loadStatusScript(token, onComplete) {
  const base = (typeof pageData !== 'undefined' && pageData.statusScriptBaseUrl) || '';
  if (!base || !token) {
    onComplete(null);
    return;
  }
  delete window.__TRINITY_COUNCIL_STATUS__[token];
  const script = document.createElement('script');
  // file:// URLs don't honor query-string cache busters — browsers look for
  // a literal file named `foo.js?t=…` and 404. Only append the buster on
  // http(s):// so the local server can refresh between polls.
  // Page-data URLs are now relative (work under both file:// and localhost),
  // so we can't sniff the protocol from `base`. Use the document's protocol
  // instead — file:// is the trigger, regardless of how `base` is shaped.
  const isFile = window.location.protocol === 'file:';
  const cacheBuster = isFile ? '' : (base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`);
  script.src = `${base}/council_status_${encodeURIComponent(token)}.js${cacheBuster}`;
  script.async = true;
  script.onload = () => {
    const status = window.__TRINITY_COUNCIL_STATUS__?.[token];
    onComplete(status || null);
    script.remove();
  };
  script.onerror = () => {
    onComplete(null);
    script.remove();
  };
  document.body.appendChild(script);
}

window.__TRINITY_COUNCIL_OUTCOME__ = window.__TRINITY_COUNCIL_OUTCOME__ || {};

function loadOutcomeScript(councilId, onComplete) {
  const base = (typeof pageData !== 'undefined' && pageData.outcomeScriptBaseUrl) || '';
  if (!base || !councilId) {
    onComplete(null);
    return;
  }
  delete window.__TRINITY_COUNCIL_OUTCOME__[councilId];
  const script = document.createElement('script');
  // file:// URLs treat `?t=…` as part of the literal filename, so the
  // browser 404s `foo.js?t=174…`. Skip cache-busting on file://.
  // Page-data URLs are now relative (work under both file:// and localhost),
  // so we can't sniff the protocol from `base`. Use the document's protocol
  // instead — file:// is the trigger, regardless of how `base` is shaped.
  const isFile = window.location.protocol === 'file:';
  const cacheBuster = isFile ? '' : (base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`);
  script.src = `${base}/${encodeURIComponent(councilId)}.js${cacheBuster}`;
  script.async = true;
  script.onload = () => {
    const outcome = window.__TRINITY_COUNCIL_OUTCOME__?.[councilId];
    onComplete(outcome || null);
    script.remove();
  };
  script.onerror = () => {
    onComplete(null);
    script.remove();
  };
  document.body.appendChild(script);
}

// ─── Phase 4 dispatch runtime ─────────────────────────────────────
// Routes button clicks across three tiers in priority order:
//   1. Chrome extension present  → chrome.runtime.sendMessage(id, …)
//   2. macOS Shortcut installed  → shortcuts:// URL (existing path)
//   3. Neither                   → install banner
//
// Verdict: council_fb374b01311885cc (codex won). The detection cannot
// be synchronous from file:// JS, so we warm-probe on page load and
// cache in sessionStorage. Native-host-unavailable surfaces the
// install-extension hint inline rather than silently falling through
// to Shortcuts — silent fallback masks the setup bug.
window.__TRINITY_DISPATCH__ = window.__TRINITY_DISPATCH__ || (function() {
  const PROBE_TIMEOUT_MS = 1500;
  const CACHE_KEY = 'trinityDispatchState';
  const ext = (typeof pageData !== 'undefined' && pageData.browserExtension) || {};
  const extensionId = ext.extensionId || null;
  let state = sessionStorage.getItem(CACHE_KEY) || (extensionId ? 'unknown' : 'absent');
  let lastProbedAt = 0;
  const listeners = new Set();

  function setState(next) {
    if (next === state) return;
    state = next;
    try { sessionStorage.setItem(CACHE_KEY, state); } catch (_) {}
    listeners.forEach((cb) => { try { cb(state); } catch (_) {} });
  }

  function sendExt(message) {
    return new Promise((resolve, reject) => {
      if (!extensionId || !window.chrome?.runtime?.sendMessage) {
        reject(new Error('extension-unconfigured'));
        return;
      }
      const timer = setTimeout(() => reject(new Error('extension-timeout')),
                               PROBE_TIMEOUT_MS);
      try {
        chrome.runtime.sendMessage(extensionId, message, (response) => {
          clearTimeout(timer);
          const err = chrome.runtime.lastError;
          if (err) { reject(new Error(err.message)); return; }
          resolve(response);
        });
      } catch (e) {
        clearTimeout(timer);
        reject(e);
      }
    });
  }

  async function probe(force) {
    if (!extensionId) {
      setState('absent');
      return state;
    }
    const stale = (Date.now() - lastProbedAt) > 30_000;
    if (!force && state === 'present' && !stale) return state;
    lastProbedAt = Date.now();
    try {
      const r = await sendExt({ type: 'trinity-ping' });
      if (r && r.ok) setState('present');
      else setState('absent');
    } catch (_) {
      setState('absent');
    }
    return state;
  }

  async function dispatch({ extensionAction, onResult }) {
    // Tier 1 — Chrome extension Native Messaging. Tier-2 macOS Shortcut
    // was retired pre-launch (commit 53db635 + this commit's JS cleanup).
    if (state !== 'absent' && extensionId && extensionAction) {
      try {
        const r = await sendExt({ type: 'action', ...extensionAction });
        setState('present');
        if (r && r.ok) {
          onResult && onResult({ tier: 'extension', ok: true, response: r });
          return { tier: 'extension', ok: true, response: r };
        }
        // Extension reached the host but action failed. Surface the error
        // — never silently swallow native-host-unavailable; the user
        // needs to fix the install.
        if (r && r.error === 'native-host-unavailable') {
          setState('native-missing');
          onResult && onResult({ tier: 'extension', ok: false, response: r,
                                 reason: 'native-host-unavailable' });
          return { tier: 'extension', ok: false, response: r };
        }
        onResult && onResult({ tier: 'extension', ok: false, response: r });
        return { tier: 'extension', ok: false, response: r };
      } catch (e) {
        // Extension not installed / no listener / timeout — fall through.
        setState('absent');
      }
    }
    // Tier 2 (install prompt) — neither path available.
    onResult && onResult({ tier: 'install-prompt', ok: false });
    return { tier: 'install-prompt', ok: false };
  }

  function onStateChange(cb) { listeners.add(cb); return () => listeners.delete(cb); }

  // Warm probe on script load + on focus when stale or unknown.
  if (extensionId) {
    setTimeout(() => probe(false), 50);
    window.addEventListener('focus', () => {
      if (state !== 'present' || (Date.now() - lastProbedAt) > 30_000) {
        probe(false);
      }
    });
  }

  return { dispatch, probe, onStateChange,
           get state() { return state; },
           get extensionId() { return extensionId; },
           get canUseShortcut() { return canUseShortcut(); } };
})();
"""
