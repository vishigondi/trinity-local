---
class: live
---

# Repo-flip-public runbook

> Status: ready to execute. Run top-to-bottom on T-0 morning. Everything
> below has been prepared so the flip-public step is a sequence of
> already-debugged `gh` commands rather than fresh judgment calls under
> launch pressure.
>
> Prereq: `gh auth status` shows you logged in as `vishigondi`.

## 1. Final pre-flip smoke

```bash
# Working tree clean except expected ignored files
git status --short

# Tests pass locally
.venv/bin/python -m pytest -q

# No remaining pip-publish references (should be zero — the curl|sh
# sweep covers everything)
grep -rn "pip install trinity-local\|pipx install trinity-local" \
  --include="*.md" --exclude-dir=.venv | grep -v "no PyPI\|NOT publish"

# Bash syntax check on the installer
bash -n scripts/install.sh
```

## 2. Flip the repo public

```bash
gh repo edit vishigondi/trinity-local --visibility public --accept-visibility-change-consequences
```

After this, every link in `README.md`, `docs/launch.md`, and the
`scripts/install.sh` URL becomes a real public URL.

## 3. Set description + topics

```bash
gh repo edit vishigondi/trinity-local \
  --description "Your taste, ported. Cross-provider memory + councils + handoff inside Claude Code, Codex CLI, Gemini CLI, and Cursor. Local-first, rides on your existing subscriptions." \
  --add-topic mcp \
  --add-topic claude-code \
  --add-topic codex-cli \
  --add-topic gemini-cli \
  --add-topic antigravity-cli \
  --add-topic cursor \
  --add-topic local-first \
  --add-topic multi-provider \
  --add-topic llm \
  --add-topic council \
  --add-topic agent \
  --add-topic privacy \
  --add-topic benchmarks \
  --add-topic preference-learning \
  --homepage "https://keepwhatworks.com"
```

## 4. Upload the social card

GitHub's social-card slot accepts 1280×640 PNGs (≤1MB). Trinity renders
exactly this shape via `me-card.py`. Generate one from your own lens:

```bash
trinity-local me-card --open --out /tmp/trinity-social-card.png
```

Then upload via the **Settings → General → Social preview** page in the
GitHub UI — `gh` doesn't expose this endpoint. If `me-card` isn't ready
(no lens.md yet), use the existing example as a temporary stand-in:

```bash
open docs/me_card_example.png
# manual upload via the GitHub Settings UI
```

## 5. Pin starter issues

Create three pinned issues so the repo lands with first-class onboarding:

```bash
gh issue create -R vishigondi/trinity-local \
  --title "Start here: install Trinity in 60 seconds" \
  --label "good-first-issue,documentation" \
  --body "Run \`curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash\` then \`/trinity\` in Claude Code. If \`trinity-local status\` reports any failure, open an issue — that's the launch-feedback we most want."

gh issue create -R vishigondi/trinity-local \
  --title "Share your first council" \
  --label "feedback" \
  --body "Run \`trinity-local council-share --council <council_id>\` (privacy-safe by construction — no user prompts inlined) and paste the share link in this issue. We learn which question shapes are most useful — and you get a marketing-legible record of when Trinity helped."

# Then pin them via the UI (gh CLI doesn't support pin):
# https://github.com/vishigondi/trinity-local/issues
```

## 6. Enable GitHub Pages

Pages serves `/docs` from the `main` branch. Content lives at
`docs/index.html` (the keepwhatworks static site moved in on
2026-05-20); `docs/.nojekyll` disables Jekyll so the ~35 internal
`.md` specs in the same directory don't auto-render as public
pages. `docs/CNAME` pins the custom domain.

```bash
gh api repos/vishigondi/trinity-local/pages -X POST \
  -f "source[branch]=main" \
  -f "source[path]=/docs" \
  2>/dev/null || echo "Pages may need manual enable in Settings UI"
```

## 7. Verify the badges turn green

After the first push to `main` post-flip:

- `https://github.com/vishigondi/trinity-local/actions/workflows/test.yml` should show a passing run within ~2 minutes.
- The README's `tests` badge auto-updates once the action completes.

If the action fails on Ubuntu (most likely: a macOS-specific test that
needs a `skipif`), the failure is fast and the fix is small — don't let
it block the launch tweet. A red badge for an hour is worse than a
delayed launch.

## 8. Done — verify the user-facing URLs

```bash
# Install one-liner reachable
curl -fsSL -o /tmp/trinity-install.sh \
  https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh
bash -n /tmp/trinity-install.sh && echo "INSTALL.SH OK"

# Repo URL renders the README hero (curl + grep instead of opening browser)
curl -fsSL https://github.com/vishigondi/trinity-local | grep -q "Your taste, ported" \
  && echo "README HERO OK" || echo "README HERO MISSING"

# Pages landing reachable (post-2026-05-17 brand flip: site lives at
# the custom keepwhatworks.com domain; the github.io subpath may
# redirect but is no longer the canonical URL).
curl -fsSL https://keepwhatworks.com/ | grep -q "keepwhatworks" \
  && echo "PAGES OK" || echo "PAGES NOT YET LIVE (give it 2-5 minutes — DNS + GH Pages SSL provisioning)"
```

## Rollback (if the launch tweet goes sideways)

```bash
# Flip back to private without losing any commits or issues
gh repo edit vishigondi/trinity-local --visibility private --accept-visibility-change-consequences
```

The repo stays intact; only the audience changes. Issues, stars, and
forks persist if you re-flip-public later.
