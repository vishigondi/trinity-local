"""Handlers for cache-stats and cache-clear."""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser("cache-stats", help="Show embedding cache statistics")
    sp.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    sp.set_defaults(handler=handle_cache_stats)

    cp = subparsers.add_parser("cache-clear", help="Clear the embedding cache")
    cp.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    cp.set_defaults(handler=handle_cache_clear)


def handle_cache_stats(args):
    from ..embeddings.cache import cache_stats

    stats = cache_stats()

    if args.as_json:
        print(json.dumps(stats, indent=2))
        return

    print("  Embedding Cache")
    print(f"    Entries:  {stats['entries']:,}")
    size_kb = stats["size_bytes"] / 1024
    if size_kb < 1024:
        print(f"    Size:     {size_kb:.1f} KB")
    else:
        print(f"    Size:     {size_kb / 1024:.2f} MB")
    print(f"    Path:     {stats['path']}")
    print()


def handle_cache_clear(args):
    from ..embeddings.cache import cache_stats, clear_cache

    stats = cache_stats()
    if stats["entries"] == 0:
        print("  Cache is already empty.")
        return

    if not args.yes:
        answer = input(f"  Clear {stats['entries']:,} cached embeddings? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("  Cancelled.")
            return

    cleared = clear_cache()
    print(f"  ✓ Cleared {cleared:,} cached embeddings.")
