"""Outer loop — one chairman call emits inversions + eval_seed for a skill intent.

Per council_7a770b8b78b6bd4e: invert + plan stay merged into ONE chairman call by
default. Only split if validation reveals signal loss. Compression preserved.

Output written to ~/.trinity/skills/<id>/frame.json. Inner loop reads this as
the rubric for execute / verify / cull stages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..state_paths import state_dir


def skills_dir() -> Path:
    """Registry root. Each skill is a folder under ~/.trinity/skills/<id>/."""
    path = state_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def skill_dir(skill_id: str) -> Path:
    path = skills_dir() / skill_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Frame:
    """Outer-loop output. `eval_seed` is the rubric the inner loop verifies against."""
    skill_id: str
    intent: str
    inversions: list[str] = field(default_factory=list)
    eval_seed: str = ""
    verifier: str = "chairman_rubric"  # or "autobrowse" for web-task skills
    model_baseline: dict[str, str] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "intent": self.intent,
            "inversions": self.inversions,
            "eval_seed": self.eval_seed,
            "verifier": self.verifier,
            "model_baseline": self.model_baseline,
            "created_at": self.created_at,
        }


def render_frame_prompt(intent: str) -> str:
    """One chairman prompt that emits inversions + eval_seed in a single JSON block.

    Per council ratification: keep one-call framing unless validation fails.
    """
    return f"""You are framing a skill the user wants to graduate. The user describes the
intent below. Your job: emit the rails this skill must run within, in ONE pass.

A "frame" has two parts, both required:

1. INVERSIONS — 3 to 7 named cases this skill would FAIL on. Always invert. The
   inversions are how the inner loop knows when verify should reject. Each
   inversion is a concrete failure scenario, not an abstract worry.

2. EVAL_SEED — a one-paragraph rubric the verifier uses to decide if a skill
   attempt passed or failed. It must be specific enough that two independent
   readers would agree on the pass/fail verdict for a given attempt.

Also classify the verifier type:

- "autobrowse" — if this skill operates on a live website (form filling,
  scraping, multi-step web tasks). Browserbase Autobrowse will run it.
- "chairman_rubric" — for everything else (code, prompts, research, analysis).
  A future chairman call will judge against the eval_seed.

Output ONE JSON object. No markdown fences, no commentary outside the JSON:

{{
  "inversions": ["...", "...", "..."],
  "eval_seed": "...",
  "verifier": "autobrowse" | "chairman_rubric"
}}

Hard requirements:
- inversions length between 3 and 7 inclusive
- eval_seed length ≥ 80 characters (must be a real paragraph, not a tagline)
- verifier is exactly one of the two enum values

INTENT:

{intent}
"""


def parse_frame_output(raw: str) -> tuple[list[str], str, str]:
    """Parse chairman output. Tolerates markdown fences, extracts the JSON object.

    Returns (inversions, eval_seed, verifier). Empty values on parse failure;
    caller is responsible for the validation check that requires non-empty.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return [], "", "chairman_rubric"
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return [], "", "chairman_rubric"

    inversions_raw = obj.get("inversions") or []
    inversions = [
        str(s).strip()
        for s in inversions_raw
        if isinstance(s, str) and s.strip()
    ]
    eval_seed = (obj.get("eval_seed") or "").strip()
    verifier = (obj.get("verifier") or "chairman_rubric").strip().lower()
    if verifier not in {"autobrowse", "chairman_rubric"}:
        verifier = "chairman_rubric"
    return inversions, eval_seed, verifier


def validate_frame(inversions: list[str], eval_seed: str) -> tuple[bool, str]:
    """Per the prompt's hard requirements. Returns (ok, reason)."""
    if not (3 <= len(inversions) <= 7):
        return False, f"inversions count {len(inversions)} not in [3, 7]"
    if len(eval_seed) < 80:
        return False, f"eval_seed too short: {len(eval_seed)} < 80 chars"
    return True, ""


def stable_skill_id(intent: str) -> str:
    """Deterministic id from intent text.

    `stable_id('skill', intent)` already returns "skill_<hash>" — using it
    directly avoids a doubled prefix.
    """
    from ..utils import stable_id
    return stable_id("skill", intent)


def save_frame(frame: Frame) -> Path:
    path = skill_dir(frame.skill_id) / "frame.json"
    path.write_text(json.dumps(frame.to_dict(), indent=2))
    return path


def load_frame(skill_id: str) -> Frame | None:
    path = skills_dir() / skill_id / "frame.json"
    if not path.exists():
        return None
    obj = json.loads(path.read_text())
    return Frame(**obj)


def frame(intent: str) -> Frame:
    """Outer loop: one chairman call → Frame.

    Caller dispatches the chairman call (we can't call providers from a pure
    function — provider config + chairman picker live up the stack). This
    function is split for testability: render prompt, parse output, build
    Frame. The CLI / MCP entry point in cli.py wires the chairman call.
    """
    raise NotImplementedError(
        "Use cli.frame_subcommand or programmatic dispatch in mcp_server. "
        "This module exposes render_frame_prompt + parse_frame_output for testing."
    )
