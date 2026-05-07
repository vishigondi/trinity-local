"""Web-task verifier — Browserbase Autobrowse subprocess wrapper.

Council `council_5fbf909119830643` ratified Autobrowse (`--env local`,
no API key, headed Chrome) as the verification adapter for web-task
skills. Inner loop's verify stage calls this when frame.verifier ==
"autobrowse"; non-web skills route to chairman_rubric instead.

Output contract is uniform across both verifiers so run.py doesn't
branch on type past the dispatch:

    {"passed": bool, "reasons": [str, ...], "skill_md_path": str | None,
     "iterations_used": int, "summary": str}

Graceful degradation: if Autobrowse isn't installed, return a structured
"not_available" result instead of crashing. Inner loop downgrades to
chairman_rubric in that case.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerifyResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    skill_md_path: str | None = None
    iterations_used: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons": self.reasons,
            "skill_md_path": self.skill_md_path,
            "iterations_used": self.iterations_used,
            "summary": self.summary,
        }


def autobrowse_available() -> bool:
    """Detect Autobrowse without invoking it.

    `npx autobrowse --version` is the cheap probe. If `npx` itself isn't on
    PATH (or the package isn't cached), we degrade rather than crash.
    """
    if shutil.which("npx") is None:
        return False
    try:
        result = subprocess.run(
            ["npx", "--no-install", "autobrowse", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _slug_from_skill_id(skill_id: str) -> str:
    """Autobrowse takes a task slug. Use the skill_id; strip the prefix."""
    return skill_id.replace("skill_", "", 1) if skill_id.startswith("skill_") else skill_id


def parse_autobrowse_output(stdout: str) -> tuple[bool, list[str], str | None, int, str]:
    """Best-effort extraction from Autobrowse's emit format.

    Autobrowse prints a per-iteration summary plus a final graduation status.
    Schema isn't 100% stable (Autobrowse is fast-moving), so we look for
    durable signals: "graduated" / "did not graduate" + "iteration N/M".
    """
    text = stdout.lower()
    passed = "graduated" in text and "did not graduate" not in text

    # Pick the LAST iteration line — Autobrowse counts up, so the final
    # iteration number is the one that mattered. First-match would always
    # return 1 even on a 5-iteration converge.
    iter_matches = re.findall(r"iteration\s+(\d+)\s*/\s*\d+", text)
    iterations_used = int(iter_matches[-1]) if iter_matches else 0

    skill_match = re.search(r"(/[^\s]+/SKILL\.md)", stdout)
    skill_md_path = skill_match.group(1) if skill_match else None

    reasons = []
    for line in stdout.splitlines():
        ll = line.strip()
        if ll.startswith(("FAIL", "REASON", "ERROR")):
            reasons.append(ll[:200])

    summary = stdout[-500:] if stdout else ""
    return passed, reasons, skill_md_path, iterations_used, summary


def verify_web(
    *,
    skill_id: str,
    eval_seed: str,
    iterations: int = 5,
    env: str = "local",
    timeout_seconds: int = 600,
) -> VerifyResult:
    """Run Autobrowse against the eval_seed. Returns a uniform VerifyResult.

    `env` is "local" (default — headed Chrome, no API key) per the council's
    ratified shape; "remote" exists for bot-protected sites but isn't the
    default cost-basis path.
    """
    if not autobrowse_available():
        return VerifyResult(
            passed=False,
            reasons=["autobrowse not_available — install browserbase/browse-plugin or fall back to chairman_rubric"],
            iterations_used=0,
            summary="autobrowse subprocess not on PATH",
        )

    slug = _slug_from_skill_id(skill_id)
    cmd = [
        "npx",
        "--no-install",
        "autobrowse",
        "--task", slug,
        "--env", env,
        "--iterations", str(iterations),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            input=eval_seed,
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            passed=False,
            reasons=[f"autobrowse timed out after {timeout_seconds}s"],
            summary="timeout",
        )
    except OSError as exc:
        return VerifyResult(
            passed=False,
            reasons=[f"autobrowse subprocess failed: {exc}"],
            summary=str(exc),
        )

    passed, reasons, skill_md_path, iterations_used, summary = parse_autobrowse_output(result.stdout or "")
    if result.returncode != 0:
        # Non-zero exit = failure regardless of stdout claims
        passed = False
        reasons.append(f"autobrowse exit code {result.returncode}")
        if result.stderr:
            reasons.append(f"stderr: {result.stderr[:200]}")
    return VerifyResult(
        passed=passed,
        reasons=reasons,
        skill_md_path=skill_md_path,
        iterations_used=iterations_used,
        summary=summary,
    )
