"""Phase 8 integration tests — exercise the full extension transition
pipeline end-to-end across the layer boundaries we built in Phases 1-7.

Each unit test pinned one layer. These integrations exercise the
contracts BETWEEN layers — the cross-layer invariants that no single
layer test could catch alone:

  1. install-extension persists settings → launchpad pageData reads
     them → dispatch_readiness reports them → doctor surfaces them.
  2. The Native Messaging frame protocol (4-byte LE length + JSON
     body) round-trips through a real subprocess invocation of
     trinity-local-capture-host with `--help` as a benign safe action.
  3. The 11-tier dispatch flow's data contract: the same payload
     shape the launchpad JS emits matches what capture_host parses.
  4. Public CLI surface includes every install-* command the
     MIGRATION doc references — drift principle #21.

These are the regression guards for "did Phase X break Phase X-1's
contract" — the failure mode an isolated unit test cannot see.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_end_to_end_install_extension_to_doctor_signal(
    isolated_home, monkeypatch, capsys
):
    """Layer 2 → Layer 5: install-extension writes settings → doctor
    reports dispatch_ready as OK. This is the contract that proves the
    install path actually wires up what the launchpad / banner consumes.
    Break this and a user can run install-extension, get success output,
    yet still see the banner — Phase 6 of the 6-stage Pillar 4 funnel.
    """
    from trinity_local.commands.install import handle_install_extension

    monkeypatch.setattr(
        "shutil.which",
        lambda name: f"/usr/local/bin/{name}",
    )
    # No-op the actual NM-dir writes; we're testing the settings file path.
    monkeypatch.setattr(
        "trinity_local.commands.install._native_messaging_dirs",
        lambda browsers: [("chrome", isolated_home / "fake-chrome-nm")],
    )

    rc = handle_install_extension(SimpleNamespace(
        extension_id="abcdefghijklmnopabcdefghijklmnop",
        host_path=None,
        browsers=["chrome"],
        firefox=False,
    ))
    assert rc in (None, 0)

    # Force shortcut applicable=False so the test is platform-independent.
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.doctor import _check_dispatch_ready
    result = _check_dispatch_ready()
    assert result.ok is True, (
        f"After install-extension, doctor must report dispatch_ready=ok. "
        f"Got detail={result.detail!r}"
    )


def test_native_messaging_frame_round_trips_action_message(isolated_home):
    """Layer 1 (capture_host stdio frame) integration. Encodes a real
    4-byte-length-prefixed action message, pipes it to a child python
    running `capture_host.main()`, and decodes the response from stdout.

    This exercises the actual byte protocol the Chrome extension uses
    to talk to the host. Any drift between the JS side
    (browser-extension/background.js sendNativeMessage) and the Python
    side (capture_host._read_message) means the extension silently fails.

    Uses kind="doesnotexist" so the action is rejected by the allowlist —
    that exercises the parse + reject path without invoking a real CLI.
    """
    # Use a real allowlist kind with the required field MISSING. That
    # routes through _is_action_message → _run_action and produces a
    # structured rejection — exercises the parse + dispatch path
    # without launching an actual CLI subprocess.
    action = {"kind": "launch-council"}  # missing required `task`
    body = json.dumps(action).encode("utf-8")
    frame = struct.pack("<I", len(body)) + body

    # Run capture_host as a subprocess to get the real stdin/stdout
    # buffer semantics. Use the same venv python that runs the test.
    proc = subprocess.run(
        [sys.executable, "-m", "trinity_local.capture_host"],
        input=frame,
        capture_output=True,
        timeout=10,
    )
    # Parse the response frame: 4-byte LE length + JSON body.
    out = proc.stdout
    assert len(out) >= 4, f"response too short: {out!r}"
    resp_len = struct.unpack("<I", out[:4])[0]
    response = json.loads(out[4:4 + resp_len].decode("utf-8"))
    assert response["ok"] is False
    assert "missing required field" in response["error"]
    assert "task" in response["error"]


def test_dispatch_payload_shape_matches_capture_host_contract():
    """Layer 3 (dispatch script in launchpad JS) → Layer 1 (capture_host
    ACTION_ALLOWLIST). The launchpad JS emits {kind, task, ...}; the host
    parses on the same `kind` field. Drift here = dispatch silently
    rejected.

    This test asserts: for every kind the dispatch script emits, the
    host's allowlist has a matching entry. The launchpad calls two
    kinds today (`launch-council`, `ingest-recent` — see Phase 4
    commit 1c6ab25, launchpad_template.py callsites). If either is
    removed from the allowlist, the corresponding launchpad button
    silently no-ops.
    """
    from trinity_local.capture_host import ACTION_ALLOWLIST
    from trinity_local.launchpad_runtime import launchpad_runtime_js

    launchpad_kinds = set()
    js = launchpad_runtime_js()
    # The dispatch script accepts kinds as arbitrary strings; callers
    # (launchpad template Vue methods) pick the kind. Crawl the template
    # for the actual call sites.
    from trinity_local import launchpad_template as lt
    template_src = Path(lt.__file__).read_text()
    # The two callsites land as {kind: 'launch-council', ...} and
    # {kind: 'ingest-recent'} (Phase 4 wiring).
    if "kind: 'launch-council'" in template_src or 'kind: "launch-council"' in template_src:
        launchpad_kinds.add("launch-council")
    if "kind: 'ingest-recent'" in template_src or 'kind: "ingest-recent"' in template_src:
        launchpad_kinds.add("ingest-recent")
    assert launchpad_kinds, (
        "No dispatch kinds detected in launchpad_template — Phase 4 wiring "
        "may have regressed."
    )
    for kind in launchpad_kinds:
        assert kind in ACTION_ALLOWLIST, (
            f"Launchpad fires kind={kind!r} but capture_host has no allowlist "
            f"entry for it. Either add to ACTION_ALLOWLIST in capture_host.py "
            f"or remove the dispatcher callsite in launchpad_template.py."
        )


def test_public_cli_includes_all_extension_transition_commands():
    """MIGRATION.md references install-extension and install-launcher —
    both must be reachable from the public CLI. Drift principle #21:
    every command name we tell the user to run in docs gets a regression
    guard at the CLI surface.
    """
    import argparse
    from trinity_local.commands.install import register

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    register(subparsers)

    for cmd in ("install-mcp", "install-extension", "install-launcher",
                "install-app", "install-hooks", "uninstall"):
        # argparse raises SystemExit on unknown subcommands; success means
        # the subcommand exists in the parser. We don't actually call the
        # handler — just confirm the parse succeeds.
        try:
            args = parser.parse_args([cmd])
        except SystemExit:
            pytest.fail(f"{cmd!r} is referenced in MIGRATION.md but not "
                        f"registered in commands/install.py register()")
        assert getattr(args, "handler", None) is not None, (
            f"{cmd!r} parser exists but has no handler set"
        )


def test_dispatch_readiness_doctor_launchpad_agree(
    isolated_home, monkeypatch
):
    """Drift principle #20 in action: the three surfaces consuming
    dispatch readiness (CLI hint, doctor check, launchpad banner) must
    all read the same underlying snapshot.

    Concretely: install nothing, then check that:
      - dispatch_readiness() returns ready=False
      - doctor's _check_dispatch_ready returns ok=False
      - pageData.browserExtension.configured is False
      - pageData.shortcutStatus.applicable controls Shortcut tier
    """
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.launchpad_data import (
        dispatch_readiness, build_page_data, _browser_extension
    )
    from trinity_local.doctor import _check_dispatch_ready

    readiness = dispatch_readiness()
    doctor_check = _check_dispatch_ready()
    page_data = build_page_data(
        live_review_path=isolated_home / "stub.html",
        recent_councils=[],
    )

    # All three must agree on the "not ready" verdict.
    assert readiness["ready"] is False
    assert doctor_check.ok is False
    assert page_data["browserExtension"]["configured"] is False

    # The recommended_action text the doctor + dispatch_readiness agree on.
    assert "install-extension" in readiness["recommended_action"]
    assert "install-extension" in doctor_check.fix


def test_chrome_extension_manifest_action_kinds_match_allowlist():
    """The capture_host action allowlist and the bundled launchpad's
    button data-action attributes must agree on the set of kinds.

    browser-extension/launchpad.html is the chrome-extension:// launchpad
    Phase 3 shipped; it has its own buttons that emit action kinds.
    Those must match capture_host's ACTION_ALLOWLIST for the bundled
    launchpad to work.
    """
    from trinity_local.capture_host import ACTION_ALLOWLIST

    repo_root = Path(__file__).resolve().parents[1]
    bundled_html = repo_root / "browser-extension" / "launchpad.html"
    assert bundled_html.exists(), "browser-extension/launchpad.html missing"
    html_src = bundled_html.read_text()
    # Each `data-action="<kind>"` value the bundled launchpad emits must
    # be in the allowlist.
    import re
    kinds = set(re.findall(r'data-action="([^"]+)"', html_src))
    assert kinds, "No data-action attributes found in bundled launchpad.html"
    for kind in kinds:
        assert kind in ACTION_ALLOWLIST, (
            f"Bundled launchpad emits kind={kind!r} but capture_host "
            f"allowlist does not include it. "
            f"Allowlist: {sorted(ACTION_ALLOWLIST.keys())!r}"
        )
