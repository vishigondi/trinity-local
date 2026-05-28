"""Stage 0 — turn-pair gap extraction (the spec's load-bearing piece).

Council `council_6892781d06ac3fa8` ratified Stage 0 as the highest-leverage
import from taste-terminal because turn-pair gaps capture implicit
behavioral preference that user-turn-only extraction misses entirely.

Council `council_e7560934cb1f1d72` ratified Option A (one batch chairman
call) over per-pair (B) and two-pass triage (C). The required mitigation
is **deterministic post-validators** that drop chairman-emitted labels
when they fail simple structural checks. Without those validators, A is
just chairman skimming with nice JSON — net negative.

Four implicit rejection signal types — adapted from the external
taste-terminal spec, ratified into Trinity's pipeline by
`council_6892781d06ac3fa8` (Stage 0 as the highest-leverage import)
and `council_e7560934cb1f1d72` (Option A with deterministic
post-validators):

- REFRAME: human accepted facts, rejected frame; substituted frame holds 2+ turns
- COMPRESSION: model gave N words, human responded with ≤N/10 — what survived is wanted
- REDIRECT: multi-part answer, human follows exactly one thread, ignores the rest
- SHARPENING: human repeats model's conclusion with harder/sharper language

Output: `~/.trinity/me/rejections.jsonl`. Stage 2 reads it as additional
high-signal source material alongside regular sampled turns.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from ..memory.store import iter_prompt_nodes
from .basins import Basin, basin_for_prompt, me_dir


VALID_SIGNAL_TYPES = {"REFRAME", "COMPRESSION", "REDIRECT", "SHARPENING"}

# Stop words that crowd out distinctive overlap when checking SHARPENING.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "is", "are", "was", "were",
    "be", "been", "being", "of", "to", "in", "on", "at", "for", "with",
    "by", "from", "as", "this", "that", "these", "those", "it", "its",
    "do", "does", "did", "have", "has", "had", "will", "would", "should",
    "could", "can", "may", "might", "must", "not", "no", "yes", "so",
    "more", "less", "than", "then", "there", "what", "when", "where",
    "who", "how", "why", "all", "any", "some", "into", "onto", "off",
}


@dataclass
class RejectionSignal:
    """One classified turn-pair gap.

    Field defaults align with `schemas/rejection_signal.schema.json`:
    only `id`, `type`, `model_quote`, `user_substitute` are required
    by the schema; the rest are optional. The dataclass mirrors that
    contract so an external schema-conformant producer (e.g. a future
    importer that parses minimal records) can construct one without
    supplying every field. `parse_rejections` already passes all
    fields, so live behavior unchanged. Sweep iter #108 caught the
    dataclass-vs-schema asymmetry.
    """
    id: str
    type: str  # REFRAME | COMPRESSION | REDIRECT | SHARPENING
    model_quote: str
    user_substitute: str
    why_signal: str = ""
    prompt_id: str | None = None
    basin: str | None = None
    next_user_turn: str = ""  # used for REFRAME persistence check; empty if unavailable

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "model_quote": self.model_quote,
            "user_substitute": self.user_substitute,
            "why_signal": self.why_signal,
            "prompt_id": self.prompt_id,
            "basin": self.basin,
            "next_user_turn": self.next_user_turn,
        }


def rejections_path() -> Path:
    return me_dir() / "rejections.jsonl"


def load_rejections() -> list[RejectionSignal]:
    """Read rejections.jsonl back into RejectionSignal objects — symmetric
    to save_rejections. Tolerant of extra keys from provider-imported
    records (eval-import adds source_provider/confidence): only the
    dataclass fields are consumed. Skips malformed or under-specified
    lines rather than failing the whole load."""
    path = rejections_path()
    if not path.exists():
        return []
    known = {f.name for f in fields(RejectionSignal)}
    required = ("id", "type", "model_quote", "user_substitute")
    out: list[RejectionSignal] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or not all(k in d for k in required):
            continue
        out.append(RejectionSignal(**{k: v for k, v in d.items() if k in known}))
    return out


def iter_turn_pairs(limit: int | None = None):
    """Yield (assistant_text, user_turn, prompt_id, next_user_text) tuples.

    `next_user_text` is the user turn AFTER the current one — used for
    REFRAME persistence validation. Empty string if unavailable.
    """
    # Uncapped: Stage 0 turn-pair extraction needs the full corpus, not
    # just the 5000 most-recent (which contain almost no
    # preceding_assistant_text since recent ingest skips that path).
    nodes = list(iter_prompt_nodes(limit=None))
    yielded = 0
    for i, node in enumerate(nodes):
        user = (node.text or "").strip()
        if not user:
            continue
        # Per-transcript fallback: claude_code transcripts have ~10%
        # preceding_assistant coverage but 73% following coverage — the
        # ingest path populates `following_assistant_text` on each node
        # but skipped `preceding_assistant_text` on the next-turn node.
        # When the current node lacks preceding, look back at the prior
        # node in the same transcript and use its `following_assistant_text`.
        # Lifts coverage from 37% → ~80% across providers.
        assistant = (node.preceding_assistant_text or "").strip()
        if not assistant and i > 0:
            prev = nodes[i - 1]
            if getattr(prev, "transcript_id", None) == getattr(node, "transcript_id", None):
                assistant = (prev.following_assistant_text or "").strip()
        if not assistant:
            continue
        # Best-effort next-user-turn lookup. Same per-transcript shape.
        next_user = ""
        if i + 1 < len(nodes):
            cand = nodes[i + 1]
            if getattr(cand, "transcript_id", None) == getattr(node, "transcript_id", None):
                cand_pred = (cand.preceding_assistant_text or "").strip()
                following = (node.following_assistant_text or "").strip()
                if cand_pred == following or (following and not cand_pred):
                    next_user = (cand.text or "").strip()
        yield (assistant, user, node.id, next_user)
        yielded += 1
        if limit is not None and yielded >= limit:
            break


def render_extraction_prompt(pairs: list[dict], basins: list[Basin]) -> str:
    """Render the single-batch Stage 0 chairman prompt.

    `pairs` items: {prompt_id, assistant_text, user_text, basin}. Output
    is one rejection signal per JSON line — same shape as Stage 2.
    """
    basin_summary = "\n".join(
        f"  {b.id}: {', '.join(b.top_terms) or '(no terms)'} ({b.size})"
        for b in basins[:20]
    )
    chunks = []
    for i, p in enumerate(pairs):
        prompt_id = p.get("prompt_id") or f"pair_{i}"
        basin = p.get("basin") or "?"
        a = (p.get("assistant_text") or "").strip().replace("\n", " ")
        u = (p.get("user_text") or "").strip().replace("\n", " ")
        if len(a) > 600:
            a = a[:600] + "…"
        if len(u) > 400:
            u = u[:400] + "…"
        chunks.append(
            f"[{prompt_id} · basin={basin}]\n"
            f"  MODEL: {a}\n"
            f"  USER: {u}"
        )
    pairs_block = "\n\n".join(chunks)

    return f"""You are mining the four implicit rejection signal types from
