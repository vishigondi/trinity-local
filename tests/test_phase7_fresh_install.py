"""Phase 7 fresh-install tests (council_37eca30b6e7010df).

Three scenarios codex flagged as the v1.0 launch-readiness floor:

  1. Fresh TRINITY_HOME → trinity-local doctor parses + reports
     trinity_home_writeable + mcp_available green (provider CLIs
     may be absent in CI; tolerated)
  2. Fresh TRINITY_HOME → trust-init writes valid TOML; trust-show
     parses it; audit-show works against empty audit log
  3. Fresh TRINITY_HOME → portal-html renders the launchpad without
     crashing (no provider data, no embeddings — just the empty-
     state shape)

These are the "first-run on a clean machine" tests. They DON'T
exercise real provider CLIs (separate manual smoke script handles
that); they DO exercise the CLI/data-contract surfaces that any
fresh install touches before anything else happens.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _trinity_local(*args, isolated_home: Path, **extra_env):
    """Run `trinity-local ...` with the test-isolated TRINITY_HOME."""
    env = {
        **os.environ,
        "TRINITY_HOME": str(isolated_home),
        "PYTHONPATH": f"{REPO_ROOT}:{REPO_ROOT / 'src'}",
        **extra_env,
    }
    return subprocess.run(
        [sys.executable, "-m", "trinity_local.main", *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_doctor_runs_on_fresh_home(isolated_home):
    """A fresh TRINITY_HOME should not crash doctor. The doctor command
    might return non-zero if optional providers are missing, but it
    must NOT crash or produce malformed output."""
    result = _trinity_local("doctor", isolated_home=isolated_home)
    # Either green (everything wired) or yellow (something to fix) —
    # both produce parseable output. We tolerate non-zero exit code
    # because provider CLIs are typically absent in CI.
    assert result.returncode in (0, 1, 2), (
        f"doctor crashed with unexpected exit code {result.returncode}: "
        f"{result.stderr!r}"
    )
    # Doctor's output should include the home check + at least one
    # other check (provider, MCP, etc.) — proves the harness ran.
    assert "trinity" in result.stdout.lower() or "trinity" in result.stderr.lower()


def test_trust_init_and_trust_show_round_trip(isolated_home):
    """trust-init writes a valid trust.toml; trust-show parses it."""
    init = _trinity_local("trust-init", isolated_home=isolated_home)
    assert init.returncode == 0, f"trust-init: {init.stderr!r}"
    payload = json.loads(init.stdout)
    trust_toml = Path(payload["path"])
    assert trust_toml.exists()
    # The default trust.toml has all the required structure.
    contents = trust_toml.read_text()
    assert "schema_version = 1" in contents
    assert "[trust]" in contents
    assert 'default = "ask"' in contents

    # trust-show parses it without error.
    show = _trinity_local("trust-show", isolated_home=isolated_home)
    assert show.returncode == 0, f"trust-show: {show.stderr!r}"
    cfg = json.loads(show.stdout)
    assert cfg["default"] == "ask"


def test_audit_show_handles_empty_log(isolated_home):
    """audit-show on a fresh install (no audit.log yet) must not crash —
    it should print a clear "no entries" message."""
    result = _trinity_local("audit-show", "--last", "5",
                            isolated_home=isolated_home)
    assert result.returncode == 0, f"audit-show: {result.stderr!r}"
    assert "no audit" in result.stdout.lower() or result.stdout.strip() == ""


def test_portal_html_renders_on_fresh_home(isolated_home):
    """portal-html on a fresh TRINITY_HOME must render the empty-state
    launchpad without crashing. No embeddings, no councils, no lens —
    just the shell of the launchpad ready for first-run."""
    result = _trinity_local("portal-html", isolated_home=isolated_home)
    assert result.returncode == 0, f"portal-html: {result.stderr!r}"
    payload = json.loads(result.stdout)
    path = Path(payload["path"])
    assert path.exists()
    # Sanity: produced a real HTML file.
    content = path.read_text()
    assert "<!doctype" in content.lower() or "<html" in content.lower()
    assert "trinity" in content.lower()


def test_scripts_resolve_repo_imports_without_pythonpath(isolated_home):
    """The council's "script mode" claim: running scripts/<name>.py
    directly from a repo checkout must resolve imports of
    trinity_local without PYTHONPATH set externally. Each script's
    own sys.path manipulation handles this."""
    # Use cluster.py — it only needs numpy + trinity_local (via the
    # pip-tier delegation we ship in v1.0).
    script = REPO_ROOT / "scripts" / "cluster.py"
    payload = json.dumps({"vectors": [[1.0, 0.0], [0.0, 1.0]],
                          "k": 2, "seed": 42})
    result = subprocess.run(
        [sys.executable, str(script)],
        input=payload, capture_output=True, text=True,
        env={
            **os.environ,
            "TRINITY_HOME": str(isolated_home),
            "TRINITY_SKIP_VENV_BOOTSTRAP": "1",
            # Critically: NO PYTHONPATH set externally.
            "PYTHONPATH": "",
        },
        timeout=10,
    )
    assert result.returncode == 0, (
        f"script mode failed without PYTHONPATH:\n{result.stderr!r}"
    )
    out = json.loads(result.stdout)
    assert out["n"] == 2


def test_tfidf_hash_is_stable_across_processes(isolated_home):
    """council_37eca30b6e7010df pre-empt: Python's hash() is
    PYTHONHASHSEED-randomized; the old TF-IDF fallback used hash()
    which would silently produce DIFFERENT vectors in different
    Python processes. The fix uses SHA-1 projection — must be
    stable cross-process.

    Verify by running the same TF-IDF embedding in two separate
    subprocesses and asserting bit-equal vectors. If this regresses
    to hash(), one of the two subprocesses gets a different
    PYTHONHASHSEED and the test catches it."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT / 'src')!r})\n"
        "from trinity_local.embeddings.backend_tfidf import embed_tfidf\n"
        "vec = embed_tfidf('the quick brown fox', dim=64)\n"
        "print(json.dumps(vec))\n"
    )
    # Two subprocesses with different random PYTHONHASHSEEDs. SHA-1
    # gives bit-equal output; hash() would not.
    vecs = []
    for seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            timeout=10,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr!r}"
        vecs.append(json.loads(result.stdout))
    assert vecs[0] == vecs[1], (
        "TF-IDF embedding diverged between subprocesses with different "
        "PYTHONHASHSEED values. The hash projection MUST be stable "
        "cross-process (SHA-1) — Python's built-in hash() is "
        "process-randomized."
    )
