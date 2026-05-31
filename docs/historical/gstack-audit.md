---
class: historical
---

# gstack pattern audit — which ratchets would have caught past fixes

Task #191. The user asked: "go back in history and see if there are
fixes we did that would have been prevented with these patterns."
This is the empirical ROI ledger for the gstack ratchet family —
each post-launch fix commit assessed against the guards we now have
(or could add). When a pattern accumulates ≥3 historical hits, it's
earned its place; promote it from "nice idea" to "ship now."

Method: walked `git log --since=2026-05-13` (post-launch) for
fix/cleanup/drift commits, categorized each against the guard that
would have caught it at PR time. One audit pass per session; this
is pass 1.

## ROI tally (pass 1)

| Pattern | Guard status | Historical hits | Verdict |
|---|---|---|---|
| **Canonical placeholder / doc-count drift** | SHIPPED pre-session (`test_doc_count_consistency`) | ≥6 | Validated — highest-frequency drift class |
| **Module/function orphans** | SHIPPED #188 (`find_orphans.py`) | ≥3 | Validated |
| **Stale retired-name references** | SHIPPED #189 (import + flag AST guards) | ≥4 | Validated; doc-side extension still open |
| **Output-shape / silent-empty** | NOT shipped (deferred from #190) | 2–3 | Approaching promotion threshold |
| **Embedding-backend-assumed-available** | partial (#185 TF-IDF skip) | 2 | Watch; one more hit → dedicated guard |

## Detailed findings

### Canonical placeholder / doc-count drift — ≥6 hits, validated

The single most frequent drift class post-launch. Every one of these
was a manual fix that the canonical-placeholder renderer now prevents:

- `5be2cb7` — py_file_count stale at 113, actually 119
- `a9743c2` — tool-count drift + duplicate paragraph
- `c2813eb` — claude.md count fix
- `3e83bab` — de-stale claude.md L13 status line
- `f72af48` — test_count 1652→1653 across 10 surfaces
- `17e0d81` — claude.md "21-command surface" stale → canonicalize

**Conclusion:** the canonical-placeholder system (Gap A, task #125)
is the highest-ROI ratchet Trinity has. Six manual fixes collapsed
into one auto-rendered source of truth. This session's work added
8 new canonical surfaces; the pattern keeps paying.

### Module/function orphans — ≥3 hits, validated #188

- `1b50b97` — orphan retired-CLI handler stubs (`commands/distill.py`
  + `bootstrap_pairs.py`) — exactly the module-orphan case
  `find_orphans.py` now catches at PR time.
- `91d9ac7` — orphan `canUseShortcut()` getter (function-level;
  vulture territory, but same family)
- `4e30ec1` — dead `watcher` subdir in a test fixture

**Conclusion:** #188's reachability finder would have flagged
`1b50b97` directly. The moves substrate (this session, -4,400 LOC)
is the same class at 50× the scale. Validated.

### Stale retired-name references — ≥4 hits, validated #189

- `69a959a` — CONTRIBUTING referenced retired `dispatch_runner`
- `dcbe8c9` — cross-platform-spec stale rating-UX refs ("escaped #134")
- `a7bc7c2` — browser-extension README: 4 stale claims
- `b6cb8e3` — `watcher_dir()` source-comment-vs-registry drift

**Conclusion:** #189's AST guards catch the *code* references
(`from trinity_local.<retired>`). The *doc* references (`dcbe8c9`,
`a7bc7c2`) need a doc-side term guard — that's the still-open leg of
#189's original scope. The "escaped #134" note in `dcbe8c9` is
telling: a retirement that leaked back into docs because nothing
guarded the doc surface. **One concrete follow-up: extend the
retired-name guard to scan active (`class: live`) docs for retired
module/CLI names.**

### Output-shape / silent-empty — 2–3 hits, approaching promotion

- `e605e74` — "memory-compare: fix two bugs that made Mode-1
  silently return 0/0 ... reported empty on real installs with
  populated lens + Auto-Dream state." **This is the canonical
  output-shape-smoke case** — a feature that runs, doesn't crash,
  and produces empty output when it shouldn't.
- The **moves substrate dormancy** (this session) — gate ran, zero
  promotions, substrate stayed empty. Same class.
- `8999c68` — extension_repair counted sentinel/orphan files as
  captures (wrong non-zero output; adjacent class).

**Conclusion:** 2 clean hits (e605e74 + moves) + 1 adjacent. The
output-shape smoke pattern (deferred from #190 because it needs
realistic fixtures) has demonstrated ROI. **Recommendation: promote
to a real task** — for each feature that produces records/files,
a smoke test asserting non-empty output on seeded realistic input.
memory-compare is retired now, but the lens-build pipeline + eval
harness are live and would benefit.

### Embedding-backend-assumed-available — 2 hits, watch

- `8cae846` — "ci: fix ... optimistic MLX probe" — the probe
  assumed MLX was loaded when it wasn't.
- This session's **#185 TF-IDF bug** — Stage 4 filter assumed real
  embeddings; collapsed under TF-IDF fallback.

**Conclusion:** two instances of "code assumed the MLX embedding
backend was active when it wasn't." Both were caught late (CI / a
forced-fallback test). One more hit and this earns a dedicated
guard: any code path that calls `embed()` AND makes a
threshold/quality decision on the result should branch on
`mlx_actually_loaded()`. For now, #185's fix is the localized
patch; watch for recurrence.

## Promotions out of this pass

1. **Doc-side retired-name guard** (extends #189): scan `class: live`
   docs for retired module/CLI names from `retired_names.RETIRED`.
   Would have caught `dcbe8c9` + `a7bc7c2`. ≥2 hits, low effort —
   worth a dedicated follow-up task.
2. **Output-shape smoke** (was deferred from #190): 2–3 hits earns
   it. Target the live producers (lens-build, eval harness).

## Next audit pass (pass 2)

Walk the pre-`v1.7.4` history (the iteration-council arc #63–#73,
the lens-pipeline build #79–#82). Larger, noisier — out of scope for
a loop tick. Focus there only if a pattern from pass 1 needs more
evidence to cross the promotion threshold.