turn-pair gaps. Each pair below is a model response followed by the user's
next turn. Look at what the user did NEXT — that's the highest-signal
behavioral data we have, because it's choices made under no obligation.

THE FOUR SIGNAL TYPES

REFRAME: the user accepts the model's facts but pivots to a different
  angle without acknowledging the previous answer. The user's next turn
  introduces a substitute frame.

COMPRESSION: the model gave N words; the user replies with ≤N/10. What
  survived compression is what the user wanted; the rest was implicit
  rejection.

REDIRECT: the model gave a multi-part answer (numbered, bulleted, or
  multi-thread). The user follows exactly one thread and ignores the
  others. Ignored threads are rejections by omission.

SHARPENING: the user repeats the model's conclusion with harder language,
  higher precision, or stronger epistemic posture.
  Example: model says "creates advantages" → user says "structural
  inevitability". User accepted the conclusion, rejected the register.

EXTRACTION RULE: only emit a signal if you can name a concrete delta
between what the model said and what the user carried into the next turn.
If the user's turn is just a follow-up question that builds on the model's
answer, that's NOT a rejection signal — skip it.

For each pair where you find a signal, emit ONE JSON line in this schema:

{{"id": "r_001", "type": "REFRAME|COMPRESSION|REDIRECT|SHARPENING", "model_quote": "<≤25 word excerpt from MODEL>", "user_substitute": "<≤25 word excerpt from USER>", "why_signal": "<one short sentence on the delta>", "prompt_id": "<the [id] from the pair header>"}}

