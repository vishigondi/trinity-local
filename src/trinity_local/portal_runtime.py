from __future__ import annotations


def portal_runtime_js() -> str:
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

function buildShortcutUrl(payload) {
  const name = encodeURIComponent(
    (typeof pageData !== 'undefined' && pageData.shortcutName) || 'Trinity Dispatch'
  );
  const text = encodeURIComponent(JSON.stringify(payload));
  return `shortcuts://run-shortcut?name=${name}&input=text&text=${text}`;
}

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
  const cacheBuster = base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`;
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
  const cacheBuster = base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`;
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
"""
