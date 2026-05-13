"""Static HTML viewer for the five plural core memories + core.md.

Writes a single page at ~/.trinity/portal_pages/memory.html that loads
the requested memory file by query param (?file=lens.md, picks.json...).
JSON is pretty-printed; .md is shown raw. No markdown rendering for now —
chairman context is the source of truth, this is for human inspection.

Linked from the launchpad. Generated alongside the launchpad on
`portal-html` and on every refresh.
"""
from __future__ import annotations

from pathlib import Path

from .state_paths import portal_pages_dir


# Allowlist matches what's in state_paths. The viewer JS validates the
# ?file= param against this list before fetching — even though we're
# local-only, that keeps the relative-URL surface bounded.
ALLOWED_FILES: list[dict[str, str]] = [
    {"name": "lens.md", "rel": "../memories/lens.md", "brain": "value memory",
     "tagline": "Tensions you'd reject vs accept. Written by lens-build."},
    {"name": "picks.json", "rel": "../memories/picks.json", "brain": "procedural memory",
     "tagline": "Model picks per topic with reasoning. Written by consolidate."},
    {"name": "routing.json", "rel": "../memories/routing.json", "brain": "empirical memory",
     "tagline": "Per-category provider track record. Computed from council outcomes."},
    {"name": "topics.json", "rel": "../memories/topics.json", "brain": "semantic memory",
     "tagline": "K-means clusters of subjects you ask about. Written by lens-build Stage 1."},
    {"name": "vocabulary.md", "rel": "../memories/vocabulary.md", "brain": "language memory",
     "tagline": "Phrases you keep using + your overloaded terms. Written by dream Phase 2.5."},
    {"name": "core.md", "rel": "../core.md", "brain": "identity",
     "tagline": "One-paragraph distillation. Chairman reads this FIRST on every council."},
]


def _render_nav_links() -> str:
    """Server-rendered nav. Server-controlled values, escaped via html.escape."""
    import html as _html

    parts = []
    for f in ALLOWED_FILES:
        parts.append(
            '<a class="memory-nav-link" '
            f'href="memory.html?file={_html.escape(f["name"])}" '
            f'data-file="{_html.escape(f["name"])}">'
            f'<span class="memory-name">{_html.escape(f["name"])}</span>'
            f'<span class="memory-brain">{_html.escape(f["brain"])}</span>'
            '</a>'
        )
    return "\n".join(parts)


