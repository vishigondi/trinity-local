"""Handler for `depth-show` — surface the top depth-ranked threads.

Inspector for the pure-geometry depth signal from src/trinity_local/me/depth.py
(corpus_distance × log(1+inter_turn) × log(1+LID)). Lets the user
look at which threads the geometry thinks are deep before the
chairman steers clustering in tick #53+. Same shape as
`merges-show` — compute-view-on-demand, no separate state file.

The user-facing test: do the top-ranked threads actually look like
deep thought, or is the geometric signal noisy on real data? If
real-corpus validation says yes, the depth-rank → chairman-in-the-
loop path is grounded; if it says no, we adjust the composite
before wasting chairman calls on noise.
"""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser(
        "depth-show",
        help="Show top-N threads by depth score (geometric: corpus distance × inter-turn × LID)",
    )
    sp.add_argument("--top", type=int, default=10, help="Number of threads to show (default 10)")
    sp.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    sp.set_defaults(handler=handle_depth_show)


def handle_depth_show(args):
    from ..me.depth import (
        rank_threads_by_depth,
        thread_corpus_distance,
        thread_inter_turn_distance,
        thread_lid,
    )
    from ..memory.store import iter_prompt_nodes

    nodes = list(iter_prompt_nodes(limit=None))
    if not nodes:
        if args.as_json:
            print(json.dumps({"total_threads": 0, "rows": []}, indent=2))
            return
        print("  No prompt nodes indexed yet — run `trinity-local seed-from-taste-terminal` first.")
        return

    # Compute all three components alongside the composite so the
    # output explains WHY a thread ranked high. The composite alone
    # is opaque; component breakdowns are debuggable.
    composite = dict(rank_threads_by_depth(nodes))
    corpus = thread_corpus_distance(nodes)
    inter = thread_inter_turn_distance(nodes)
    lid = thread_lid(nodes)

    ranked = sorted(composite.items(), key=lambda kv: kv[1], reverse=True)[: args.top]

    # Pick a representative prompt per thread — the FIRST turn of the
    # thread, which is usually the initiating question and the most
    # informative single line for inspection.
    thread_first_turn: dict[str, str] = {}
    thread_turn_count: dict[str, int] = {}
    for node in nodes:
        tid = getattr(node, "transcript_id", None) or node.id
        thread_turn_count[tid] = thread_turn_count.get(tid, 0) + 1
        ti = getattr(node, "turn_index", 0)
        existing = thread_first_turn.get(tid)
        if existing is None or ti == 0:
            text = (getattr(node, "text", "") or "").strip()
            if text and (existing is None or ti == 0):
                thread_first_turn[tid] = text

    rows = []
    for tid, score in ranked:
        first = thread_first_turn.get(tid, "")
        if len(first) > 140:
            first = first[:140].rstrip() + "…"
        rows.append({
            "transcript_id": tid,
            "depth_score": round(score, 4),
            "corpus_distance": round(corpus.get(tid, 0.0), 4),
            "inter_turn_distance": round(inter.get(tid, 0.0), 4),
            "lid": round(lid.get(tid, 0.0), 3),
            "turn_count": thread_turn_count.get(tid, 0),
            "first_turn": first,
        })

    if args.as_json:
        print(json.dumps({
            "total_threads": len(composite),
            "shown": len(rows),
            "rows": rows,
        }, indent=2))
        return

    print(f"  Depth-ranked threads ({len(rows)} of {len(composite)})")
    print(f"  {'score':>8s}  {'corpus':>9s}  {'inter':>6s}  {'LID':>5s}  {'turns':>5s}  preview")
    print(f"  {'-'*8}  {'-'*9}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*60}")
    for row in rows:
        preview = row["first_turn"] or "(no first turn text)"
        if len(preview) > 60:
            preview = preview[:60] + "…"
        # 6 decimal places on corpus_distance because unit-normalized
        # embeddings on a sphere produce small absolute distances even
        # when the rank order is meaningful; 4 places rounded to 0.0000.
        print(
            f"  {row['depth_score']:>8.4f}  "
            f"{row['corpus_distance']:>9.6f}  "
            f"{row['inter_turn_distance']:>6.4f}  "
            f"{row['lid']:>5.2f}  "
            f"{row['turn_count']:>5d}  "
            f"{preview}"
        )
    print()
    print("  score = 1.0*corpus_distance + 0.5*log(1+inter_turn) + 0.5*tanh(LID/10)")
    print("  Higher = thread sits further from corpus mean, moved through embedding space, sampled more axes.")
    print("  (additive composition so single-turn outliers still rank — fixed tick #54)")
