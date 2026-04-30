from __future__ import annotations

import argparse

from .commands import (
    actions,
    adapters,
    cache,
    council,
    daemon,
    digest,
    ingest,
    portal,
    research,
    review,
    shortcuts,
    status,
    tasks,
    telemetry,
    watch,
    workflow,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trinity-local")
    parser.add_argument("--config", help="Path to config.json", default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register all command groups
    ingest.register(subparsers)
    tasks.register(subparsers)
    council.register(subparsers)
    portal.register(subparsers)
    actions.register(subparsers)
    shortcuts.register(subparsers)
    watch.register(subparsers)
    workflow.register(subparsers)
    digest.register(subparsers)
    review.register(subparsers)
    adapters.register(subparsers)
    status.register(subparsers)
    telemetry.register(subparsers)
    daemon.register(subparsers)
    research.register(subparsers)
    cache.register(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "handler"):
        parser.error(f"Unknown command: {args.command}")

    args.handler(args)


if __name__ == "__main__":
    main()
