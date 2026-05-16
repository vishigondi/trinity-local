from __future__ import annotations

import argparse
import importlib
import os
from collections.abc import Iterable
from types import ModuleType


def _pin_hf_offline() -> None:
    """Default Trinity to fully offline behavior for the HuggingFace Hub.

    Trinity should never make outbound HF calls during normal operation —
    embeddings rely on a model that's already cached at
    ``~/.cache/huggingface/hub/`` (or wherever ``HF_HOME`` points). The
    one-time download is a deliberate user action via
    ``huggingface-cli download nomic-ai/nomic-embed-text-v1.5`` (or by
    running once with ``HF_HUB_OFFLINE=0 trinity-local seed-from-taste-terminal``).

    Why setdefault and not unconditional set: a user who explicitly wants
    online behavior (e.g. CI pulling fresh model weights) can export
    ``HF_HUB_OFFLINE=0`` before invoking ``trinity-local`` and we honor it.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    # Suppress the "no telemetry permission" log line that fires even when
    # the rest of HF is fully offline.
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


CORE_COMMAND_MODULES = (
    "actions",
    "adapters",
    "bootstrap_pairs",
    "cache",
    "cortex",
    "council",
    "council_last",
    "depth",
    "distill",
    "doctor",
    "dream",
    "eval",
    "handoff",
    "ingest",
    "me",
    "me_card",
    "merges",
    "metric",
    "portal",
    "replay",
    "research",
    "review",
    "seed",
    "shortcuts",
    "stats",
    "status",
    "tasks",
    "telemetry",
    "trust",
    "unrated",
    "vocabulary",
    "watch",
)

OPTIONAL_COMMAND_MODULES = (
    "install",
)


def _module_path(name: str) -> str:
    package = __package__ or "trinity_local"
    return f"{package}.{name}"


def _import_optional(module_path: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            return None
        raise


def _iter_command_modules() -> Iterable[ModuleType]:
    for name in CORE_COMMAND_MODULES:
        yield importlib.import_module(_module_path(f"commands.{name}"))
    for name in OPTIONAL_COMMAND_MODULES:
        module = _import_optional(_module_path(f"commands.{name}"))
        if module is not None:
            yield module


def _load_mcp_runner():
    module_path = _module_path("mcp_server")
    module = _import_optional(module_path)
    if module is None:
        raise SystemExit("error: MCP server support is not available in this checkout.")
    return module.run_stdio_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trinity-local")
    parser.add_argument("--config", help="Path to config.json", default=None)

    subparsers = parser.add_subparsers(dest="command", required=False)

    for module in _iter_command_modules():
        module.register(subparsers)

    return parser


def main() -> None:
    _pin_hf_offline()
    parser = build_parser()
    parser.add_argument("--mcp", action="store_true", help="Run as an MCP server")
    args = parser.parse_args()

    if args.mcp:
        import asyncio
        try:
            asyncio.run(_load_mcp_runner()())
        except KeyboardInterrupt:
            pass
        return

    if not args.command:
        parser.print_help()
        return

    if not hasattr(args, "handler"):
        parser.error(f"Unknown command: {args.command}")

    args.handler(args)


if __name__ == "__main__":
    main()
