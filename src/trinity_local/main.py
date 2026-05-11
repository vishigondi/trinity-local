from __future__ import annotations

import argparse
import importlib
from collections.abc import Iterable
from types import ModuleType


CORE_COMMAND_MODULES = (
    "actions",
    "adapters",
    "cache",
    "cortex",
    "council",
    "council_last",
    "doctor",
    "ingest",
    "me",
    "me_card",
    "metric",
    "portal",
    "replay",
    "research",
    "review",
    "seed",
    "shortcuts",
    "status",
    "tasks",
    "telemetry",
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
