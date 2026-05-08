"""trinity-local council-last — instant council on your last Claude Code prompt.

Per council_35b2ae198a65b349: onboarding (c) — instant council on a recent
prompt — beats (a) demo-seed, (b) auto-build wait, and (d) empty state.
The council also ratified "no clipboard auto-read" (privacy self-own);
last-Claude-Code-prompt or explicit --task is the safer path.

Flow:
  1. Find the most recently modified Claude Code session JSONL
     (~/.claude/projects/*/<session>.jsonl)
  2. Walk its turns, pick the LAST user turn
  3. Show the prompt + ask for confirmation
  4. On confirm, dispatch trinity-local council-launch with that prompt

If --yes is passed (for harness / scripting use), skips the prompt.
If --task is passed, uses that text directly (the explicit-paste path
the council preferred to clipboard auto-read).
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from ..ingest import iter_prompt_turns, parse_claude_code_session


def register(subparsers):
    parser = subparsers.add_parser(
        "council-last",
        help="Council your last Claude Code prompt (onboarding flow for new users).",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Explicit prompt text (skips auto-detection of last Claude Code prompt).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt; immediately fire the council.",
    )
    parser.add_argument(
        "--members",
        nargs="+",
        default=["claude", "gemini", "codex"],
        help="Council members.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be councilled without firing.",
    )
    parser.set_defaults(handler=handle_council_last)


def _find_last_user_prompt() -> tuple[str | None, str | None]:
    """Walk ~/.claude/projects/ for the most recently-modified .jsonl, pick
    the LAST user turn from it. Returns (prompt_text, source_path) or
    (None, None) if no Claude Code history found."""
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return None, None

    sessions = list(root.glob("*/*.jsonl"))
    if not sessions:
        return None, None
    sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for session_path in sessions[:5]:  # check up to 5 most recent for content
        session = parse_claude_code_session(session_path)
        if session is None:
            continue
        turns = list(iter_prompt_turns(session))
        if not turns:
            continue
        # Take the LAST user turn — what the user just asked
        last = turns[-1]
        text = (last.text or "").strip()
        if text and len(text) >= 10:
            return text, str(session_path)
    return None, None


def handle_council_last(args):
    if args.task:
        prompt = args.task.strip()
        source = "(--task argument)"
    else:
        prompt, source = _find_last_user_prompt()
        if not prompt:
            print(json.dumps({
                "ok": False,
                "error": "no Claude Code history found at ~/.claude/projects/",
                "fix": "open Claude Code and ask one prompt, then re-run, OR pass --task \"<your prompt>\"",
            }, indent=2))
            return 1

    if args.dry_run or not args.yes:
        # Show the prompt + source so the user can confirm before any chairman call
        preview = prompt if len(prompt) <= 280 else prompt[:280] + "…"
        print(f"Found prompt from {source}:")
        print()
        print(f"  {preview}")
        print()
        if args.dry_run:
            print(f"Would council with members: {', '.join(args.members)}")
            return 0
        try:
            response = input(f"Council this prompt with {', '.join(args.members)}? [Y/n] ")
        except (EOFError, KeyboardInterrupt):
            print()  # clean newline
            print(json.dumps({"ok": False, "error": "canceled"}))
            return 1
        if response.strip().lower() in ("n", "no"):
            print(json.dumps({"ok": False, "error": "user declined"}))
            return 1

    # Dispatch council-launch as a subprocess so we reuse the full launch flow
    # (notification, status writing, browser open) without replicating it.
    cmd = [
        sys.executable, "-m", "trinity_local.main",
        "council-launch",
        "--task", prompt,
        "--members", *args.members,
        "--cwd", ".",
        "--open-browser",
    ]
    print(f"Firing: {' '.join(shlex.quote(c) for c in cmd)}")
    return subprocess.call(cmd)
