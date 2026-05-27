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
    # `adapters` CLI verb retired 2026-05-27 (commit 6a03d10 follow-up) —
    # `trinity-local status` already shows provider adapter status; the
    # dedicated verb was a duplicate surface with zero unique value.
    # The src/trinity_local/adapters.py library module survives (used by
    # status / setup_guidance / launchpad_data). See retired_names.py.
    "cortex",
    "council",
    "debug",
    # `decision_log` CLI verb retired 2026-05-27 — see retired_names.py.
    # The me/decisions.py loader survives so existing decision_log.jsonl
    # files keep flowing into lens-build at weight=2.0.
    "download_embedder",
    "dream",
    "eval",
    "eval_import",
    "extension_repair",
    "import_export",
    "install_umbrella",
    "lens_import",
    "me",
    "me_card",
    "moves",
    "portal",
    # `replay` CLI verb retired 2026-05-27 — see retired_names.py.
    # The natural way to populate the routing table is to use Trinity
    # normally; council outcomes accumulate on disk and aggregate
    # automatically via compute_personal_routing_table().
    "review",
    "seed",
    "status",
    "telemetry",
    "update",
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

    # `metavar` overrides argparse's auto-generated choice list (which
    # would print all 40+ registered subparsers in both the usage line
    # AND the descriptive table heading). The {install,status,...}
    # form gives the user the canonical 5 verbs at a glance.
    subparsers = parser.add_subparsers(
        dest="command",
        required=False,
        metavar="{install,status,update,dream,debug}",
    )

    for module in _iter_command_modules():
        module.register(subparsers)

    _hide_non_canonical_from_help(subparsers)
    return parser


# Area 5: CLI consolidation. The user-visible surface is exactly these
# five verbs; everything else stays registered (the launchpad's Native
# Messaging dispatch and the Chrome extension's action allowlist both
# call subparsers by name — dropping the registrations would break
# real flows) but gets `help=argparse.SUPPRESS`'d so it doesn't appear
# in `trinity-local --help`. Power-user verbs are reachable both by
# their original names AND under `trinity-local debug <subcmd>` for
# discoverability.
USER_FACING_COMMANDS = frozenset({
    "install",
    "status",
    "update",
    "dream",
    "debug",
})


def _hide_non_canonical_from_help(subparsers: argparse._SubParsersAction) -> None:
    """Suppress non-canonical subparsers from `--help` output without
    dropping them from the live argparse surface.

    Two reasons subparsers stay registered:
      - Launchpad dispatch fires `trinity-local council-launch …` via
        Chrome Native Messaging. Dropping the registration breaks the
        dispatcher.
      - Power users may still type the bare names. They keep working;
        they're just no longer advertised.

    Mechanism: argparse formats subparser help by iterating
    `subparsers._choices_actions`. Setting `help = argparse.SUPPRESS`
    leaks the literal "==SUPPRESS==" string into the output (it's
    only honored for argument actions, not subparser choices), so we
    remove the entries entirely. The parsers stay in `subparsers.choices`
    — still callable, just no longer advertised in `--help`.
    """
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions
        if action.dest in USER_FACING_COMMANDS
    ]


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
