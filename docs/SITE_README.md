---
class: live
---

# keepwhatworks.com — static site

Marketing site for the products + essays that come out of this repo.
Trinity Local is the first product featured.

## Layout

- `index.html` — landing (hero + featured product + essay list)
- `style.css` — shared stylesheet, palette + typography matched to
  `src/trinity_local/design_system.py` so the site visually descends
  from the launchpad
- `articles/` — long-form essays. Each article carries a Trinity
  callout connecting the essay's main idea to the product
- `articles/raw/` — pre-formatting text captures (sources)
- `.nojekyll` — disables Jekyll so the 35 internal `.md` specs in
  this directory aren't auto-rendered as public-domain pages
- `CNAME` — pins `keepwhatworks.com` as the GitHub Pages custom domain

## Preview locally

```
cd docs && python3 -m http.server 8090
# open http://localhost:8090/
```

## Deploy

The site is deployed via GitHub Pages from `docs/` on the `main` branch.

1. Repo Settings → Pages → Source = `Deploy from a branch`
2. Branch = `main`, folder = `/docs`
3. Save. The `CNAME` file in this folder pins `keepwhatworks.com`.
4. Verify the custom domain at the registrar:
   - Apex (`keepwhatworks.com`): `A` records to GitHub Pages IPs
     (185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153)
   - `www`: `CNAME` to `vishigondi.github.io`

Every push to `main` that touches files under `docs/` auto-deploys.

## Design system

Colors and font stack are pulled from `src/trinity_local/design_system.py`'s
`COLORS` dict so the marketing site stays in sync with the product UI.

## Internal docs co-resident under docs/

Trinity Local's internal specs (`spec-v1.md`, `scale-plan.md`,
`launch-package.md`, etc.) also live under `docs/`. With `.nojekyll`
they don't render as public pages. They're still reachable as raw text
at e.g. `keepwhatworks.com/spec-v1.md` — fine, since the repo is
public — but no navigation surfaces them.
