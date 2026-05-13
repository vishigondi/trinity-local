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
   1b. Autofill content quality: no scaffolding leaks in councilSuggestions
    2. Settings gear: modal opens, sharing + auto-chain toggles present
    3. Personal routing table: >=1 row, columns readable
    4. Lenses Copy-for-sharing: clipboard write fires with non-empty text
    5. Recent council click: live page loads with chairman synthesis
    6. Live council: Back to Launchpad returns home; winner persists on reload
    7. Launch Council button: present + clickable (full e2e gated on macOS Shortcut)
    8. Telemetry guard: no example.invalid console errors
    9. Multi-round thread render: 3 chain segments visible with round numbers
   10. Recent council card content: title + winner + rounds badge per card
   11. Autofill apply: clicking a suggestion fills the textarea
   12. Settings toggle binding: each :checked reflects underlying telemetry state
   13. Lens card render: paired-lenses block populates when tasteLenses exists
   14. Memory viewer + launchpad link: chip links → memory.html loads + renders file

Exit codes:
    0 — all surfaces pass
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

        # ─── Surface 1b: autofill content quality ────────────────────────────
        # Trinity's own extractor / lens-build prompts can leak into the
        # user's CLI transcripts as role=user. We filter them at ingest +
        # search, but a regression in either path silently floods the
        # autofill with "You are extracting durable facts..." clones.
        # See commit 71c3a83 (replay-history fix) and the launchpad fix
        # that followed. Catch any new leak from the rendered DOM.
        # councilSuggestions is loaded into pageData regardless of whether the
        # suggestion panel is currently rendered (panel is v-if="showSuggestions",
        # only shown on textarea focus). Pull it directly from the inline JSON
        # so the check works without simulating user focus.
        autofill = page.evaluate(
            """() => {
              const script = document.getElementById('page-data');
              if (!script) return [];
              try {
                const data = JSON.parse(script.textContent || '{}');
                return (data.councilSuggestions || []).slice(0, 15).map(
                  s => (typeof s === 'string' ? s : (s.text || '')).trim()
                );
              } catch (_) { return []; }
            }"""
        )
        leak_count = sum(
            1 for t in autofill
            if t.lower().startswith(("you are ", "you will "))
        )
        prefixes = [t[:200] for t in autofill if t]
        dup_count = len(prefixes) - len(set(prefixes))
        # Only fail on scaffolding leaks. Prefix duplicates can be legitimate
        # template reuse (e.g. running the same floorplan-analysis template
        # against the same target multiple times) — report for visibility but
        # don't fail.
        if leak_count == 0:
            print(f"[ ✓ ] Surface 1b autofill: {len(autofill)} entries, no scaffolding leaks (dups={dup_count})")
        else:
            reason = f"leak={leak_count} (first: {autofill[0][:80] if autofill else 'empty'!r})"
            print(f"[ ✗ ] Surface 1b autofill: {reason}")
            fails.append((1, "autofill scaffolding leak", reason))

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
              // Exclude .cortex-rules-table — that's the "what Trinity learned"
              // card which shares the .routing-table base class but has its
              // own first-cell shape (plain text, no .benchmark-category div).
              // We want the personal routing table specifically.
              const rows = document.querySelectorAll('table.routing-table:not(.cortex-rules-table) tbody tr');
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
        # Scroll the lens section into view FIRST so the post-click screenshot
        # frames the right surface. Clicking flips the button label to
        # "Copied!" which would break any text-based selector run after.
        page.evaluate(
            """() => {
              const btn = Array.from(document.querySelectorAll('button')).find(b => /(Copy.*shar|Copy as text)/i.test(b.textContent));
              btn?.scrollIntoView({block: 'center'});
            }"""
        )
        page.wait_for_timeout(300)

        copy_state = page.evaluate(
            """() => new Promise(resolve => {
              let copied = null;
              const orig = navigator.clipboard?.writeText;
              if (orig) navigator.clipboard.writeText = async (t) => { copied = t; return Promise.resolve(); };
              const btn = Array.from(document.querySelectorAll('button')).find(b => /(Copy.*shar|Copy as text)/i.test(b.textContent));
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
        # Close the modal cleanly before subsequent surfaces interact with
        # the launchpad — petite-vue mounts it over the whole viewport and
        # eats clicks if left open.
        page.evaluate(
            """() => {
              const buttons = Array.from(document.querySelectorAll('.settings-modal button'));
              const x = buttons.find(b => b.textContent.trim() === '×');
              if (x) x.click();
            }"""
        )
        page.wait_for_function(
            "() => !document.querySelector('.settings-modal')",
            timeout=3000,
        )

        # ─── Surface 9: Multi-round thread render ────────────────────────────
        # The thread-per-page UX (commit 3c44bbd fixed a regression where
        # auto-chain iteration rounds got lost). Pick a known 3-round bundle
        # from disk and assert all three segments render with the expected
        # round numbers in order. Skips if no multi-round bundle is on disk.
        thread_id = _find_multi_round_thread()
        if thread_id is None:
            print(f"[ - ] Surface 9 multi-round thread: SKIPPED (no 3+ round bundle on disk)")
        else:
            page.goto(
                f"{base_url}/review_pages/live_council.html?thread_id={thread_id}",
                wait_until="networkidle",
                timeout=15000,
            )
            page.wait_for_timeout(1500)  # petite-vue hydration
            thread_state = page.evaluate(
                """() => {
                  const segments = Array.from(document.querySelectorAll('.chain-segment'));
                  const roundLabels = segments.map(seg => {
                    const eyebrow = seg.querySelector('.eyebrow');
                    const m = eyebrow?.textContent?.match(/Round\\s+(\\d+)/);
                    return m ? parseInt(m[1], 10) : null;
                  });
                  const hasSynthesis = segments.map(seg =>
                    !!seg.querySelector('.synthesis-section .markdown-body')
                  );
                  return {seg_count: segments.length, roundLabels, hasSynthesis};
                }"""
            )
            page.screenshot(path=str(SHOTS_DIR / "9-multi-round-thread.png"), full_page=True)
            rounds = thread_state.get("roundLabels", [])
            seg_count = thread_state.get("seg_count", 0)
            synth_ok = all(thread_state.get("hasSynthesis", []))
            # Each segment must (a) exist, (b) carry its own round number,
            # (c) render its own chairman synthesis. Round numbers should be
            # monotonic — first is 1, then 2, then 3.
            if seg_count >= 3 and rounds[:3] == [1, 2, 3] and synth_ok:
                print(f"[ ✓ ] Surface 9 multi-round thread: {seg_count} segments, rounds={rounds}, synthesis per round")
            else:
                reason = f"seg_count={seg_count} rounds={rounds} synth_per_round_ok={synth_ok}"
                print(f"[ ✗ ] Surface 9 multi-round thread: {reason}")
                fails.append((9, "multi-round thread render", reason))

            # Bounce back to the launchpad for the next surfaces.
            page.goto(f"{base_url}/portal_pages/launchpad.html", wait_until="networkidle", timeout=10000)
            page.wait_for_timeout(800)

        # ─── Surface 10: Recent council card content ─────────────────────────
        # Surface 5 confirms cards click through; this confirms each card
        # actually carries the title + meta block ("winner · date · N rounds")
        # — a missing winner/date is a recent regression signal (e.g. the
        # personal_routing_table rewire shipped a card with empty meta).
        cards_state = page.evaluate(
            """() => {
              const cards = Array.from(document.querySelectorAll('a.council-card-link'));
              const sample = cards.slice(0, 3).map(a => {
                const title = a.querySelector('.council-title')?.textContent?.trim();
                const meta = a.querySelector('.meta')?.textContent?.trim();
                const hrefHasThread = (a.getAttribute('href') || '').includes('thread_id=');
                return {title_ok: !!title && title.length > 0, meta_ok: !!meta && meta.length > 0, hrefHasThread};
              });
              return {count: cards.length, sample};
            }"""
        )
        sample = cards_state.get("sample", [])
        cards_ok = (
            cards_state.get("count", 0) >= 1
            and all(s.get("title_ok") and s.get("meta_ok") and s.get("hrefHasThread") for s in sample)
        )
        if cards_ok:
            print(f"[ ✓ ] Surface 10 recent cards: {cards_state['count']} cards, first 3 have title + meta + thread_id href")
        else:
            reason = f"count={cards_state.get('count')} sample={sample}"
            print(f"[ ✗ ] Surface 10 recent cards: {reason}")
            fails.append((10, "recent card content", reason))

        # ─── Surface 11: Autofill suggestion click → textarea fills ──────────
        # Surface 1b validates the suggestion DATA. This validates the
        # APPLY path: focus the textarea, pick the first non-empty
        # suggestion, click it, verify the textarea now contains that text.
        # Catches regressions in @mousedown handling / applySuggestion().
        apply_state = page.evaluate(
            """() => new Promise(resolve => {
              const textarea = document.querySelector('textarea');
              if (!textarea) { resolve({ok: false, reason: 'no textarea'}); return; }
              // Focus opens the panel (v-if="showSuggestions")
              textarea.focus();
              setTimeout(() => {
                const items = Array.from(document.querySelectorAll('.suggestion-item'));
                if (items.length === 0) { resolve({ok: false, reason: 'no suggestion items rendered after focus'}); return; }
                const target = items[0];
                const targetText = target.querySelector('.suggestion-text')?.textContent?.trim() || '';
                // Suggestion buttons use @mousedown.prevent — dispatch that.
                target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                setTimeout(() => {
                  resolve({
                    ok: true,
                    targetHead: targetText.slice(0, 80),
                    valueHead: (textarea.value || '').slice(0, 80),
                    matches: targetText.length > 0 && (textarea.value || '').startsWith(targetText.slice(0, 40)),
                  });
                }, 400);
              }, 400);
            })"""
        )
        if apply_state.get("ok") and apply_state.get("matches"):
            print(f"[ ✓ ] Surface 11 autofill apply: textarea filled from suggestion ('{apply_state['valueHead']}...')")
        else:
            reason = apply_state.get("reason") or f"target={apply_state.get('targetHead')!r} value={apply_state.get('valueHead')!r}"
            print(f"[ ✗ ] Surface 11 autofill apply: {reason}")
            fails.append((11, "autofill apply", reason))

        # Clear textarea + blur so it doesn't intercept later surfaces.
        page.evaluate(
            """() => {
              const t = document.querySelector('textarea');
              if (t) { t.value = ''; t.dispatchEvent(new Event('input', {bubbles: true})); t.blur(); }
            }"""
        )
        page.wait_for_timeout(300)

        # ─── Surface 12: Settings toggle binding ─────────────────────────────
        # Surface 2 confirms toggles are present. This confirms each toggle's
        # `:checked` binding actually reflects the underlying telemetry state
        # in page-data — catches a regression where the binding is wired to
        # the wrong reactive key or a stale closure.
        #
        # NOTE: we don't simulate a click. Real toggles call
        # `triggerSettingsAction` which fires `scheduleLaunchpadReload(1400)`
        # — the page navigates mid-test, destroying any pending evaluate.
        # The full mutation path is covered by unit tests + end-to-end
        # `trinity-local telemetry-{enable,disable}` calls; here we just
        # verify the rendered DOM matches the bound state.
        page.evaluate(
            """() => {
              const gear = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '⚙');
              gear?.click();
            }"""
        )
        page.wait_for_selector(".settings-modal input[type='checkbox']", state="attached", timeout=2000)
        toggle_state = page.evaluate(
            """() => {
              const script = document.getElementById('page-data');
              const data = script ? JSON.parse(script.textContent || '{}') : {};
              const tel = data.telemetry || {};
              const toggles = Array.from(document.querySelectorAll('.settings-modal input[type="checkbox"]'));
              // Expected order matches the template: Sharing, Auto-chain, Polish-auto.
              const expected = [
                ['enabled', tel.enabled],
                ['autoChainEnabled', tel.autoChainEnabled],
                ['polishAutoIterate', tel.polishAutoIterate],
              ];
              const rows = toggles.slice(0, 3).map((t, i) => ({
                key: expected[i][0],
                expected: !!expected[i][1],
                actual: t.checked,
                matches: t.checked === !!expected[i][1],
              }));
              return {toggle_count: toggles.length, rows};
            }"""
        )
        rows = toggle_state.get("rows", [])
        bindings_ok = (
            toggle_state.get("toggle_count", 0) >= 3
            and len(rows) == 3
            and all(r.get("matches") for r in rows)
        )
        if bindings_ok:
            summary = ", ".join(f"{r['key']}={r['actual']}" for r in rows)
            print(f"[ ✓ ] Surface 12 toggle bindings: all 3 match page-data ({summary})")
        else:
            reason = f"count={toggle_state.get('toggle_count')} rows={rows}"
            print(f"[ ✗ ] Surface 12 toggle bindings: {reason}")
            fails.append((12, "settings toggle binding", reason))

        # Close modal cleanly before next surface.
        page.evaluate(
            """() => {
              const buttons = Array.from(document.querySelectorAll('.settings-modal button'));
              const x = buttons.find(b => b.textContent.trim() === '×');
              if (x) x.click();
            }"""
        )
        page.wait_for_function(
            "() => !document.querySelector('.settings-modal')",
            timeout=3000,
        )

        # ─── Surface 13: Lens card render ────────────────────────────────────
        # The taste-card is v-if="tasteLenses" — if lens-build hasn't run
        # we get an empty-state card instead. Either is valid; assert
        # whichever path the data takes is structurally complete.
        lens_state = page.evaluate(
            """() => {
              const tasteCard = document.querySelector('section.taste-card');
              if (tasteCard) {
                const paired = tasteCard.querySelectorAll('.taste-block .taste-list li').length;
                const vocab = tasteCard.querySelectorAll('.taste-vocab-chip').length;
                const shareBtn = !!Array.from(tasteCard.querySelectorAll('button')).find(b => /copy/i.test(b.textContent));
                return {variant: 'lenses', paired_count: paired, vocab_count: vocab, has_share_btn: shareBtn};
              }
              // Empty-state — the section right below the routing card carrying the lens-build CTA.
              const emptyHeading = Array.from(document.querySelectorAll('h2'))
                .find(h => /lens|taste|me-build|lens-build/i.test(h.textContent));
              return {variant: 'empty-state', has_cta: !!emptyHeading};
            }"""
        )
        if lens_state.get("variant") == "lenses":
            ok = lens_state.get("paired_count", 0) >= 1 and lens_state.get("has_share_btn")
            if ok:
                print(f"[ ✓ ] Surface 13 lens card: {lens_state['paired_count']} lens items + share button rendered")
            else:
                reason = f"lens card present but incomplete: {lens_state}"
                print(f"[ ✗ ] Surface 13 lens card: {reason}")
                fails.append((13, "lens card render", reason))
        elif lens_state.get("variant") == "empty-state" and lens_state.get("has_cta"):
            print(f"[ ✓ ] Surface 13 lens card: empty-state CTA shown (lens-build not run on this install)")
        else:
            reason = f"neither lens card nor empty-state CTA: {lens_state}"
            print(f"[ ✗ ] Surface 13 lens card: {reason}")
            fails.append((13, "lens card render", reason))

        # ─── Surface 14: Memory viewer + launchpad chip link ─────────────────
        # The launchpad's "Your memories, raw" card should expose chip links
        # to the generic memory viewer (memory.html?file=<name>). This
        # asserts (a) chips exist for each of the six memories, (b) clicking
        # one navigates to memory.html and the viewer renders the file body.
        chips_state = page.evaluate(
            """() => {
              const chips = Array.from(document.querySelectorAll('a.memory-chip'));
              return {
                count: chips.length,
                names: chips.map(a => a.querySelector('code')?.textContent?.trim()).filter(Boolean),
                first_href: chips[0]?.getAttribute('href'),
              };
            }"""
        )
        expected_names = {"lens.md", "picks.json", "routing.json", "topics.json", "vocabulary.md", "core.md"}
        actual_names = set(chips_state.get("names") or [])
        if chips_state.get("count", 0) >= 6 and expected_names.issubset(actual_names):
            print(f"[ ✓ ] Surface 14a memory chips: {chips_state['count']} links present (all 6 memories)")
        else:
            reason = f"count={chips_state.get('count')} names={sorted(actual_names)}"
            print(f"[ ✗ ] Surface 14a memory chips: {reason}")
            fails.append((14, "memory viewer chips", reason))

        # Click the first chip (lens.md) and verify the viewer renders body.
        try:
            with page.expect_navigation(timeout=8000):
                page.evaluate("""() => document.querySelector('a.memory-chip')?.click()""")
            page.wait_for_timeout(800)  # let fetch + DOM render settle
            viewer_state = page.evaluate(
                """() => ({
                  url: window.location.href,
                  title: document.querySelector('.content-header h2')?.textContent,
                  bodyLen: (document.querySelector('pre.body')?.textContent || '').length,
                  activeNav: document.querySelector('.memory-nav-link.active')?.dataset.file,
                  navCount: document.querySelectorAll('.memory-nav-link').length,
                })"""
            )
            page.screenshot(path=str(SHOTS_DIR / "14-memory-viewer.png"), full_page=True)
            on_viewer = "memory.html" in viewer_state.get("url", "")
            has_body = (viewer_state.get("bodyLen") or 0) > 50  # any real memory has more than 50 chars
            empty_ok = viewer_state.get("bodyLen") == 0 and viewer_state.get("title")  # empty-state is also OK
            if on_viewer and viewer_state.get("navCount") == 6 and (has_body or empty_ok):
                print(f"[ ✓ ] Surface 14b memory viewer: '{viewer_state['title']}' rendered ({viewer_state['bodyLen']} chars, active={viewer_state['activeNav']})")
            else:
                reason = f"viewer_state={viewer_state}"
                print(f"[ ✗ ] Surface 14b memory viewer: {reason}")
                fails.append((14, "memory viewer load", reason))
        except Exception as exc:
            print(f"[ ✗ ] Surface 14b memory viewer: navigation failed ({exc})")
            fails.append((14, "memory viewer load", str(exc)[:120]))

        browser.close()

    print()
    print("─" * 60)
    if not fails:
        print(f"✓ All surfaces pass. Screenshots in {SHOTS_DIR.relative_to(REPO_ROOT)}/")
        return 0
    else:
        print(f"✗ {len(fails)} surface(s) failed:")
        for n, name, reason in fails:
            print(f"    Surface {n} ({name}): {reason[:120]}")
        return 1


def _find_multi_round_thread() -> str | None:
    """Pick a thread bundle on disk with 3+ segments, for Surface 9.

    Walks `~/.trinity/council_outcomes/_thread_*.js`, parses the embedded
    JSON, returns the first chain_root_id whose segments[] has length >= 3.
    Returns None if no such bundle exists — Surface 9 then skips.
    """
    threads_dir = TRINITY_HOME / "council_outcomes"
    if not threads_dir.is_dir():
        return None
    import re as _re
    # File shape (one line):
    #   window.__TRINITY_COUNCIL_THREAD__ = window.__TRINITY_COUNCIL_THREAD__ || {};
    #   window.__TRINITY_COUNCIL_THREAD__["bundle_X"] = {<payload>};
    # The first `{}` is the empty-object initializer; we need the assignment
    # payload, which is the `{...}` after the indexed assignment.
    pattern = _re.compile(r'__TRINITY_COUNCIL_THREAD__\[[^\]]+\]\s*=\s*({.*})\s*;', _re.DOTALL)
    for path in sorted(threads_dir.glob("_thread_*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = pattern.search(text)
        if not m:
            continue
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        segments = payload.get("segments") or []
        if len(segments) >= 3:
            return payload.get("chain_root_id") or None
    return None


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
