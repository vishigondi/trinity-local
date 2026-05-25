"""`eval-prompt` + `eval-import` — provider-side rejection-signal loop.

Sibling to lens-prompt/lens-import. Same shape, different artifact:
this one captures REFRAME / REDIRECT / SHARPENING / COMPRESSION
rejection signals that the user produced naturally during chats with
the provider. Trinity scores any future model dispatch against the
imported signals as a personal eval suite (eval-build → eval-run
chain shipped task #122).

Measurement loop: same set, scored weekly against the current lens.
Score climbing = lens improvement, observable. OpenAI's "eval skills"
pattern — evaluate a skill against the case suite it claims to handle.

Schema mapping is in ``_provider_dict_to_rejection_signal`` — keep in
sync with ``docs/evals-from-provider.md``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..me.turn_pairs import RejectionSignal, rejections_path
from ..utils import stable_id


# Same anchor + lookup logic as lens_import. Kept independent so the
# two doc files can evolve separately if one ever shifts naming.
_PROMPT_BODY_MARKER = "## The prompt — copy below this line"
_VALID_REJECTION_TYPES = {"REFRAME", "REDIRECT", "SHARPENING", "COMPRESSION"}


def _prompt_doc_path() -> Path | None:
    """Resolve docs/evals-from-provider.md (repo-relative or env override)."""
    import os
    override = os.environ.get("TRINITY_EVAL_PROMPT_DOC")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    candidate = Path(__file__).resolve().parents[3] / "docs" / "evals-from-provider.md"
    return candidate if candidate.exists() else None


def register(subparsers):
    prompt = subparsers.add_parser(
        "eval-prompt",
        help=(
            "Print the canonical provider-side eval prompt (paste into "
            "Claude/Codex/Gemini, save JSON, then `eval-import`)."
        ),
    )
    prompt.add_argument(
        "--with-instructions",
        action="store_true",
        help=(
            "Include the full doc (intro + measurement story), not just "
            "the prompt body. Default: prompt body only, so "
            "`eval-prompt | pbcopy` lands a clean paste."
        ),
    )
    prompt.set_defaults(handler=handle_eval_prompt)

    imp = subparsers.add_parser(
        "eval-import",
        help=(
            "Merge a provider's JSON-shaped rejection signals (see "
            "docs/evals-from-provider.md) into ~/.trinity/me/rejections.jsonl."
        ),
    )
    imp.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to the JSON file. Omit with --from-json to read stdin.",
    )
    imp.add_argument(
        "--from-json",
        action="store_true",
        help="Read the JSON payload from stdin instead of a file path.",
    )
    imp.add_argument(
        "--provider",
        default=None,
        help=(
            "Override the `source_provider` field in the payload. Useful "
            "when the provider's JSON omits it or you want to attribute "
            "the import differently."
        ),
    )
    imp.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + print merge plan; do not write to rejections.jsonl.",
    )
    imp.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit structured JSON to stdout instead of the human summary.",
    )
    imp.set_defaults(handler=handle_eval_import)


# ---------------------------------------------------------------------
# eval-prompt
# ---------------------------------------------------------------------


def handle_eval_prompt(args) -> int:
    doc = _prompt_doc_path()
    if doc is None:
        print(
            "error: couldn't find docs/evals-from-provider.md. Set "
            "TRINITY_EVAL_PROMPT_DOC to its absolute path if you're "
            "running from a non-checkout install.",
            file=sys.stderr,
        )
        return 1
    text = doc.read_text(encoding="utf-8")
    if args.with_instructions:
        sys.stdout.write(text)
        return 0
    idx = text.find(_PROMPT_BODY_MARKER)
    if idx < 0:
        print(
            "warning: prompt-body marker not found in doc; emitting "
            "full file. Update docs/evals-from-provider.md to restore "
            f"the '{_PROMPT_BODY_MARKER}' anchor.",
            file=sys.stderr,
        )
        sys.stdout.write(text)
        return 0
    after = text[idx:].split("\n", 2)
    body = after[-1] if len(after) == 3 else text[idx:]
    sys.stdout.write(body)
    return 0


# ---------------------------------------------------------------------
# eval-import
# ---------------------------------------------------------------------


def _provider_dict_to_rejection_signal(
    r: dict,
    source_provider: str,
    seq: int,
) -> RejectionSignal | None:
    """Map a single provider 'rejection' dict → RejectionSignal.

    Returns None when required fields are missing; caller counts skips.
    `seq` is the per-payload index, mixed into the stable id so
    re-imports collide deterministically (same input → same id), but
    two different payloads from the same provider don't collide.
    """
    rtype = (r.get("type") or "").strip().upper()
    if rtype not in _VALID_REJECTION_TYPES:
        return None
    model_quote = (r.get("model_quote") or "").strip()
    user_substitute = (r.get("user_substitute") or "").strip()
    if not model_quote or not user_substitute:
        return None
    why_signal = (r.get("why_signal") or "").strip()
    confidence = (r.get("confidence") or "medium").strip().lower()
    # Stable id: hash of the substantive content so re-running the
    # provider with the same data doesn't double-import. Source
    # provider is folded in so the same quote captured by two
    # providers stays distinct (they often phrase it differently).
    # Prefix is "r" (not "rej") to match the published rejection_signal
    # schema's ^r_ pattern — the schema is the interop contract for
    # other tools reading rejections.jsonl, the writer must conform.
    rid = stable_id(
        "r",
        source_provider,
        rtype,
        model_quote[:200],
        user_substitute[:200],
    )
    return RejectionSignal(
        id=rid,
        type=rtype,
        model_quote=model_quote,
        user_substitute=user_substitute,
        why_signal=(
            f"[{source_provider}/{confidence}] {why_signal}"
            if why_signal
            else f"[{source_provider}/{confidence}]"
        ),
        prompt_id=None,  # provider doesn't know our prompt-node ids
        basin=None,  # provider doesn't know our basin ids
        next_user_turn="",
    )


def _read_existing_ids() -> set[str]:
    """Load ids from rejections.jsonl for dedup. Skinny — just the id field."""
    path = rejections_path()
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = obj.get("id")
        if rid:
            ids.add(rid)
    return ids


def _append_signals(signals: list[RejectionSignal]) -> None:
    """Append-only write to rejections.jsonl. Same convention as turn_pairs."""
    path = rejections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for s in signals:
            fh.write(json.dumps(s.to_dict()) + "\n")


def handle_eval_import(args) -> int:
    raw: str | None = None
    if args.from_json:
        raw = sys.stdin.read()
    elif args.path:
        p = Path(args.path).expanduser()
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 1
        raw = p.read_text(encoding="utf-8")
    else:
        print(
            "error: pass a path positional arg or --from-json (stdin).",
            file=sys.stderr,
        )
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: input is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("error: top-level JSON must be an object", file=sys.stderr)
        return 2

    cli_override = getattr(args, "provider", None)
    source_provider = (
        cli_override or payload.get("source_provider") or "unknown"
    ).strip().lower()
    raw_rejections = payload.get("rejections") or []

    # Map + skip malformed.
    parsed: list[RejectionSignal] = []
    skipped = 0
    for i, r in enumerate(raw_rejections):
        if not isinstance(r, dict):
            skipped += 1
            continue
        sig = _provider_dict_to_rejection_signal(r, source_provider, i)
        if sig is None:
            skipped += 1
            continue
        parsed.append(sig)

    # Dedup against existing ids.
    existing_ids = _read_existing_ids()
    new_signals = [s for s in parsed if s.id not in existing_ids]
    duplicates = len(parsed) - len(new_signals)

    # Per-axis breakdown for human + analytics consumers.
    axis_counts: dict[str, int] = {}
    for s in new_signals:
        axis_counts[s.type] = axis_counts.get(s.type, 0) + 1

    result = {
        "ok": True,
        "source_provider": source_provider,
        "rejections": {
            "incoming": len(parsed),
            "new": len(new_signals),
            "duplicates": duplicates,
            "skipped_malformed": skipped,
            "by_axis": axis_counts,
        },
        "dry_run": bool(args.dry_run),
    }

    if not args.dry_run and new_signals:
        _append_signals(new_signals)
        result["rejections_path"] = str(rejections_path())

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        verb = "DRY-RUN — would import" if args.dry_run else "imported"
        print(f"{verb} from provider '{source_provider}'")
        r = result["rejections"]
        axis_str = ", ".join(f"{k}={v}" for k, v in sorted(r["by_axis"].items())) if r["by_axis"] else "—"
        print(
            f"  {r['new']} new ({axis_str}), "
            f"{r['duplicates']} duplicates, "
            f"{r['skipped_malformed']} skipped"
        )
        if not args.dry_run and new_signals:
            print(f"  → {result['rejections_path']}")
            print(
                "  next: `trinity-local eval-build` to package these into "
                "an eval set, then `trinity-local eval-run` to score a model"
            )
    return 0
