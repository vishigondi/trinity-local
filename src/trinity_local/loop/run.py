"""Inner loop — execute → verify → cull → re-verify → commit, iterated.

Council `council_5fbf909119830643` substrate + `council_7a770b8b78b6bd4e`
modifications:

- Model called per-stage. Each iteration is 1 chairman call (execute) +
  1 verify (Autobrowse for web tasks, chairman-rubric otherwise) +
  1 chairman call (cull) + 1 conditional re-verify.
- State persists to ~/.trinity/skills/<id>/state.json so the loop
  resumes after crash. The supervisor IS this CLI process; no daemon.
- Cull → re-verify → commit is non-negotiable. **Re-verify gate is
  hash-based** (Codex's eval seed for this council): compute
  sha256(pre_cull) != sha256(post_cull); only re-verify when the cull
  actually mutated the artifact.
- state.history carries STRUCTURED records (not raw failure strings)
  so the next iteration's execute prompt pulls structured fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils import now_iso
from .frame import Frame, load_frame, skill_dir


def state_path(skill_id: str) -> Path:
    return skill_dir(skill_id) / "state.json"


@dataclass
class HistoryRecord:
    """One structured entry in state.history. Per council ratification, the
    inner loop carries structured fields, not raw failure strings."""
    iteration: int
    stage: str  # "verify" | "cull" | "re_verify" | "commit"
    outcome: str  # "passed" | "failed" | "noop" | "mutated"
    reasons: list[str] = field(default_factory=list)
    artifact_hash_before: str | None = None
    artifact_hash_after: str | None = None
    cull_proposal_id: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "stage": self.stage,
            "outcome": self.outcome,
            "reasons": self.reasons,
            "artifact_hash_before": self.artifact_hash_before,
            "artifact_hash_after": self.artifact_hash_after,
            "cull_proposal_id": self.cull_proposal_id,
            "timestamp": self.timestamp,
        }


@dataclass
class State:
    skill_id: str
    iteration: int = 0
    artifact: str = ""
    history: list[HistoryRecord] = field(default_factory=list)
    graduated: bool = False
    failed_to_graduate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "iteration": self.iteration,
            "artifact": self.artifact,
            "history": [r.to_dict() for r in self.history],
            "graduated": self.graduated,
            "failed_to_graduate": self.failed_to_graduate,
        }

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "State":
        return cls(
            skill_id=obj["skill_id"],
            iteration=int(obj.get("iteration") or 0),
            artifact=str(obj.get("artifact") or ""),
            history=[HistoryRecord(**r) for r in (obj.get("history") or [])],
            graduated=bool(obj.get("graduated")),
            failed_to_graduate=bool(obj.get("failed_to_graduate")),
        )


def save_state(state: State) -> Path:
    path = state_path(state.skill_id)
    path.write_text(json.dumps(state.to_dict(), indent=2))
    return path


def load_state(skill_id: str) -> State | None:
    path = state_path(skill_id)
    if not path.exists():
        return None
    try:
        return State.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def artifact_hash(artifact: str) -> str:
    """sha256 — used for the cull-mutation gate (council eval seed)."""
    return "sha256:" + hashlib.sha256(artifact.encode("utf-8")).hexdigest()


def render_execute_prompt(frame: Frame, state: State) -> str:
    """Per the structured-state-history modification: the next iteration's
    execute prompt pulls structured fields from history rather than a raw
    concatenation of failure strings."""
    failures = [r for r in state.history if r.outcome == "failed"]
    failure_block = ""
    if failures:
        failure_block = "\n\nPRIOR ATTEMPTS FAILED FOR THESE STRUCTURED REASONS:\n"
        for r in failures[-3:]:  # cap at last 3 to keep prompt focused
            failure_block += f"- iteration {r.iteration} ({r.stage}): " + "; ".join(r.reasons[:3]) + "\n"

    return f"""Generate the artifact for this skill. The frame's eval_seed is the
rubric you'll be tested against; aim to satisfy it on the first attempt.

INTENT: {frame.intent}

EVAL_SEED (the rubric):
{frame.eval_seed}

INVERSIONS (cases this skill must NOT fail on):
{chr(10).join(f"- {inv}" for inv in frame.inversions)}{failure_block}

Output: the skill artifact ONLY. No commentary, no markdown fences around
the whole output, no preamble. Match whatever format the eval_seed implies
(markdown for docs, code blocks for executable skills, JSON for structured
output, etc.)."""


def render_verify_prompt(frame: Frame, artifact: str) -> str:
    """Chairman-rubric verify (used when frame.verifier == 'chairman_rubric').

    Output is a structured pass/fail with reasons, matching VerifyResult shape.
    """
    return f"""You are verifying a skill artifact against its rubric. Apply the eval_seed
strictly. If any inversion case applies to the artifact below, fail it.

EVAL_SEED:
{frame.eval_seed}

