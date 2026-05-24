"""Handler for `trinity-local decision-log` — capture a strategic
decision at decision-time, with the counterfactual reasoning attached.

The headline insight (ratified by post-launch lens-build plan iter 1,
2026-05-23): retroactive extraction of "would have flipped if X" from
transcripts is weak — rationalization sets in fast between the moment
of decision and the moment of writing about it. The high-quality
version of the counterfactual signal is captured AT THE DECISION,
not in the transcript.

Pattern: capture the highest-quality signal where it lives, not where
it's cheapest to extract.

Wire-up:
  - User invokes interactively when making a real strategic call:
        trinity-local decision-log
  - JSONL appended to ~/.trinity/me/decision_log.jsonl
  - Next `lens-build` reads decision_log.jsonl and prepends entries
    to Stage 2's decision corpus with weight=2.0 (pair-miner treats
    them as load-bearing over transcript-derived 1x decisions).

Non-interactive mode (--json) accepts a JSON object on stdin so
scripted callers (the launchpad, future MCP exposure) can log without
the interactive prompts.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from ..me.decisions import VALID_HORIZONS, VALID_VALENCES, decision_log_path


def register(subparsers):
    sp = subparsers.add_parser(
        "decision-log",
        help="Log a strategic decision with its counterfactual at decision-time (vs. retroactive extraction from transcripts)",
    )
    sp.add_argument(
        "--decision",
        help="Decision (one-line summary). If omitted, prompt interactively.",
    )
    sp.add_argument(
        "--privileged",
        help="Pole A — what got privileged.",
    )
    sp.add_argument(
        "--sacrificed",
        help="Pole B — what got sacrificed.",
    )
    sp.add_argument(
        "--valence",
        choices=sorted(VALID_VALENCES),
        help="Decision valence (satisfaction/regret/unresolved/correction/cost).",
    )
    sp.add_argument(
        "--would-flip-if",
        dest="would_flip_if",
        help="The counterfactual — what evidence would have flipped this decision.",
    )
    sp.add_argument(
        "--horizon",
        choices=sorted(VALID_HORIZONS),
        help="Time-horizon scope (tactical/strategic/philosophical). Default: strategic.",
    )
    sp.add_argument(
        "--basin",
        help="Basin id hint (optional).",
    )
    sp.add_argument(
        # Was `--json` originally — collided with every other Trinity
        # CLI's `--json` "output JSON" convention (status, eval-show,
        # memory-compare, me-card, etc.). Renamed to `--from-json` so
        # the name describes the actual direction (stdin INTO Trinity).
        "--from-json", dest="from_json", action="store_true",
        help="Read a single JSON object from stdin instead of prompting. Bypasses interactive flow.",
    )
    sp.set_defaults(handler=handle_decision_log)


def handle_decision_log(args):
    if args.from_json:
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(f"✗ stdin is not valid JSON: {exc}", file=sys.stderr)
            raise SystemExit(2)
        if not isinstance(payload, dict):
            print("✗ stdin JSON must be an object", file=sys.stderr)
            raise SystemExit(2)
        record = _build_record_from_dict(payload)
    else:
        record = _build_record_interactive(args)

    if record is None:
        print("✗ aborted", file=sys.stderr)
        raise SystemExit(1)

    path = decision_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    print(f"✓ logged decision to {path}")
    print(f"  privileged: {record['privileged']}")
    print(f"  sacrificed: {record['sacrificed']}")
    if record.get("would_flip_if"):
        print(f"  would flip if: {record['would_flip_if']}")
    print(
        f"  horizon: {record.get('horizon', 'strategic')} · "
        f"valence: {record['valence']} · weight: {record.get('weight', 2.0)}"
    )
    print("→ next `trinity-local lens-build` will weight this 2x in Stage 2.")


def _build_record_interactive(args) -> dict | None:
    def prompt(label: str, default: str = "", choices: list[str] | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        choice_hint = f" ({'/'.join(choices)})" if choices else ""
        while True:
            try:
                raw = input(f"  {label}{choice_hint}{suffix}: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return ""
            value = raw or default
            if choices and value and value not in choices:
                print(f"    must be one of: {', '.join(choices)}")
                continue
            return value

    print("trinity-local decision-log — capture a strategic call at decision-time")
    print("(Press Ctrl-C to abort. Empty answers use the default in brackets.)")
    print()

    decision = args.decision or prompt("Decision (one-line summary)")
    if not decision:
        return None
    privileged = args.privileged or prompt("Privileged (pole A)")
    sacrificed = args.sacrificed or prompt("Sacrificed (pole B)")
    if not privileged or not sacrificed:
        print("✗ both poles required", file=sys.stderr)
        return None
    valence = args.valence or prompt(
        "Valence",
        default="satisfaction",
        choices=sorted(VALID_VALENCES),
    )
    would_flip_if = args.would_flip_if or prompt(
        "Would have flipped if (leave blank if no clear counterfactual)"
    )
    horizon = args.horizon or prompt(
        "Horizon",
        default="strategic",
        choices=sorted(VALID_HORIZONS),
    )
    basin = args.basin or prompt("Basin hint (optional)")

    return _normalize_record(
        decision=decision,
        privileged=privileged,
        sacrificed=sacrificed,
        valence=valence,
        would_flip_if=would_flip_if,
        horizon=horizon,
        basin=basin,
    )


def _build_record_from_dict(payload: dict) -> dict:
    return _normalize_record(
        decision=str(payload.get("decision") or payload.get("verbatim") or "").strip(),
        privileged=str(payload.get("privileged") or "").strip(),
        sacrificed=str(payload.get("sacrificed") or "").strip(),
        valence=str(payload.get("valence") or "satisfaction").strip(),
        would_flip_if=str(payload.get("would_flip_if") or "").strip(),
        horizon=str(payload.get("horizon") or "strategic").strip(),
        basin=str(payload.get("basin") or "").strip(),
    )


def _normalize_record(
    *,
    decision: str,
    privileged: str,
    sacrificed: str,
    valence: str,
    would_flip_if: str,
    horizon: str,
    basin: str,
) -> dict:
    if valence not in VALID_VALENCES:
        valence = "satisfaction"
    if horizon not in VALID_HORIZONS:
        horizon = "strategic"

    record: dict[str, object] = {
        "privileged": privileged,
        "sacrificed": sacrificed,
        "valence": valence,
        # `verbatim` is the user's own one-line summary of the decision;
        # mirrors the field Stage 2 chairman fills from transcript excerpts.
        "verbatim": decision[:200],
        "source": "user_logged",
        "logged_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "weight": 2.0,
        "horizon": horizon,
    }
    if would_flip_if:
        record["would_flip_if"] = would_flip_if
    if basin:
        record["basin"] = basin
    return record
