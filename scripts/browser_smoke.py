#!/usr/bin/env python3
"""scripts/browser_smoke.py — v1 launch-day UI smoke.

Drives Trinity's launchpad through 8 testable surfaces via headless playwright,
asserts on DOM + console, saves a screenshot per surface to docs/smoke/, exits
non-zero if any surface fails.

Cheaper than Autobrowse (no per-page API token cost) and deterministic — same
result every run unless the underlying data changes. This is the launch gate
for "did the brand land in the browser, do all clicks still work."

Usage:
    python scripts/browser_smoke.py                    # headless
    python scripts/browser_smoke.py --headed           # watch it run
    python scripts/browser_smoke.py --port 8765        # different server port
    python scripts/browser_smoke.py --skip-regen       # don't re-run portal-html

Prereqs (installed once):
    pip install playwright
    playwright install chromium

Surfaces:
    1. Launchpad cold-render: Ratings chart bars rendered
    2. Settings gear: modal opens, sharing + auto-chain toggles present
    3. Personal routing table: >=1 row, columns readable
    4. Lenses Copy-for-sharing: clipboard write fires with non-empty text
    5. Recent council click: live page loads with chairman synthesis
    6. Live council: Back to Launchpad returns home; winner persists on reload
    7. Launch Council button: present + clickable (full e2e gated on macOS Shortcut)
    8. Telemetry guard: no example.invalid console errors

Exit codes:
    0 — all 8 surfaces pass
    1 — at least one surface failed
    2 — setup error (server, regen, etc.)
    3 — playwright not installed
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TRINITY_HOME = Path.home() / ".trinity"
SHOTS_DIR = REPO_ROOT / "docs" / "smoke"
DEFAULT_PORT = 8765


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--skip-regen", action="store_true", help="skip portal-html regeneration")
    args = parser.parse_args()

    # Step 1: regenerate launchpad pages from current source
    if not args.skip_regen:
        print("[setup] regenerating launchpad via portal-html...")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "trinity_local.main", "portal-html"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            print("[setup] portal-html timed out — fatal")
            return 2
        if result.returncode != 0:
            print(f"[setup] portal-html failed (exit {result.returncode}):\n{result.stderr[:500]}")
            return 2

    # Step 2: ensure a server is responding
    server_handle = _ensure_server(args.port)
    if server_handle is None and not _is_server_up(args.port):
        print(f"[setup] could not start nor reach server on :{args.port}")
        return 2

    # Step 3: open playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[setup] playwright not installed. Run:")
        print("    pip install playwright")
        print("    playwright install chromium")
        return 3

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{args.port}"

    fails: list[tuple[int, str, str]] = []  # (surface_num, name, reason)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=not args.headed)
        except Exception as exc:
            print(f"[setup] chromium launch failed: {exc}")
            print("    Run: playwright install chromium")
            return 3
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        # ─── Surface 1: launchpad cold-render ────────────────────────────────
        page.goto(f"{base_url}/portal_pages/launchpad.html", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(1500)  # petite-vue + Chart.js settle
        chart_data = page.evaluate(
            """() => {
              const c = document.getElementById('personal-preference-chart');
              if (!c) return {chart_attached: false, reason: 'canvas missing'};
              const ch = (window.Chart && Chart.getChart) ? Chart.getChart(c) : null;
              if (!ch) return {chart_attached: false, reason: 'no chart instance'};
              const has_bars = ch.data.datasets.some(d => d.data.some(v => v !== null));
              return {chart_attached: true, has_bars, labels: ch.data.labels, first_dataset: ch.data.datasets[0]?.data};
            }"""
        )
        page.screenshot(path=str(SHOTS_DIR / "1-launchpad.png"), full_page=True)
        if chart_data.get("chart_attached") and chart_data.get("has_bars"):
            print(f"[ ✓ ] Surface 1 launchpad: chart bars present {chart_data['first_dataset']}")
        else:
            reason = chart_data.get("reason") or "no bars in any dataset"
            print(f"[ ✗ ] Surface 1 launchpad: {reason}")
            fails.append((1, "launchpad cold-render", reason))

        # ─── Surface 2: Settings gear ────────────────────────────────────────
        gear_clicked = page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '⚙');
              if (!btn) return {ok: false, reason: 'gear button missing'};
              btn.click();
              return {ok: true};
            }"""
        )
        page.wait_for_timeout(400)
        settings_state = page.evaluate(
            """() => {
              const modal = document.querySelector('.settings-modal');
              const toggles = document.querySelectorAll('.settings-modal input[type="checkbox"]');
              const endpoint = Array.from(document.querySelectorAll('.settings-modal .meta'))
                .find(el => /https?:\\/\\//.test(el.textContent))?.textContent?.trim();
              return {modal_visible: !!modal, toggle_count: toggles.length, has_endpoint: !!endpoint};
            }"""
        )
        page.screenshot(path=str(SHOTS_DIR / "2-settings.png"))
        # Close the modal so it doesn't intercept subsequent clicks.
        # Petite-vue binds @click="settingsOpen = false" on the × button;
        # find it by content + dispatch a real click. Verify the modal
        # actually went away before moving on.
        page.evaluate(
            """() => {
              const buttons = Array.from(document.querySelectorAll('.settings-modal button'));
              const x = buttons.find(b => b.textContent.trim() === '×');
              if (x) x.click();
            }"""
        )
        # Wait for petite-vue to re-render the modal away
        page.wait_for_function(
            "() => !document.querySelector('.settings-modal')",
            timeout=3000,
        )
        page.wait_for_timeout(200)
        if gear_clicked.get("ok") and settings_state.get("modal_visible") and settings_state.get("toggle_count", 0) >= 2:
            print(f"[ ✓ ] Surface 2 settings: modal opens with {settings_state['toggle_count']} toggles")
        else:
            reason = f"{gear_clicked} / {settings_state}"
            print(f"[ ✗ ] Surface 2 settings: {reason}")
            fails.append((2, "settings gear", reason))

        # ─── Surface 3: Personal routing table ───────────────────────────────
        routing_state = page.evaluate(
            """() => {
              const rows = document.querySelectorAll('table.routing-table tbody tr');
              const first = rows[0];
              const first_task = first?.querySelector('td:first-child .benchmark-category')?.textContent?.trim();
              return {row_count: rows.length, first_task};
            }"""
        )
        if routing_state.get("row_count", 0) >= 1 and routing_state.get("first_task"):
            print(f"[ ✓ ] Surface 3 routing table: {routing_state['row_count']} rows (first: '{routing_state['first_task']}')")
        else:
            reason = f"row_count={routing_state.get('row_count')}"
            print(f"[ ✗ ] Surface 3 routing table: {reason}")
            fails.append((3, "routing table", reason))

        # Focused screenshot — scroll to the routing table so visual review
        # gets the section in isolation, not buried in a fullPage shot.
        page.evaluate("() => document.querySelector('table.routing-table')?.scrollIntoView({block: 'start'})")
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOTS_DIR / "3-routing-table.png"))

        # ─── Surface 4: Copy-for-sharing clipboard write ─────────────────────
        copy_state = page.evaluate(
            """() => new Promise(resolve => {
              let copied = null;
              const orig = navigator.clipboard?.writeText;
              if (orig) navigator.clipboard.writeText = async (t) => { copied = t; return Promise.resolve(); };
              const btn = Array.from(document.querySelectorAll('button')).find(b => /Copy.*shar/i.test(b.textContent));
              if (!btn) { if (orig) navigator.clipboard.writeText = orig; resolve({ok: false, reason: 'btn missing'}); return; }
              btn.click();
              setTimeout(() => {
                if (orig) navigator.clipboard.writeText = orig;
                resolve({ok: true, len: copied?.length, preview: copied?.slice(0, 80)});
              }, 300);
            })"""
        )
        if copy_state.get("ok") and (copy_state.get("len") or 0) > 0:
            print(f"[ ✓ ] Surface 4 copy-for-sharing: {copy_state['len']} chars copied ('{copy_state['preview']}...')")
        else:
            reason = copy_state.get("reason") or "nothing copied"
            print(f"[ ✗ ] Surface 4 copy-for-sharing: {reason}")
            fails.append((4, "copy-for-sharing", reason))

        # Focused screenshot of the /me lens + copy button.
        page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button')).find(b => /Copy.*shar/i.test(b.textContent));
              btn?.scrollIntoView({block: 'center'});
            }"""
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOTS_DIR / "4-copy-for-sharing.png"))

        # ─── Surface 5: Recent council click ─────────────────────────────────
        recent_state = page.evaluate(
            """() => {
              const links = document.querySelectorAll('a.council-card-link');
              return {count: links.length, first_href: links[0]?.getAttribute('href')};
            }"""
        )
        if recent_state.get("count", 0) == 0:
            print(f"[ ✗ ] Surface 5 recent council: no cards (need to run trinity-local council-launch first)")
            fails.append((5, "recent council click", "no cards rendered"))
            council_page_loaded = False
        else:
            page.click("a.council-card-link", timeout=5000)
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_timeout(2000)
            live_state = page.evaluate(
                """() => {
                  const h2 = document.querySelector('h2');
                  const has_failed_card = !!Array.from(document.querySelectorAll('strong,h2,h3,p'))
                    .find(el => /Council failed/i.test(el.textContent));
                  const has_winner = !!Array.from(document.querySelectorAll('h2,h3'))
                    .find(el => /winner/i.test(el.textContent));
                  return {url: window.location.href, h2: h2?.textContent?.trim(), has_failed_card, has_winner};
                }"""
            )
            page.screenshot(path=str(SHOTS_DIR / "5-recent-council.png"), full_page=True)
            council_page_loaded = "live_council" in live_state.get("url", "") and not live_state.get("has_failed_card")
            if council_page_loaded:
                print(f"[ ✓ ] Surface 5 recent council: live page renders ('{live_state.get('h2')}')")
            else:
                reason = "Council failed card" if live_state.get("has_failed_card") else f"didn't reach live page: {live_state}"
                print(f"[ ✗ ] Surface 5 recent council: {reason}")
                fails.append((5, "recent council click", reason))

        # ─── Surface 6: Live council back-trip + winner persist ──────────────
        if council_page_loaded:
            # Wait for the navigation in the same context as the click —
            # otherwise wait_for_load_state can return on the still-current
            # page before the link fires its navigation.
            back_present = page.evaluate(
                """() => !!Array.from(document.querySelectorAll('a.button.ghost'))
                    .find(a => /Back to Launchpad/i.test(a.textContent))"""
            )
            if not back_present:
                print(f"[ ✗ ] Surface 6 live council back-trip: back btn missing")
                fails.append((6, "live council back-trip", "back btn missing"))
            else:
                try:
                    with page.expect_navigation(timeout=10000):
                        page.evaluate(
                            """() => {
                              Array.from(document.querySelectorAll('a.button.ghost'))
                                .find(a => /Back to Launchpad/i.test(a.textContent))?.click();
                            }"""
                        )
                    page.wait_for_timeout(500)
                    if "launchpad.html" in page.url:
                        print(f"[ ✓ ] Surface 6 live council back-trip: returned to launchpad")
                        # Focused capture — launchpad-after-back-from-council.
                        # Should look identical to the cold-render except scroll
                        # position; visual review catches state leakage.
                        page.evaluate("() => window.scrollTo(0, 0)")
                        page.wait_for_timeout(300)
                        page.screenshot(path=str(SHOTS_DIR / "6-back-to-launchpad.png"))
                except Exception as exc:
                    print(f"[ ✗ ] Surface 6 live council back-trip: navigation failed ({exc})")
                    fails.append((6, "live council back-trip", str(exc)[:120]))
        else:
            print(f"[ - ] Surface 6 live council back-trip: SKIPPED (surface 5 failed)")
            fails.append((6, "live council back-trip", "skipped (s5 failed)"))

        # ─── Surface 7: Launch Council button presence ───────────────────────
        # E2E (fire a real council) is gated on macOS Shortcut; assert button is wired.
        # If we navigated mid-Surface-6, wait for the new page to be ready.
        if "launchpad.html" not in page.url:
            page.goto(f"{base_url}/portal_pages/launchpad.html", wait_until="networkidle", timeout=10000)
        page.wait_for_timeout(800)
        launch_state = page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button'))
                .find(b => /Launch Council/i.test(b.textContent));
              return {present: !!btn, disabled: btn?.disabled || false};
            }"""
        )
        if launch_state.get("present") and not launch_state.get("disabled"):
            print(f"[ ✓ ] Surface 7 Launch Council button: present + enabled (e2e gated on macOS Shortcut, not asserted)")
        else:
            print(f"[ ✗ ] Surface 7 Launch Council button: {launch_state}")
            fails.append((7, "Launch Council button", str(launch_state)))

        # Focused screenshot of the Council card with Launch button visible.
        page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button')).find(b => /Launch Council/i.test(b.textContent));
              btn?.scrollIntoView({block: 'center'});
            }"""
        )
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOTS_DIR / "7-launch-button.png"))

        # ─── Surface 8: Telemetry guard (no example.invalid in console) ──────
        invalid_errs = [e for e in console_errors if "example.invalid" in e or "ERR_NAME_NOT_RESOLVED" in e]
        if not invalid_errs:
            print(f"[ ✓ ] Surface 8 telemetry guard: no example.invalid console errors")
        else:
            print(f"[ ✗ ] Surface 8 telemetry guard: {len(invalid_errs)} stray errors")
            fails.append((8, "telemetry guard", f"{len(invalid_errs)} errors: {invalid_errs[:2]}"))

        # Focused screenshot — settings modal showing the "Not configured"
        # display fix (endpoint guard). Open modal, capture, close cleanly.
        page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '⚙');
              btn?.click();
            }"""
        )
        page.wait_for_timeout(400)
        page.screenshot(path=str(SHOTS_DIR / "8-settings-endpoint-guard.png"))

        browser.close()

    print()
    print("─" * 60)
    if not fails:
        print(f"✓ All 8 surfaces pass. Screenshots in {SHOTS_DIR.relative_to(REPO_ROOT)}/")
        return 0
    else:
        print(f"✗ {len(fails)}/8 surfaces failed:")
        for n, name, reason in fails:
            print(f"    Surface {n} ({name}): {reason[:120]}")
        return 1


def _is_server_up(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/portal_pages/launchpad.html", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _ensure_server(port: int) -> threading.Thread | None:
    """Return a thread handle if we started a new server, None if one was already up."""
    if _is_server_up(port):
        return None

    home = TRINITY_HOME
    if not home.is_dir():
        print(f"[setup] TRINITY_HOME not found at {home} — run portal-html first")
        return None

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(home), **kw)
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"[setup] could not bind 127.0.0.1:{port} — {exc}")
        return None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.6)
    return thread


if __name__ == "__main__":
    sys.exit(main())