INVERSIONS (any of these should trigger failure):
{chr(10).join(f"- {inv}" for inv in frame.inversions)}

ARTIFACT:
{artifact}

Output ONE JSON object, no markdown fences, no commentary outside the JSON:

{{
  "passed": true | false,
  "reasons": ["<concrete reason>", "<concrete reason>", ...]
}}

Rules:
- "reasons" is required even when passed=true (≥1 reason that confirms
  the rubric was met). Without reasons, the verdict isn't auditable.
- If you'd say "looks fine" rather than name a reason, the artifact
  hasn't earned a pass — return false."""


def parse_verify_output(raw: str) -> tuple[bool, list[str]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return False, ["verify parser: no JSON object in output"]
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return False, [f"verify parser: JSON decode error — {exc}"]
    passed = bool(obj.get("passed"))
    reasons = [str(r) for r in (obj.get("reasons") or []) if isinstance(r, str)]
    if not reasons:
        # Per the prompt's own rule — no reasons means no audit trail
        return False, ["verify output had no reasons"]
    return passed, reasons


def render_cull_prompt(frame: Frame, artifact: str, verify_reasons: list[str]) -> str:
    """Cull-as-tool-call: explicit "what would you remove and why?" pass."""
    return f"""You are culling a skill artifact that just passed verification. Kill the
darlings. What's redundant, decorative, or off-target relative to the
eval_seed? Cut it. If nothing should be cut, say so explicitly.

EVAL_SEED:
{frame.eval_seed}

VERIFY REASONS (what verify said earned the pass):
{chr(10).join(f"- {r}" for r in verify_reasons)}

CURRENT ARTIFACT:
{artifact}

Output ONE JSON object, no markdown fences:

{{
  "removed": ["<one line per cut, naming what came out and why>"],
  "artifact": "<the artifact AFTER cuts; identical to input if nothing was cut>"
}}

Rules:
- If you cut nothing, "removed" is [] and "artifact" matches input verbatim.
- Cuts should sharpen the artifact against the eval_seed, not weaken it.
  If you can't cut without breaking the rubric, don't cut."""


def parse_cull_output(raw: str, original: str) -> tuple[list[str], str]:
    """Returns (removed_reasons, post_cull_artifact). Falls back to
    (no_op, original) on parse failure — defensive: chairman drift never
    silently rewrites the artifact."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return [], original
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return [], original
    removed = [str(r) for r in (obj.get("removed") or []) if isinstance(r, str)]
    post = obj.get("artifact")
    if not isinstance(post, str) or not post.strip():
        return removed, original
    return removed, post


def commit_skill(skill_id: str, frame: Frame, artifact: str, verify_reasons: list[str], state: State) -> Path:
    """Write the graduated skill to ~/.trinity/skills/<id>/SKILL.md plus the
    test (eval.json) that proved it and the rationale.

    Per council substrate: skills ship with a passing test as the commit
    gate. The eval.json IS the test artifact.
    """
    sdir = skill_dir(skill_id)
    skill_md = sdir / "SKILL.md"
    skill_md.write_text(artifact)
    eval_path = sdir / "eval.json"
    eval_path.write_text(json.dumps({
        "eval_seed": frame.eval_seed,
        "inversions": frame.inversions,
        "verify_reasons": verify_reasons,
        "iterations_to_graduate": state.iteration,
        "passed_at": now_iso(),
    }, indent=2))
    rationale = sdir / "rationale.md"
    rationale.write_text(
        f"# {skill_id}\n\n"
        f"## Intent\n{frame.intent}\n\n"
        f"## Why this skill exists\n"
        f"Graduated after {state.iteration} iterations. Passed the eval_seed:\n\n"
        f"> {frame.eval_seed}\n\n"
        f"## Failure modes the inversions warned about\n"
        + "\n".join(f"- {inv}" for inv in frame.inversions)
        + "\n"
    )
    return skill_md


def run_inner_loop(skill_id: str, *, max_iter: int = 5) -> int:
    """The state machine. CLI entry point; pipes stdout JSON for harness use.

    Lazy chairman dispatch — same path as me_builder + frame.cli.
    """
    frame = load_frame(skill_id)
    if frame is None:
        print(json.dumps({"ok": False, "error": f"no frame for skill_id={skill_id}; run `loop frame` first"}))
        return 1

    # Resume support: if a state.json exists and the run isn't terminal, pick up.
    state = load_state(skill_id) or State(skill_id=skill_id)
    if state.graduated:
        print(json.dumps({"ok": True, "skill_id": skill_id, "graduated": True, "noop": "already graduated"}))
        return 0
    if state.failed_to_graduate:
        print(json.dumps({"ok": False, "skill_id": skill_id, "failed_to_graduate": True, "noop": "previous run gave up"}))
        return 2

    from .cli import _resolve_chairman
    chairman_name, chairman_config, primary = _resolve_chairman()

    while state.iteration < max_iter:
        state.iteration += 1
        # ---- execute ----
        exec_prompt = render_execute_prompt(frame, state)
        exec_result = primary.run(exec_prompt, cwd=Path.cwd())
        artifact = (exec_result.stdout or "").strip()
        if not artifact:
            state.history.append(HistoryRecord(
                iteration=state.iteration, stage="execute", outcome="failed",
                reasons=["execute returned empty output"], timestamp=now_iso(),
            ))
            save_state(state)
            continue
        state.artifact = artifact

        # ---- verify ----
        verify_passed, verify_reasons = _run_verify(frame, artifact, primary)
        if not verify_passed:
            state.history.append(HistoryRecord(
                iteration=state.iteration, stage="verify", outcome="failed",
                reasons=verify_reasons, artifact_hash_before=artifact_hash(artifact),
                timestamp=now_iso(),
            ))
            save_state(state)
            continue
        state.history.append(HistoryRecord(
            iteration=state.iteration, stage="verify", outcome="passed",
            reasons=verify_reasons, artifact_hash_before=artifact_hash(artifact),
            timestamp=now_iso(),
        ))

        # ---- cull ----
        cull_prompt = render_cull_prompt(frame, artifact, verify_reasons)
        cull_result = primary.run(cull_prompt, cwd=Path.cwd())
        removed, post_cull = parse_cull_output(cull_result.stdout or "", artifact)
        pre_hash = artifact_hash(artifact)
        post_hash = artifact_hash(post_cull)
        cull_id = f"cull_iter{state.iteration}"

        # ---- re-verify gate (HASH-BASED per council eval seed) ----
        if pre_hash != post_hash:
            state.history.append(HistoryRecord(
                iteration=state.iteration, stage="cull", outcome="mutated",
                reasons=removed,
                artifact_hash_before=pre_hash, artifact_hash_after=post_hash,
                cull_proposal_id=cull_id, timestamp=now_iso(),
            ))
            re_passed, re_reasons = _run_verify(frame, post_cull, primary)
            if not re_passed:
                # Cull broke verify — discard the cull, keep pre-cull artifact,
                # but log the failure so future iterations see it
                state.history.append(HistoryRecord(
                    iteration=state.iteration, stage="re_verify", outcome="failed",
                    reasons=re_reasons, artifact_hash_before=post_hash,
                    cull_proposal_id=cull_id, timestamp=now_iso(),
                ))
                save_state(state)
                continue
            state.history.append(HistoryRecord(
                iteration=state.iteration, stage="re_verify", outcome="passed",
                reasons=re_reasons, artifact_hash_before=post_hash,
                cull_proposal_id=cull_id, timestamp=now_iso(),
            ))
            artifact = post_cull
            verify_reasons = re_reasons
        else:
            state.history.append(HistoryRecord(
                iteration=state.iteration, stage="cull", outcome="noop",
                reasons=removed,
                artifact_hash_before=pre_hash, artifact_hash_after=post_hash,
                cull_proposal_id=cull_id, timestamp=now_iso(),
            ))

        # ---- commit ----
        skill_md_path = commit_skill(skill_id, frame, artifact, verify_reasons, state)
        state.artifact = artifact
        state.graduated = True
        state.history.append(HistoryRecord(
            iteration=state.iteration, stage="commit", outcome="passed",
            reasons=[f"wrote {skill_md_path}"], artifact_hash_before=artifact_hash(artifact),
            timestamp=now_iso(),
        ))
        save_state(state)
        print(json.dumps({
            "ok": True, "skill_id": skill_id, "graduated": True,
            "iterations": state.iteration,
            "skill_md_path": str(skill_md_path),
            "history_records": len(state.history),
        }, indent=2))
        return 0

    state.failed_to_graduate = True
    save_state(state)
    print(json.dumps({
        "ok": False, "skill_id": skill_id, "failed_to_graduate": True,
        "iterations_used": state.iteration,
        "last_failure": state.history[-1].to_dict() if state.history else None,
    }, indent=2))
    return 3


def _run_verify(frame: Frame, artifact: str, primary) -> tuple[bool, list[str]]:
    """Dispatch by frame.verifier. Returns (passed, reasons).

    Per council ratification: Autobrowse for web-task skills, chairman-rubric
    otherwise. If Autobrowse is unavailable, fall back to chairman-rubric so
    the loop doesn't crash on a fresh install.
    """
    if frame.verifier == "autobrowse":
        from .verify_web import autobrowse_available, verify_web
        if autobrowse_available():
            result = verify_web(skill_id=frame.skill_id, eval_seed=frame.eval_seed)
            return result.passed, result.reasons
        # Graceful degradation
    # chairman_rubric path (default + autobrowse fallback)
    prompt = render_verify_prompt(frame, artifact)
    result = primary.run(prompt, cwd=Path.cwd())
    return parse_verify_output(result.stdout or "")