Hard caps:
- Skip pairs with no clear signal. Don't force categorization.
- At most 60 emitted signals total. Quality over quantity.
- Output format: ONE JSON object per line, NO commentary, NO markdown
  fences, NO blank lines.

Basins reference (id : top terms · size):
{basin_summary}

PAIRS:

{pairs_block}
"""


def parse_rejections(raw: str, basins: list[Basin]) -> list[RejectionSignal]:
    """Parse chairman output. Re-tags basin from prompt_id ground truth."""
    signals: list[RejectionSignal] = []
    next_auto_id = 1
    seen_ids: set[str] = set()

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        sig_type = (obj.get("type") or "").strip().upper()
        if sig_type not in VALID_SIGNAL_TYPES:
            continue
        model_quote = (obj.get("model_quote") or "").strip()
        user_substitute = (obj.get("user_substitute") or "").strip()
        if not model_quote or not user_substitute:
            continue
        prompt_id = (obj.get("prompt_id") or "").strip() or None
        basin_id = basin_for_prompt(basins, prompt_id) if prompt_id else None
        if basin_id is None:
            basin_id = (obj.get("basin") or "").strip() or None

        r_id = (obj.get("id") or "").strip()
        if not r_id or r_id in seen_ids:
            r_id = f"r_{next_auto_id:03d}"
            while r_id in seen_ids:
                next_auto_id += 1
                r_id = f"r_{next_auto_id:03d}"
        seen_ids.add(r_id)
        next_auto_id += 1

        signals.append(RejectionSignal(
            id=r_id,
            type=sig_type,
            model_quote=model_quote,
            user_substitute=user_substitute,
            why_signal=(obj.get("why_signal") or "").strip(),
            prompt_id=prompt_id,
            basin=basin_id,
        ))
    return signals


# ---- deterministic validators (the load-bearing piece per council_e7560934) ----


def _word_count(text: str) -> int:
    return len(text.split())


def _keyword_set(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-_]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _looks_multi_part(text: str) -> bool:
    """Heuristic: is the model's answer structured as multiple threads?

    Looks for any of: numbered list (1. / 1)), bullet markers (- *), or
    ≥3 sentences. Mirrors what the spec means by "multi-part answer".
    """
    if re.search(r"^\s*\d+[.)]\s+", text, flags=re.MULTILINE):
        return True
    if re.search(r"^\s*[-*•]\s+", text, flags=re.MULTILINE):
        return True
    sentence_count = len(re.findall(r"[.!?]\s+[A-Z]", text))
    return sentence_count >= 3


def validate_signals(
    signals: list[RejectionSignal],
    pair_index: dict[str, dict],
) -> tuple[list[RejectionSignal], list[dict]]:
    """Apply deterministic post-validators per signal type.

    Returns (kept, rejected) — rejected entries carry a `reason` field
    so we can audit chairman drift over time.
    """
    kept: list[RejectionSignal] = []
    rejected: list[dict] = []

    for sig in signals:
        pair = pair_index.get(sig.prompt_id or "") or {}
        assistant = pair.get("assistant_text") or ""
        user = pair.get("user_text") or ""
        next_user = pair.get("next_user_text") or ""

        ok, reason = _validate_one(sig, assistant, user, next_user)
        if ok:
            sig.next_user_turn = next_user
            kept.append(sig)
        else:
            rejected.append({"signal": sig.to_dict(), "reason": reason})
    return kept, rejected


def _validate_one(
    sig: RejectionSignal,
    assistant: str,
    user: str,
    next_user: str,
) -> tuple[bool, str]:
    """One signal → (kept, reason). Reason explains rejection when False."""
    t = sig.type
    if t == "COMPRESSION":
        # User text must be ≤10% of model text by word count.
        a_words = _word_count(assistant)
        u_words = _word_count(user)
        if a_words == 0:
            return False, "no model text to compare"
        if u_words * 10 > a_words:
            return False, f"user/model ratio {u_words}/{a_words} > 1/10"
        return True, ""
    if t == "REDIRECT":
        if not _looks_multi_part(assistant):
            return False, "model answer not structurally multi-part"
        return True, ""
    if t == "SHARPENING":
        # User must share ≥2 keywords with model — confirms they're
        # restating the same idea, not pivoting away.
        overlap = _keyword_set(assistant) & _keyword_set(user)
        if len(overlap) < 2:
            return False, f"keyword overlap {len(overlap)} < 2"
        return True, ""
    if t == "REFRAME":
        # Spec: substituted frame must hold ≥2 turns. Approximate by
        # checking that the next user turn shares more keywords with the
        # CURRENT user than with the original model frame.
        if not next_user:
            # No next-turn data — be lenient (don't drop), but flag.
            return True, ""
        u_keys = _keyword_set(user)
        next_keys = _keyword_set(next_user)
        a_keys = _keyword_set(assistant)
        if not u_keys:
            return False, "user turn has no keywords"
        sub_persistence = len(u_keys & next_keys)
        return_to_model = len(a_keys & next_keys)
        if return_to_model > sub_persistence:
            return False, f"frame did not persist (return_to_model={return_to_model} vs sub={sub_persistence})"
        return True, ""
    return False, f"unknown signal type {t}"


class DegenerateExtractionError(RuntimeError):
    """save_rejections was asked to overwrite a populated corpus with a
    cliff-drop result. Almost always a transient chairman-empty run
    (the Stage 0 call returned nothing parseable), NOT a real signal
    change. Raised instead of silently truncating — the live corpus is
    preserved and the would-be result is written to a `.degenerate`
    sidecar for inspection.

    Live incident 2026-05-28 (#194): a chairman blip made Stage 0
    extract 0 rejections; lens-build overwrote 49 rejections + a
    3-tension lens with empty results and reported ok:true. Recovery
    relied on a stale 3-day-old .bak that happened to exist. This guard
    removes the luck.
    """


# Clobber-guard thresholds. A new extraction must not wipe the corpus
# when it's a cliff-drop vs what's on disk: empty when ≥MIN_EXISTING
# rows exist, or below MIN_FRACTION of the existing count.
_CLOBBER_MIN_EXISTING = 5
_CLOBBER_MIN_FRACTION = 0.25


def save_rejections(
    signals: list[RejectionSignal], *, allow_shrink: bool = False
) -> Path:
    path = rejections_path()
    existing = 0
    if path.exists():
        try:
            existing = sum(
                1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            )
        except OSError:
            existing = 0
    floor = max(1, int(existing * _CLOBBER_MIN_FRACTION))
    if (
        not allow_shrink
        and existing >= _CLOBBER_MIN_EXISTING
        and len(signals) < floor
    ):
        # Preserve the live corpus; stash the would-be result for debugging.
        sidecar = path.parent / (path.name + ".degenerate")
        try:
            with sidecar.open("w", encoding="utf-8") as f:
                for sig in signals:
                    f.write(json.dumps(sig.to_dict()) + "\n")
        except OSError:
            pass
        raise DegenerateExtractionError(
            f"Refusing to overwrite {existing} rejections with "
            f"{len(signals)} (cliff-drop below {floor}). Almost certainly "
            f"a transient chairman-empty Stage 0 run, not a real shrink. "
            f"Live corpus preserved; degenerate result written to "
            f"{sidecar.name}. Re-run lens-build; pass allow_shrink=True "
            f"only if the corpus genuinely shrank."
        )
    with path.open("w") as f:
        for sig in signals:
            f.write(json.dumps(sig.to_dict()) + "\n")
    # Also fan out to the unified merges.jsonl corpus (tick #46). The
    # rejections.jsonl is the canonical store for lens-build's own
    # pipeline; the merge log is a side-channel that aggregates ALL
    # tacit-record acts (council winners + cortex overrides + these
    # in-thread overwrites) so v1.5+ direction-of-preference vectors
    # have one place to read from.
    #
    # Dedup on (signal_id) so re-runs of lens-build don't double-count
    # the same (prompt_id, type) pair — save_rejections truncates
    # rejections.jsonl but the merge log is append-only.
    try:
        from ..merges import record_merge, iter_merge_records
        seen_ids: set[str] = set()
        for row in iter_merge_records():
            if row.get("type") == "in_thread_overwrite":
                sid = row.get("signal_id")
                if isinstance(sid, str):
                    seen_ids.add(sid)
        for sig in signals:
            if sig.id in seen_ids:
                continue
            record_merge({
                "type": "in_thread_overwrite",
                "signal_type": sig.type,
                "signal_id": sig.id,
                "prompt_id": sig.prompt_id,
                "basin": sig.basin,
                "model_quote": sig.model_quote,
                "user_substitute": sig.user_substitute,
                "why_signal": sig.why_signal,
            })
    except Exception:
        # Side-channel: failure here can't break lens-build.
        pass
    return path


