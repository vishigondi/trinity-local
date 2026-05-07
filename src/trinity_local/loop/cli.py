"""trinity-loop CLI — supervisor for the Loop Constitution double-loop.

Subcommands:
- frame   — outer loop. One chairman call emits inversions + eval_seed.
- run     — inner loop. Iterates execute → verify → cull → re-verify → commit.
- reframe — outer-loop rerun on stale skills (eviction trigger).

Per council_5fbf909119830643: "supervisor owns continuity, no daemon" — this
CLI is the supervisor. State machine in run.py persists to state.json so each
run can resume after crash.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..utils import now_iso
from .frame import (
    Frame,
    parse_frame_output,
    render_frame_prompt,
    save_frame,
    skill_dir,
    stable_skill_id,
    validate_frame,
)


def _resolve_chairman():
    """Pick + load the chairman provider via the same path me_builder uses.

    Returns (chairman_name, chairman_config, primary_provider).
    """
    from ..config import load_config
    from ..providers import make_provider
    from ..ranker import predict_strongest_chairman

    config = load_config()
    available = [
        name for name, p in (config.providers if config else {}).items()
        if p.enabled and p.type in ("cli", "codex")
    ]
    chairman = predict_strongest_chairman(
        "Frame a skill: emit inversions and an eval_seed.",
        available_providers=available or ["claude"],
    )
    chairman_config = config.providers.get(chairman) if config else None
    if chairman_config is None or not chairman_config.enabled:
        chairman = available[0] if available else ""
        chairman_config = config.providers.get(chairman) if (config and chairman) else None
    if chairman_config is None:
        raise RuntimeError("trinity-loop requires at least one enabled provider in config")
    return chairman, chairman_config, make_provider(chairman_config)


def handle_frame(args):
    """One chairman call → Frame, persisted to ~/.trinity/skills/<id>/frame.json."""
    intent = args.intent.strip()
    if len(intent) < 8:
        print(json.dumps({"ok": False, "error": "intent too short (≥8 chars)"}))
        return 1

    chairman, chairman_config, primary = _resolve_chairman()

    prompt = render_frame_prompt(intent)
    result = primary.run(prompt, cwd=Path.cwd())
    raw = result.stdout or ""
    inversions, eval_seed, verifier = parse_frame_output(raw)

    ok, reason = validate_frame(inversions, eval_seed)
    if not ok:
        print(json.dumps({
            "ok": False,
            "error": f"frame validation failed: {reason}",
            "inversions_count": len(inversions),
            "eval_seed_chars": len(eval_seed),
            "stderr": (result.stderr or "")[:300],
        }, indent=2))
        return 2

    skill_id = stable_skill_id(intent)
    f = Frame(
        skill_id=skill_id,
        intent=intent,
        inversions=inversions,
        eval_seed=eval_seed,
        verifier=verifier,
        model_baseline={chairman: chairman_config.model or ""},
        created_at=now_iso(),
    )
    path = save_frame(f)
    print(json.dumps({
        "ok": True,
        "skill_id": skill_id,
        "frame_path": str(path),
        "inversions_count": len(inversions),
        "verifier": verifier,
        "chairman": chairman,
    }, indent=2))
    return 0


def handle_run(args):
    """Inner loop. Imported lazily so frame.py works without run.py present
    (commit boundary)."""
    try:
        from .run import run_inner_loop
    except ImportError:
        print(json.dumps({"ok": False, "error": "loop/run.py not yet implemented"}))
        return 1
    return run_inner_loop(args.skill, max_iter=args.max_iter)


def handle_reframe(args):
    print(json.dumps({"ok": False, "error": "reframe not yet implemented"}))
    return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    """Attach `trinity-loop frame|run|reframe` to main.py's argparse tree."""
    loop = subparsers.add_parser(
        "loop",
        help="Loop Constitution v2 — outer/inner loops for skill graduation.",
    )
    loop_sub = loop.add_subparsers(dest="loop_command", required=True)

    frame_p = loop_sub.add_parser("frame", help="Outer loop: emit inversions + eval_seed.")
    frame_p.add_argument("--intent", required=True, help="Skill intent (one sentence).")
    frame_p.set_defaults(handler=handle_frame)

    run_p = loop_sub.add_parser("run", help="Inner loop: iterate execute→verify→cull→re-verify→commit.")
    run_p.add_argument("--skill", required=True, help="skill_id from a prior frame call.")
    run_p.add_argument("--max-iter", type=int, default=5)
    run_p.set_defaults(handler=handle_run)

    reframe_p = loop_sub.add_parser("reframe", help="Re-run outer on stale skills (eviction).")
    reframe_p.add_argument("--on-model-release", action="store_true")
    reframe_p.set_defaults(handler=handle_reframe)
