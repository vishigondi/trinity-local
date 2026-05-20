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

## Preview locally

```
cd keepwhatworks && python3 -m http.server 8090
# open http://localhost:8090/
```

## Deploy

GitHub Pages is not yet enabled on the repo. To publish:
1. Repo Settings → Pages → Source = `Deploy from a branch`
2. Branch = `main`, folder = `/keepwhatworks` (or copy to `/docs`)
3. Custom domain = `keepwhatworks.com`
4. Verify the CNAME / DNS at the registrar

## Design system

Colors and font stack are pulled from `src/trinity_local/design_system.py`'s
`COLORS` dict so the marketing site stays in sync with the product UI.
