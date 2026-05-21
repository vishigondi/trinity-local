"""Handler for `trinity-local handoff <provider>` — continue a
conversation in a different model.

This is the CLI wrapper around `handoff.run_handoff()`. The MCP-side
exposure lives in `mcp_server.py` so the agent can call it inline
from inside Claude Code / Codex CLI / Gemini CLI.

Demo path (task #120):
  1. User just had a conversation in Claude Code.
  2. Runs `trinity-local handoff gemini`.
  3. Gemini receives the prior conversation as context and continues.
  4. "Wait, how did Gemini know what we were talking about?" — that's
     the demo working. The wedge is structurally non-refutable: only
     Trinity has the cross-provider prompt index.
"""
from __future__ import annotations

import json

from ..handoff import DEFAULT_TURNS, run_handoff


def register(subparsers):
    sp = subparsers.add_parser(
        "handoff",
        help="Continue your most-recent conversation in a different model (cross-provider continuity)",
    )
    sp.add_argument(
        "provider",
        help="Target provider (e.g. claude, codex, antigravity). Receives the prior conversation as context.",
    )
    sp.add_argument(
        "-c", "--continuation",
        default=None,
        help="Optional new question to ask. If omitted, the target model just continues the thread.",
    )
    sp.add_argument(
        "-n", "--num-turns",
        type=int,
        default=DEFAULT_TURNS,
        help=f"How many prior (user, assistant) pairs to include (default {DEFAULT_TURNS})",
    )
    sp.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Output the full result as JSON (target_provider, response_text, source_providers, ...)",
    )
    sp.set_defaults(handler=handle_handoff)


def handle_handoff(args):
    from ..config import load_config

    config = load_config(getattr(args, "config", None), required=True)
    provider_configs = {name: p for name, p in config.providers.items() if p.enabled}
    result = run_handoff(
        args.provider,
        provider_configs,
        continuation=args.continuation,
        num_turns=args.num_turns,
    )

    if args.as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    if result.error:
        print(f"✗ handoff to {args.provider} failed:")
        print(f"  {result.error}")
        if result.context_turns:
            print(f"  (context loaded: {result.context_turns} turn(s) from {', '.join(result.source_providers)})")
        raise SystemExit(2)

    # Human-readable: header line then the model's response. The
    # header lands the wedge ("the prior turns came from X provider(s),
    # now Y continued the thread") so the user sees the magic working.
    src = ", ".join(result.source_providers) if result.source_providers else "(unknown)"
    print(
        f"→ handed off to {result.target_provider}"
        f"{f' ({result.target_model})' if result.target_model else ''}"
        f" — {result.context_turns} prior turn(s) from {src}, "
        f"{result.elapsed_seconds:.1f}s"
    )
    print()
    print(result.response_text)