def render_memory_viewer_html() -> str:
    """Return the viewer HTML — static page, JS handles the fetch."""
    import json as _json

    files_json = _json.dumps(ALLOWED_FILES, ensure_ascii=True)
    nav_links = _render_nav_links()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trinity · Memory viewer</title>
  <style>
    :root {{
      --bg: #fafaf7;
      --fg: #222;
      --meta: #666;
      --accent: #6366f1;
      --border: #e5e5e0;
      --code-bg: #f4f4ee;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--fg);
      line-height: 1.5;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px 32px;
      border-bottom: 1px solid var(--border);
      background: white;
    }}
    .topbar a.back {{
      color: var(--fg);
      text-decoration: none;
      opacity: 0.7;
      padding: 6px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 14px;
    }}
    .topbar a.back:hover {{ opacity: 1; }}
    .topbar h1 {{ font-size: 16px; margin: 0; font-weight: 600; }}
    .layout {{
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 0;
      min-height: calc(100vh - 57px);
    }}
    .nav {{
      border-right: 1px solid var(--border);
      padding: 24px 16px;
      background: white;
    }}
    .nav-eyebrow {{
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--meta);
      margin-bottom: 12px;
    }}
    .memory-nav-link {{
      display: block;
      padding: 10px 12px;
      margin-bottom: 4px;
      border-radius: 6px;
      text-decoration: none;
      color: var(--fg);
      transition: background 0.1s;
    }}
    .memory-nav-link:hover {{ background: var(--code-bg); }}
    .memory-nav-link.active {{ background: rgba(99, 102, 241, 0.08); }}
    .memory-name {{
      display: block;
      font-family: ui-monospace, "SF Mono", Monaco, monospace;
      font-size: 13px;
      color: var(--accent);
      font-weight: 500;
    }}
    .memory-brain {{
      display: block;
      font-size: 11px;
      color: var(--meta);
      margin-top: 2px;
    }}
    .content {{
      padding: 32px;
      max-width: 880px;
    }}
    .content-header {{
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}
    .content-header h2 {{
      font-family: ui-monospace, "SF Mono", Monaco, monospace;
      font-size: 18px;
      margin: 0 0 6px;
      color: var(--accent);
    }}
    .content-header .meta {{
      font-size: 13px;
      color: var(--meta);
      margin: 0;
    }}
    pre.body {{
      font-family: ui-monospace, "SF Mono", Monaco, monospace;
      font-size: 13px;
      background: var(--code-bg);
      padding: 20px;
      border-radius: 6px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
      margin: 0;
    }}
    .empty, .error {{
      padding: 40px;
      text-align: center;
      color: var(--meta);
    }}
    .error {{ color: #b91c1c; }}
    .empty code, .error code {{
      background: var(--code-bg);
      padding: 2px 6px;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <a class="back" href="../portal_pages/launchpad.html">← Launchpad</a>
    <h1>Your memories</h1>
  </header>
  <div class="layout">
    <nav class="nav">
      <div class="nav-eyebrow">Five plural + one core</div>
      {nav_links}
    </nav>
    <main class="content" id="content">
      <div class="empty">Loading…</div>
    </main>
  </div>

  <script>
    const FILES = {files_json};
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("file") || FILES[0].name;
    const file = FILES.find(f => f.name === requested);
    const content = document.getElementById("content");

    // Highlight active link
    document.querySelectorAll(".memory-nav-link").forEach(a => {{
      if (a.dataset.file === requested) a.classList.add("active");
    }});

    // DOM helpers — building with createElement + textContent avoids any
    // innerHTML write path so a future change to FILES (or a corrupted
    // file body) can never inject HTML, even though the source is local.
    function clearContent() {{ while (content.firstChild) content.removeChild(content.firstChild); }}
    function el(tag, cls, text) {{
      const e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text !== undefined) e.textContent = text;
      return e;
    }}
    function renderHeader(file) {{
      const wrap = el("div", "content-header");
      wrap.appendChild(el("h2", null, file.name));
      wrap.appendChild(el("p", "meta", file.brain + " · " + file.tagline));
      return wrap;
    }}
    function renderEmpty(file) {{
      const wrap = el("div", "empty");
      wrap.appendChild(document.createTextNode("Not built yet. Run "));
      wrap.appendChild(el("code", null, "trinity-local " + suggestionFor(file.name)));
      wrap.appendChild(document.createTextNode(" to generate it."));
      return wrap;
    }}
    function renderError(file, message) {{
      const wrap = el("div", "error");
      wrap.appendChild(document.createTextNode("Could not load "));
      wrap.appendChild(el("code", null, file.rel));
      wrap.appendChild(document.createTextNode(" (" + message + "). "));
      wrap.appendChild(document.createTextNode(
        "If you opened this page via file:// the browser blocks local fetches — start the server with "));
      wrap.appendChild(el("code", null, "trinity-local serve"));
      wrap.appendChild(document.createTextNode(" and open via "));
      wrap.appendChild(el("code", null, "http://localhost:8765/portal_pages/memory.html"));
      wrap.appendChild(document.createTextNode("."));
      return wrap;
    }}

    if (!file) {{
      clearContent();
      const errWrap = el("div", "error");
      errWrap.appendChild(document.createTextNode("Unknown memory: "));
      errWrap.appendChild(el("code", null, requested));
      errWrap.appendChild(document.createTextNode(". Pick one from the nav."));
      content.appendChild(errWrap);
    }} else {{
      fetch(file.rel)
        .then(r => {{
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.text();
        }})
        .then(text => {{
          clearContent();
          if (!text.trim()) {{
            content.appendChild(renderHeader(file));
            content.appendChild(renderEmpty(file));
            return;
          }}
          let body = text;
          // Pretty-print JSON so the raw file's compactness doesn't tank readability.
          if (file.name.endsWith(".json")) {{
            try {{ body = JSON.stringify(JSON.parse(text), null, 2); }}
            catch (_) {{ /* malformed JSON — show raw */ }}
          }}
          content.appendChild(renderHeader(file));
          content.appendChild(el("pre", "body", body));
        }})
        .catch(err => {{
          clearContent();
          content.appendChild(renderHeader(file));
          content.appendChild(renderError(file, err.message));
        }});
    }}

    function suggestionFor(name) {{
      // What to run to populate each memory if it's missing.
      if (name === "lens.md" || name === "topics.json") return "lens-build";
      if (name === "picks.json") return "consolidate";
      if (name === "routing.json") return "dream";
      if (name === "vocabulary.md") return "vocabulary";
      if (name === "core.md") return "distill";
      return "dream";
    }}
  </script>
</body>
</html>
"""


def write_memory_viewer() -> Path:
    """Write the viewer HTML to ~/.trinity/portal_pages/memory.html."""
    path = portal_pages_dir() / "memory.html"
    path.write_text(render_memory_viewer_html(), encoding="utf-8")
    return path
