"""Regression: `trinity-local serve` must send Cache-Control: no-store
for .html and .json responses, so the launchpad picks up new code
without the user manually hard-reloading (Cmd+Shift+R).

Symptom this prevents: ship a launchpad fix, user goes back to the
already-open tab, hits ⌘R, Chrome serves the cached HTML, the new
behavior never lands. We chased this for ~5 minutes during the
2026-05-26 stuck-launch e2e — every regen looked like a no-op until
we cache-busted the URL with ?bust=...
"""
from __future__ import annotations

from http.server import HTTPServer
import socket
import threading

import pytest

# Spins up a real HTTPServer + hits it via urllib. The slow marker
# keeps it out of the default `pytest -q` shard so unit tests stay
# under a minute. Run with `pytest -m slow` or `TRINITY_SLOW=1 pytest`.
pytestmark = pytest.mark.slow
import urllib.request


def _get_handler_class():
    from trinity_local.commands.portal import _NoCacheHTMLHandler
    return _NoCacheHTMLHandler


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_html_response_sends_no_store_cache_control(tmp_path):
    handler_cls = _get_handler_class()
    # Drop a tiny HTML file in tmp_path
    (tmp_path / "test.html").write_text("<html></html>")

    handler = lambda *a, **kw: handler_cls(*a, directory=str(tmp_path), **kw)
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/test.html", timeout=2) as resp:
            cache = resp.headers.get("Cache-Control", "")
            pragma = resp.headers.get("Pragma", "")
            expires = resp.headers.get("Expires", "")
        assert "no-store" in cache, f"expected no-store, got: {cache!r}"
        assert "no-cache" in pragma, f"expected no-cache, got: {pragma!r}"
        assert expires == "0", f"expected '0', got: {expires!r}"
    finally:
        server.shutdown()
        server.server_close()


def test_json_response_also_disables_cache(tmp_path):
    """Council status JSON files (~/.trinity/portal_pages/status/*.json)
    are polled while a council runs — they must not be cached either."""
    handler_cls = _get_handler_class()
    (tmp_path / "status.json").write_text('{"state": "running"}')

    handler = lambda *a, **kw: handler_cls(*a, directory=str(tmp_path), **kw)
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status.json", timeout=2) as resp:
            cache = resp.headers.get("Cache-Control", "")
        assert "no-store" in cache, f"expected no-store on JSON, got: {cache!r}"
    finally:
        server.shutdown()
        server.server_close()


def test_static_assets_dont_get_no_store(tmp_path):
    """Vendor JS + PNG share cards keep default caching — they don't
    change between regens and pinning them prevents the user's browser
    from re-pulling the petite-vue bundle on every page reload."""
    handler_cls = _get_handler_class()
    (tmp_path / "asset.js").write_text("// vendor")
    (tmp_path / "card.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    handler = lambda *a, **kw: handler_cls(*a, directory=str(tmp_path), **kw)
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/asset.js", timeout=2) as resp:
            cache = resp.headers.get("Cache-Control", "")
        # SimpleHTTPRequestHandler default does not set Cache-Control at all.
        assert "no-store" not in cache, f"static JS should not have no-store: {cache!r}"
    finally:
        server.shutdown()
        server.server_close()
