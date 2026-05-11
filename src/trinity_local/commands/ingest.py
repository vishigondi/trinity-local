"""Handler for the `features` command — extracts compact session features
from the user's local transcripts (Claude Code, Codex, Gemini CLI, Cowork).
Used for offline debugging / analysis; not on the live product path.

The companion `examples` command was removed alongside v2 trained-coordinator
sunset — it produced training data for a coordinator we're no longer training.
"""
from __future__ import annotations

import json

from ..feature_extractors import extract_session_features
from ..ingest import (
    iter_claude_code_sessions,
    iter_codex_sessions,
    iter_cowork_sessions,
    iter_gemini_cli_sessions,
)


def _load_sessions(source: str) -> list:
    if source == "claude":
        return list(iter_claude_code_sessions())
    if source == "codex":
        return list(iter_codex_sessions())
    if source == "gemini":
        return list(iter_gemini_cli_sessions())
    if source == "cowork":
        return list(iter_cowork_sessions())
    if source == "all":
        sessions = []
        sessions.extend(iter_claude_code_sessions())
        sessions.extend(iter_codex_sessions())
        sessions.extend(iter_gemini_cli_sessions())
        sessions.extend(iter_cowork_sessions())
        return list(sessions)
    raise ValueError(f"Unknown source: {source}")


def register(subparsers):
    features_parser = subparsers.add_parser("features", help="Extract compact session features")
    features_parser.add_argument("--source", default="all", choices=["all", "claude", "codex", "gemini", "cowork"])
    features_parser.add_argument("--limit", type=int, default=10)
    features_parser.set_defaults(handler=handle_features)


def handle_features(args):
    sessions = _load_sessions(args.source)
    features = [extract_session_features(session).to_dict() for session in sessions[: args.limit]]
    print(json.dumps(features, indent=2))
