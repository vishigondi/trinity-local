---
class: live
---

# Parasitism Audit — entangled dead/live code patterns

> Written 2026-05-27 after the seed/import-export refactor surfaced
> the question: "what else looks like this?" This is the audit. Each
> entry: pattern name, files involved, severity, recommended action.

## What "parasitism" means here

A live module depending on a retired/about-to-retire module. The
specific shapes that bite Trinity:

1. **Import parasitism** — module B imports a helper from module A,
   but A's CLI surface is retired. Cutting A breaks B. The seed → 
   import-export case from 2026-05-27 was this exactly.
2. **Misleading name** — module N does live work but the name says
   it was retired (`doctor.py` survives but `doctor` verb retired).
3. **Duplicated helpers** — two or more files have copies of the
   same function, sometimes with subtle drift between them.

## Findings (post-seed-cut, 2026-05-27)

### HIGH — `doctor.py` is the next misleading-name target

**Pattern:** misleading name
**Files:** `src/trinity_local/doctor.py` (881 LOC), `src/trinity_local/commands/status.py`
**What's happening:** the `doctor` CLI verb retired pre-launch (collapsed
into `status`), but `doctor.py` survives as the engine. `status.py`
imports `run_doctor`, `format_one_line`, `_check_trinity_home`,
`_check_provider`, `_check_mcp_available`, `_check_feedback_consistency`
etc. from it. The module does real work — provider-adapter checks,
MCP availability checks, feedback-consistency checks — but a reader
seeing `doctor.py` reasonably expects retired code.

**Recommendation:** rename `doctor.py` → `health_checks.py` (or
`status_checks.py`). Move `tests/test_doctor.py` → `tests/test_health_checks.py`.
Move `tests/test_doctor_browser_capture.py` → `tests/test_health_checks_browser_capture.py`.
Update the 4 import sites in `commands/status.py` and the test files.
Blast radius: 5 files, mechanical rename.

### MEDIUM — `me_card.py` is an orphan in src/

**Pattern:** dead module only referenced by tests + its own CLI
**Files:** `src/trinity_local/me_card.py` + `src/trinity_local/commands/me_card.py`
**What's happening:** `me_card.py` is imported only by `commands/me_card.py`
(the CLI handler) and its own tests. No other src/ module touches it.
The launchpad template references the verb via a button → extension
dispatch, NOT via direct Python import. Per CUT-CANDIDATES.md Phase 4
this is the share-card surface trim — still requires JS template
surgery for the "Render me-card" button.

**Recommendation:** cut per CUT-CANDIDATES.md Phase 4. Deferred until
the launchpad button + extension allowlist are pruned together.

### LOW — `_tokenize` triplicated, intentionally divergent

**Pattern:** duplicated helper, semantic drift on purpose
**Files:**
  - `src/trinity_local/vocabulary.py` — applies stopwords
  - `src/trinity_local/moves/gate.py` — no stopwords, T1 lexical compare
  - `src/trinity_local/embeddings/backend_tfidf.py` — simple regex

**What's happening:** each one tokenizes for a different purpose. The
shared name is misleading but the divergence is intentional. Centralizing
would force false coupling.

**Recommendation:** rename each to its purpose: `_tokenize_with_stopwords`,
`_tokenize_for_jaccard`, `_tokenize_for_tfidf`. No coupling, less
confusion. Cosmetic; defer.

### LOW — `_cosine` duplicated (5 lines each, tolerable)

**Pattern:** duplicated tiny helper
**Files:**
  - `src/trinity_local/cross_provider_pairs.py`
  - `src/trinity_local/moves/gate.py`

**What's happening:** identical 5-line cosine-similarity functions.
Could live in a shared `math_utils.py`. The duplication isn't
expensive but is a small flag.

**Recommendation:** defer until a third caller appears.

## False positives caught by the audit

These looked suspicious in the regex pass but resolved cleanly when
investigated:

- **`ranker/fallback.py`** — `ranker/__init__.py` re-exports it; not orphan.
- **`me/depth.py`** — actively used by `basins.py` + lens pipeline.
- **Most `back-compat` markers** — they're explicit retirement-context
  notes (renamed file/path), not parasitism.

## Audit method (for future passes)

```bash
# 1. Find files marked as "shim / inert / back-compat" but not in retired_names.py
grep -rn "inert shim\|back-compat\|deprecated\|TODO retir" src/trinity_local/ | grep -v retired_names

# 2. Find orphan modules (0 internal callers — excluding command modules
#    which are imported via importlib by main.py)
.venv/bin/python -c "
import ast, pathlib
from collections import defaultdict
src = pathlib.Path('src/trinity_local')
all_mods = {p.stem for p in src.rglob('*.py') if p.stem != '__init__'}
callers = defaultdict(set)
for py in src.rglob('*.py'):
    if py.stem == '__init__': continue
    for node in ast.walk(ast.parse(py.read_text())):
        if isinstance(node, ast.ImportFrom):
            short = (node.module or '').split('.')[-1]
            if short in all_mods and short != py.stem:
                callers[short].add(py.stem)
orphans = sorted(m for m, c in callers.items() if not c)
print('\n'.join(orphans))
"

# 3. Find duplicate function names
.venv/bin/python -c "
import re, pathlib
from collections import defaultdict
funcs = defaultdict(list)
for py in pathlib.Path('src/trinity_local').rglob('*.py'):
    for m in re.finditer(r'^def (_?[a-z_][a-z0-9_]*)\(', py.read_text(), re.MULTILINE):
        funcs[m.group(1)].append(str(py))
for n, locs in sorted(funcs.items()):
    if len(locs) > 1: print(f'{n}: {locs}')
"
```

## Net status (2026-05-27)

- **Cut:** seed-from-taste-terminal + 2 helper functions consolidated
  into `ingest_helpers.py`. Hot path got 1.85s faster.
- **Identified next:** rename `doctor.py` → `health_checks.py` (881 LOC,
  mechanical rename, HIGH-confidence).
- **Deferred:** me-card surface trim (Phase 4 of CUT-CANDIDATES),
  _tokenize per-purpose rename (cosmetic).
- **Net retirement registry size:** 95 entries (was 87 pre-cut-arc).
