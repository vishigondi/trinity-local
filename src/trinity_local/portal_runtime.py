from __future__ import annotations


def portal_runtime_js() -> str:
    """Shared JS runtime block injected into Launchpad and live council pages."""
    return """
window.__TRINITY_COUNCIL_STATUS__ = window.__TRINITY_COUNCIL_STATUS__ || {};

function buildShortcutUrl(payload) {
  const name = encodeURIComponent(
    (typeof pageData !== 'undefined' && pageData.shortcutName) || 'Trinity Dispatch'
  );
  const text = encodeURIComponent(JSON.stringify(payload));
  return `shortcuts://run-shortcut?name=${name}&input=text&text=${text}`;
}

function loadStatusScript(token, onComplete) {
  const base = (typeof pageData !== 'undefined' && pageData.statusScriptBaseUrl) || '';
  if (!base || !token) {
    onComplete(null);
    return;
  }
  const script = document.createElement('script');
  script.src = `${base}/council_status_${encodeURIComponent(token)}.js?t=${Date.now()}`;
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
"""
