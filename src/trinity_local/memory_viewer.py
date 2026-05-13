"""Static HTML viewer for the five plural core memories + core.md.

Writes a single page at ~/.trinity/portal_pages/memory.html that loads
the requested memory file by query param (?file=lens.md, picks.json...).
JSON is pretty-printed; .md is shown raw. No markdown rendering for now —
chairman context is the source of truth, this is for human inspection.

Memory contents are inlined into a `window.__TRINITY_MEMORIES__` global at
write time (same pattern as council thread manifests in live_council.html).
This makes the viewer work under file:// — no `fetch()`, no `trinity-local
serve` required — which matters because the launchpad opens via file://
from the macOS desktop shortcut, and the chips link straight here.

Linked from the launchpad. Generated alongside the launchpad on
`portal-html` and on every refresh.
"""
from __future__ import annotations

from pathlib import Path

from .state_paths import (
    core_path,
    lens_path,
    picks_path,
    portal_pages_dir,
    routing_path,
    topics_path,
    vocabulary_path,
)


# Allowlist matches what's in state_paths. Used by render time (to load
# file contents into the inlined JS payload) and by the client-side JS
# (to validate the ?file= param against a known set).
ALLOWED_FILES: list[dict[str, str]] = [
    {"name": "lens.md", "brain": "value memory",
     "tagline": "Tensions you'd reject vs accept. Written by lens-build."},
    {"name": "picks.json", "brain": "procedural memory",
     "tagline": "Model picks per topic with reasoning. Written by consolidate."},
    {"name": "routing.json", "brain": "empirical memory",
     "tagline": "Per-category provider track record. Computed from council outcomes."},
    {"name": "topics.json", "brain": "semantic memory",
     "tagline": "K-means clusters of subjects you ask about. Written by lens-build Stage 1."},
    {"name": "vocabulary.md", "brain": "language memory",
     "tagline": "Phrases you keep using + your overloaded terms. Written by dream Phase 2.5."},
    {"name": "core.md", "brain": "identity",
     "tagline": "One-paragraph distillation. Chairman reads this FIRST on every council."},
]


_FILE_PATH_RESOLVERS = {
    "lens.md": lens_path,
    "picks.json": picks_path,
    "routing.json": routing_path,
    "topics.json": topics_path,
    "vocabulary.md": vocabulary_path,
    "core.md": core_path,
}


def _read_memory_contents() -> dict[str, str | None]:
    """Read each memory file at render time. Returns name → contents, with
    None for missing files (the viewer renders an empty-state for those).

    Rendering is client-side: `marked` handles markdown, the inline JSON
    viewer (in the embedded JS) handles JSON. Keeps it DRY — same JS
    libs Trinity already pulls (petite-vue, Chart.js); no parallel
    server-side renderer to maintain.
    """
    contents: dict[str, str | None] = {}
    for name, resolver in _FILE_PATH_RESOLVERS.items():
        path = resolver()
        try:
            contents[name] = path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            contents[name] = None
    return contents


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
    """Return the viewer HTML with memory contents inlined.

    Reads each memory file at render time and emits its contents into
    `window.__TRINITY_MEMORIES__` so the page works under file:// (no
    fetch needed). Same pattern as live_council.html's thread manifests.
    """
    import json as _json

    files_json = _json.dumps(ALLOWED_FILES, ensure_ascii=True)
    memories_payload = _json.dumps(_read_memory_contents(), ensure_ascii=True)
    nav_links = _render_nav_links()
    # Bundled JS deps — same pattern as launchpad_template.py
    # (petite-vue + Chart.js from CDN). `marked` is the standard markdown
    # renderer; ~30KB gzipped. Kills the dual-renderer problem (we already
    # have markdown_utils server-side for council pages; client-side
    # marked() keeps the memory viewer DRY).
    marked_src = "https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"
    # wordcloud2.js (timdream) — standalone, ~31KB. Used by the topics.json
    # Reader view to render a basin cloud above the bar list.
    # d3 modules for the topics.json basin-relation graph. We pull only
    # the pieces we need rather than the full ~250KB d3 bundle:
    #   - d3-selection: DOM binding (.select, .selectAll, .data, .join)
    #   - d3-drag: pointer drag for moving nodes
    #   - d3-dispatch + d3-timer: event + animation loop (force needs these)
    #   - d3-quadtree: spatial index used by forceCollide + forceManyBody
    #   - d3-force: the simulation itself
    # Total ~80KB — still under the full d3 (~250KB).
    d3_select_src = "https://cdn.jsdelivr.net/npm/d3-selection@3.0.0/dist/d3-selection.min.js"
    d3_dispatch_src = "https://cdn.jsdelivr.net/npm/d3-dispatch@3.0.1/dist/d3-dispatch.min.js"
    d3_timer_src = "https://cdn.jsdelivr.net/npm/d3-timer@3.0.1/dist/d3-timer.min.js"
    d3_quadtree_src = "https://cdn.jsdelivr.net/npm/d3-quadtree@3.0.1/dist/d3-quadtree.min.js"
    d3_drag_src = "https://cdn.jsdelivr.net/npm/d3-drag@3.0.0/dist/d3-drag.min.js"
    d3_force_src = "https://cdn.jsdelivr.net/npm/d3-force@3.0.0/dist/d3-force.min.js"
    # d3-zoom — pan + scroll-wheel zoom on the topic graph. The viewer
    # advertises "scroll to zoom" in the hint chip; without this module
    # that was a lie.
    d3_zoom_src = "https://cdn.jsdelivr.net/npm/d3-zoom@3.0.0/dist/d3-zoom.min.js"
    # d3-interpolate is a transitive dep of d3-zoom (for the transform
    # interpolation during programmatic zoom). Tiny (~5KB).
    d3_interpolate_src = "https://cdn.jsdelivr.net/npm/d3-interpolate@3.0.1/dist/d3-interpolate.min.js"
    d3_color_src = "https://cdn.jsdelivr.net/npm/d3-color@3.1.0/dist/d3-color.min.js"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trinity · Memory viewer</title>
  <script src="{marked_src}"></script>
  <script src="{d3_select_src}"></script>
  <script src="{d3_dispatch_src}"></script>
  <script src="{d3_timer_src}"></script>
  <script src="{d3_quadtree_src}"></script>
  <script src="{d3_drag_src}"></script>
  <script src="{d3_force_src}"></script>
  <script src="{d3_color_src}"></script>
  <script src="{d3_interpolate_src}"></script>
  <script src="{d3_zoom_src}"></script>
  <style>
    /* Palette: matches DESIGN.md + design_system.py — warm paper bg,
       forest green primary action, warm brown accent for emphasis. */
    :root {{
      --bg: #f5efe3;
      --bg-wash: #ece4d6;
      --surface: #fbf8f2;
      --surface-muted: #f1eadf;
      --fg: #1f1a17;
      --meta: #86796d;
      --primary: #255847;       /* forest green */
      --primary-hover: #1d4638;
      --primary-text: #f7f3ea;
      --accent: #b57438;        /* warm brown */
      --border: #d7ccb9;
      --code-bg: #f1eadf;
      --success: #2d6a4f;
      --warning: #b26a1f;
      --danger: #a33c2f;
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
    .memory-nav-link.active {{ background: rgba(37, 88, 71, 0.10); }}
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
    /* Rendered markdown ─────────────────────────────────────────────── */
    .markdown-body {{ font-size: 14px; line-height: 1.65; }}
    .markdown-body h1 {{ font-size: 22px; margin: 28px 0 12px; }}
    .markdown-body h2 {{ font-size: 18px; margin: 24px 0 10px; }}
    .markdown-body h3 {{ font-size: 16px; margin: 20px 0 8px; }}
    .markdown-body p {{ margin: 10px 0; }}
    .markdown-body ul, .markdown-body ol {{ margin: 10px 0; padding-left: 24px; }}
    .markdown-body li {{ margin: 4px 0; }}
    .markdown-body code {{
      font-family: ui-monospace, "SF Mono", Monaco, monospace;
      font-size: 0.92em;
      background: var(--code-bg);
      padding: 2px 6px;
      border-radius: 4px;
    }}
    .markdown-body pre {{
      background: var(--code-bg);
      padding: 16px;
      border-radius: 6px;
      overflow-x: auto;
      font-size: 13px;
    }}
    .markdown-body pre code {{ background: none; padding: 0; }}
    .markdown-body blockquote {{
      border-left: 3px solid var(--accent);
      padding: 4px 14px;
      margin: 12px 0;
      color: var(--meta);
    }}
    .markdown-body table {{
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 13px;
      width: 100%;
    }}
    .markdown-body th, .markdown-body td {{
      border: 1px solid var(--border);
      padding: 8px 12px;
      text-align: left;
    }}
    .markdown-body th {{ background: var(--code-bg); font-weight: 600; }}
    .markdown-body tr:nth-child(even) td {{ background: #fbfbf8; }}
    .markdown-body em {{ color: var(--meta); }}
    /* JSON quick views ──────────────────────────────────────────────── */
    .pick-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px 18px;
      margin-bottom: 12px;
      background: white;
    }}
    .pick-head {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
    .pick-basin {{
      font-family: ui-monospace, "SF Mono", Monaco, monospace;
      font-size: 14px;
      color: var(--accent);
      font-weight: 600;
    }}
    .pick-primary {{
      font-size: 13px;
      color: var(--fg);
    }}
    .pick-badge {{
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      background: var(--code-bg);
      color: var(--meta);
    }}
    .pick-badge.high {{ background: #dcfce7; color: #166534; }}
    .pick-badge.med  {{ background: #fef9c3; color: #854d0e; }}
    .pick-badge.low  {{ background: #fee2e2; color: #991b1b; }}
    .pick-meta {{ margin-top: 8px; font-size: 12px; color: var(--meta); }}
    .pick-failures {{ margin-top: 10px; font-size: 13px; }}
    .pick-failures ul {{ margin: 4px 0 0; padding-left: 20px; }}
    .routing-table {{
      border-collapse: collapse;
      font-size: 13px;
      width: 100%;
      margin: 12px 0;
    }}
    .routing-table th, .routing-table td {{
      border: 1px solid var(--border);
      padding: 6px 10px;
    }}
    .routing-table th {{ background: var(--code-bg); font-weight: 600; text-align: left; }}
    .routing-table td.score {{ text-align: right; font-family: ui-monospace, monospace; }}
    .routing-table td.best {{ background: rgba(34, 197, 94, 0.08); font-weight: 600; }}
    /* topics.json reader — basin-relation graph (Obsidian-style). */
    .topics-graph-wrap {{
      background: #1a1715;       /* ink-on-paper inverse — same hue family as --fg */
      border-radius: 8px;
      padding: 0;
      margin-bottom: 16px;
      position: relative;
      overflow: hidden;
      border: 1px solid var(--border);
    }}
    .topics-graph-svg {{
      display: block;
      width: 100%;
      height: 520px;
      background: radial-gradient(circle at center, #221c18 0%, #14110f 100%);
      cursor: grab;
    }}
    .topics-graph-svg:active {{ cursor: grabbing; }}
    .topics-graph-svg .link {{
      stroke: rgba(181, 116, 56, 0.35);   /* warm-brown, low opacity */
      stroke-width: 1px;
    }}
    .topics-graph-svg .link.strong {{
      stroke: rgba(181, 116, 56, 0.75);
      stroke-width: 2px;
    }}
    .topics-graph-svg .node {{
      cursor: pointer;
      stroke: rgba(255, 255, 255, 0.4);
      stroke-width: 1.5px;
    }}
    .topics-graph-svg .node:hover {{ stroke: white; stroke-width: 2.5px; }}
    .topics-graph-svg .label {{
      fill: rgba(255, 255, 255, 0.92);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-weight: 600;
      pointer-events: none;
      text-anchor: middle;
      paint-order: stroke fill;
      stroke: rgba(0, 0, 0, 0.7);
      stroke-width: 3px;
      stroke-linejoin: round;
    }}
    .topics-graph-hint {{
      position: absolute;
      bottom: 12px;
      right: 16px;
      font-size: 11px;
      color: rgba(255, 255, 255, 0.4);
      pointer-events: none;
    }}
    .topics-graph-detail {{
      background: white;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 12px;
      font-size: 13px;
      min-height: 64px;
    }}
    .topics-graph-detail .empty {{ color: var(--meta); padding: 0; text-align: left; }}
    .topics-graph-detail .basin-id {{
      font-family: ui-monospace, monospace;
      color: var(--accent);
      font-weight: 600;
    }}
    .topics-graph-detail .row-label {{ color: var(--meta); }}
    .topics-reps-label {{
      color: var(--meta);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-top: 10px;
      margin-bottom: 6px;
    }}
    .topics-reps-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .topics-rep {{
      background: var(--code-bg);
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 13px;
      color: var(--fg);
      border-left: 3px solid var(--accent);
      line-height: 1.5;
    }}
    /* JSON syntax highlight (used for topics.json Raw view + others) */
    .json-body {{ font-family: ui-monospace, monospace; font-size: 12px; }}
    .json-key {{ color: #255847; }}
    .json-str {{ color: #166534; }}
    .json-num {{ color: #b45309; }}
    .json-bool {{ color: #be185d; }}
    .json-null {{ color: var(--meta); }}
    /* View toggle */
    .view-toggle {{
      display: inline-flex;
      gap: 8px;
      margin-bottom: 16px;
      font-size: 12px;
    }}
    .view-toggle button {{
      border: 1px solid var(--border);
      background: white;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
      color: var(--meta);
    }}
    .view-toggle button.active {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
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
    // Memory contents are inlined at render time (not fetched at runtime)
    // so the viewer works under file:// from the desktop shortcut.
    // Refreshes whenever portal-html runs.
    window.__TRINITY_MEMORIES__ = {memories_payload};
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
    if (!file) {{
      clearContent();
      const errWrap = el("div", "error");
      errWrap.appendChild(document.createTextNode("Unknown memory: "));
      errWrap.appendChild(el("code", null, requested));
      errWrap.appendChild(document.createTextNode(". Pick one from the nav."));
      content.appendChild(errWrap);
    }} else {{
      // Read from the inlined payload — no fetch, works under file://.
      const text = window.__TRINITY_MEMORIES__?.[file.name];
      clearContent();
      content.appendChild(renderHeader(file));
      if (text === null || text === undefined || !text.trim()) {{
        content.appendChild(renderEmpty(file));
      }} else if (file.name.endsWith(".md")) {{
        renderMarkdown(content, text);
      }} else {{
        renderJson(content, file.name, text);
      }}
    }}

    // ─── Markdown rendering ──────────────────────────────────────────────
    // Uses `marked` (CDN dep, same pattern as petite-vue/Chart.js). Parsed
    // HTML goes through DOMParser so we never call innerHTML on the live
    // tree — avoids the XSS surface even if a memory file is hand-edited.
    function renderMarkdown(target, mdText) {{
      const wrap = el("div", "markdown-body");
      try {{
        const html = window.marked ? window.marked.parse(mdText) : null;
        if (html) {{
          const parsed = new DOMParser().parseFromString(html, "text/html");
          // Strip any <script>/<style>/<iframe> tags before adopting nodes —
          // marked doesn't emit them but a future config change could.
          parsed.querySelectorAll("script,style,iframe,object,embed").forEach(n => n.remove());
          while (parsed.body.firstChild) wrap.appendChild(parsed.body.firstChild);
        }} else {{
          // marked failed to load — fall through to raw text in <pre>
          wrap.appendChild(el("pre", "body", mdText));
        }}
      }} catch (e) {{
        wrap.appendChild(el("pre", "body", mdText));
      }}
      target.appendChild(wrap);
    }}

    // ─── JSON rendering ──────────────────────────────────────────────────
    // Two views: a schema-aware "Reader" view (cards/tables for picks +
    // routing) and a "Raw" pretty-printed JSON view. Toggle preserves
    // across nav clicks via the active button state.
    function renderJson(target, name, jsonText) {{
      let parsed = null;
      try {{ parsed = JSON.parse(jsonText); }}
      catch (_) {{
        target.appendChild(el("pre", "body", jsonText));
        return;
      }}

      const readerSupported = name === "picks.json" || name === "routing.json" || name === "topics.json";
      const toggleWrap = el("div", "view-toggle");
      const readerBtn = el("button", null, "Reader");
      const rawBtn = el("button", null, "Raw JSON");
      const viewWrap = el("div");

      function showReader() {{
        readerBtn.classList.add("active");
        rawBtn.classList.remove("active");
        clearChildren(viewWrap);
        if (name === "picks.json") renderPicksReader(viewWrap, parsed);
        else if (name === "routing.json") renderRoutingReader(viewWrap, parsed);
        else if (name === "topics.json") renderTopicsReader(viewWrap, parsed);
      }}
      function showRaw() {{
        rawBtn.classList.add("active");
        readerBtn.classList.remove("active");
        clearChildren(viewWrap);
        const pre = el("pre", "body json-body");
        pre.appendChild(highlightJson(JSON.stringify(parsed, null, 2)));
        viewWrap.appendChild(pre);
      }}

      readerBtn.addEventListener("click", showReader);
      rawBtn.addEventListener("click", showRaw);
      if (readerSupported) toggleWrap.appendChild(readerBtn);
      toggleWrap.appendChild(rawBtn);
      target.appendChild(toggleWrap);
      target.appendChild(viewWrap);
      if (readerSupported) showReader();
      else showRaw();
    }}

    function clearChildren(node) {{ while (node.firstChild) node.removeChild(node.firstChild); }}

    function trustBadgeClass(score) {{
      if (typeof score !== "number") return "";
      if (score >= 0.7) return "high";
      if (score >= 0.4) return "med";
      return "low";
    }}

    function renderPicksReader(target, picks) {{
      // picks.json shape: {{basin_id: {{routing_rule: {{primary, confidence, ...}},
      //   trust_score: {{value, interpretation}}, n_episodes, failure_modes, ...}}}}
      const basins = Object.keys(picks);
      if (basins.length === 0) {{
        target.appendChild(el("p", "meta", "No picks yet — run trinity-local consolidate."));
        return;
      }}
      basins.forEach(basinId => {{
        const p = picks[basinId];
        const card = el("div", "pick-card");
        const head = el("div", "pick-head");
        head.appendChild(el("span", "pick-basin", basinId));
        const rule = p.routing_rule || {{}};
        if (rule.primary) {{
          head.appendChild(el("span", "pick-primary", "Use " + rule.primary));
        }}
        const trust = p.trust_score || {{}};
        const tval = typeof trust.value === "number" ? trust.value : null;
        if (tval !== null) {{
          const badge = el("span", "pick-badge " + trustBadgeClass(tval),
            "trust " + tval.toFixed(2) + (trust.interpretation ? " · " + trust.interpretation : ""));
          head.appendChild(badge);
        }}
        if (typeof p.n_episodes === "number") {{
          head.appendChild(el("span", "pick-badge", "n=" + p.n_episodes));
        }}
        if (p.audit_status) {{
          head.appendChild(el("span", "pick-badge", "audit: " + p.audit_status));
        }}
        card.appendChild(head);
        if (rule.reasoning || rule.why_matters) {{
          card.appendChild(el("div", "pick-meta", rule.reasoning || rule.why_matters));
        }}
        if (Array.isArray(p.failure_modes) && p.failure_modes.length) {{
          const fwrap = el("div", "pick-failures");
          fwrap.appendChild(el("strong", null, "Known failure modes:"));
          const ul = el("ul");
          p.failure_modes.forEach(fm => ul.appendChild(el("li", null, typeof fm === "string" ? fm : JSON.stringify(fm))));
          fwrap.appendChild(ul);
          card.appendChild(fwrap);
        }}
        target.appendChild(card);
      }});
    }}

    function renderRoutingReader(target, routing) {{
      // routing.json shape: {{by_task_type: {{task: {{provider: {{n, overall}}}}}},
      //   best_per_task_type: {{task: provider}}, computed_at: iso}}
      const by = routing.by_task_type || {{}};
      const best = routing.best_per_task_type || {{}};
      const taskTypes = Object.keys(by).sort();
      if (taskTypes.length === 0) {{
        target.appendChild(el("p", "meta", "No routing data yet — record outcomes via record_outcome (or run replay-history)."));
        return;
      }}
      const providers = new Set();
      taskTypes.forEach(t => Object.keys(by[t] || {{}}).forEach(p => providers.add(p)));
      const provList = Array.from(providers).sort();

      const tbl = el("table", "routing-table");
      const thead = el("thead");
      const hr = el("tr");
      hr.appendChild(el("th", null, "Task type"));
      provList.forEach(p => hr.appendChild(el("th", null, p)));
      hr.appendChild(el("th", null, "Best"));
      thead.appendChild(hr);
      tbl.appendChild(thead);

      const tbody = el("tbody");
      taskTypes.forEach(t => {{
        const tr = el("tr");
        tr.appendChild(el("td", null, t));
        const row = by[t] || {{}};
        provList.forEach(p => {{
          const cell = row[p];
          const td = el("td", "score");
          if (cell && typeof cell.overall === "number") {{
            const txt = cell.overall.toFixed(1) + (typeof cell.n === "number" ? " (n=" + cell.n + ")" : "");
            td.textContent = txt;
            if (best[t] === p) td.classList.add("best");
          }} else {{
            td.textContent = "—";
          }}
          tr.appendChild(td);
        }});
        tr.appendChild(el("td", null, best[t] || "—"));
        tbody.appendChild(tr);
      }});
      tbl.appendChild(tbody);
      target.appendChild(tbl);
      if (routing.computed_at) {{
        target.appendChild(el("p", "meta", "Computed " + routing.computed_at));
      }}
    }}

    function renderTopicsReader(target, topics) {{
      // topics.json shape: {{basins: [{{id, size, top_terms, centroid, prompt_ids}}]}}
      // We visualize basins as a force-directed graph (Obsidian-style).
      // Nodes = basins (size by basin.size), edges = centroid cosine
      // similarity, force layout pulls related topics together so the
      // user can SEE which subjects cluster vs. which sit alone.
      const basins = Array.isArray(topics.basins) ? topics.basins.slice() : [];
      if (basins.length === 0) {{
        target.appendChild(el("p", "meta", "No topics yet — run trinity-local lens-build to compute basins."));
        return;
      }}

      // Detail panel above the graph — populated on node click.
      const detail = el("div", "topics-graph-detail");
      const detailEmpty = el("div", "empty", "Click a basin to see its top terms and prompt count.");
      detail.appendChild(detailEmpty);
      target.appendChild(detail);

      // Graph container — dark canvas + SVG overlay for the force layout.
      const graphWrap = el("div", "topics-graph-wrap");
      const svgNS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(svgNS, "svg");
      svg.setAttribute("class", "topics-graph-svg");
      svg.setAttribute("viewBox", "0 0 1000 520");
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
      graphWrap.appendChild(svg);
      const hint = el("div", "topics-graph-hint", "Drag nodes · scroll to zoom · click for detail");
      graphWrap.appendChild(hint);
      target.appendChild(graphWrap);

      if (!window.d3 || !window.d3.forceSimulation) {{
        graphWrap.removeChild(svg);
        graphWrap.appendChild(el("div", "topics-graph-hint",
          "Graph library not loaded — try the Raw JSON view."));
        return;
      }}

      const W = 1000, H = 520;
      // Cosine similarity over the centroid embeddings. Centroids are
      // 768-d (Nomic). 20 basins → 190 pairs → trivial.
      function cosine(a, b) {{
        if (!a || !b || a.length !== b.length) return 0;
        let dot = 0, na = 0, nb = 0;
        for (let i = 0; i < a.length; i++) {{
          const x = a[i], y = b[i];
          dot += x * y; na += x * x; nb += y * y;
        }}
        const denom = Math.sqrt(na) * Math.sqrt(nb);
        return denom > 0 ? dot / denom : 0;
      }}

      // Label = first 4 words of the top representative prompt — the
      // closest-to-centroid prompt is the most semantically central thing
      // the user actually asked, so its opening words tell you what this
      // basin is *about*. Falls back to TF-IDF top_terms when representatives
      // haven't been written yet (legacy topics.json files from before the
      // representatives feature shipped — those clear on the next lens-build).
      function labelFor(b) {{
        const reps = Array.isArray(b.representatives) ? b.representatives : [];
        if (reps.length && reps[0].snippet) {{
          const words = reps[0].snippet.trim().split(/\\s+/).slice(0, 4).join(" ");
          if (words) return words.length > 36 ? words.slice(0, 36) + "…" : words;
        }}
        return (b.top_terms && b.top_terms[0]) || b.id || "?";
      }}
      function tooltipFor(b) {{
        // Hover tooltip = full top representative if we have one.
        const reps = Array.isArray(b.representatives) ? b.representatives : [];
        if (reps.length && reps[0].snippet) return reps[0].snippet;
        return (b.top_terms || []).join(", ");
      }}
      const nodes = basins.map((b, i) => ({{
        id: b.id || ("b" + i),
        basin: b,
        size: b.size || 0,
        label: labelFor(b),
        tooltip: tooltipFor(b),
      }}));
      const sizeMax = nodes.reduce((m, n) => Math.max(m, n.size), 1);
      const sizeMin = nodes.reduce((m, n) => Math.min(m, n.size), sizeMax);
      // Node radius: sqrt-scale (so a basin 100x bigger is 10x wider, not 100x).
      function radiusFor(n) {{
        const t = Math.sqrt(Math.max(1, n.size) / sizeMax);
        return 10 + 32 * t;
      }}

      // Build edges: every pair with cosine > threshold. We tune the
      // threshold so each node gets ~3-5 neighbors on average — that's
      // the visual sweet spot. With 20 basins that means ~50 edges.
      const allPairs = [];
      for (let i = 0; i < basins.length; i++) {{
        for (let j = i + 1; j < basins.length; j++) {{
          const sim = cosine(basins[i].centroid, basins[j].centroid);
          allPairs.push({{ source: i, target: j, sim }});
        }}
      }}
      // Pick a similarity threshold so we keep the top ~3*n edges.
      const targetEdgeCount = Math.min(allPairs.length, nodes.length * 3);
      allPairs.sort((a, b) => b.sim - a.sim);
      const edges = allPairs.slice(0, targetEdgeCount).map(p => ({{
        source: nodes[p.source].id,
        target: nodes[p.target].id,
        sim: p.sim,
        strong: p.sim > 0.6,
      }}));

      // d3-force simulation. Force config tuned for 20 nodes:
      //   link distance proportional to (1 - sim) so similar basins sit close
      //   charge repels nodes so labels don't overlap
      //   center keeps the whole thing on canvas
      //   collide prevents node overlap
      const sim = window.d3.forceSimulation(nodes)
        .force("link", window.d3.forceLink(edges).id(d => d.id)
          .distance(d => 60 + (1 - d.sim) * 220)
          .strength(d => 0.2 + d.sim * 0.6))
        .force("charge", window.d3.forceManyBody().strength(-380))
        .force("center", window.d3.forceCenter(W / 2, H / 2))
        .force("collide", window.d3.forceCollide().radius(d => radiusFor(d) + 6).strength(0.9))
        .alpha(1).alphaDecay(0.025);

      // Pre-compute adjacency so click-highlight is O(1) per node.
      const neighborsOf = new Map();
      nodes.forEach(n => neighborsOf.set(n.id, new Set([n.id])));
      edges.forEach(e => {{
        const s = typeof e.source === "object" ? e.source.id : e.source;
        const t = typeof e.target === "object" ? e.target.id : e.target;
        neighborsOf.get(s)?.add(t);
        neighborsOf.get(t)?.add(s);
      }});

      // d3-zoom group — everything else nests inside `viewport` so the
      // zoom transform applies uniformly to links + nodes + labels.
      const d3svg = window.d3.select(svg);
      const viewport = d3svg.append("g").attr("class", "viewport");

      const linkSel = viewport.append("g")
        .selectAll("line")
        .data(edges)
        .join("line")
        .attr("class", d => d.strong ? "link strong" : "link");

      const nodeSel = viewport.append("g")
        .selectAll("circle")
        .data(nodes)
        .join("circle")
        .attr("class", "node")
        .attr("r", radiusFor)
        .attr("fill", d => {{
          // Warm-brown → forest-green gradient by size for hierarchy.
          // Matches DESIGN.md palette: accent (#b57438) → primary (#255847).
          const t = Math.sqrt(d.size / sizeMax);
          const hue = 28 + (155 - 28) * t;
          const sat = 50 + 5 * t;
          const light = 55 - 30 * t;
          return "hsl(" + hue + "," + sat + "%," + light + "%)";
        }})
        .on("click", (event, d) => {{
          event.stopPropagation();  // don't bubble to the svg background
          showDetail(d.basin);
          highlightNeighborhood(d.id);
        }});

      // Native SVG <title> for hover tooltip — first representative or
      // fallback to TF-IDF top terms. Browser renders it natively, no JS.
      nodeSel.append("title").text(d => d.tooltip);

      // Drag re-energizes the sim so the dragged node "pulls" neighbors
      // with it (Obsidian feel).
      nodeSel.call(window.d3.drag()
        .on("start", (event, d) => {{
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        }})
        .on("drag", (event, d) => {{ d.fx = event.x; d.fy = event.y; }})
        .on("end", (event, d) => {{
          if (!event.active) sim.alphaTarget(0);
          d.fx = null; d.fy = null;
        }}));

      const labelSel = viewport.append("g")
        .selectAll("text")
        .data(nodes)
        .join("text")
        .attr("class", "label")
        .attr("font-size", d => 11 + Math.sqrt(d.size / sizeMax) * 9)
        .text(d => d.label);

      // Background click clears the highlight selection.
      d3svg.on("click", () => clearHighlight());

      // d3-zoom: scroll-wheel zoom + click-drag pan over the viewport.
      // Scale clamped 0.5×–4× so the user can't lose the graph by
      // zooming to a single pixel or so far out it vanishes.
      if (window.d3.zoom) {{
        const zoom = window.d3.zoom()
          .scaleExtent([0.5, 4])
          .on("zoom", (event) => viewport.attr("transform", event.transform));
        d3svg.call(zoom);
      }}

      function highlightNeighborhood(centerId) {{
        const neighbors = neighborsOf.get(centerId) || new Set([centerId]);
        nodeSel.style("opacity", d => neighbors.has(d.id) ? 1 : 0.18);
        labelSel.style("opacity", d => neighbors.has(d.id) ? 1 : 0.18);
        linkSel.style("opacity", d => {{
          const s = typeof d.source === "object" ? d.source.id : d.source;
          const t = typeof d.target === "object" ? d.target.id : d.target;
          return (s === centerId || t === centerId) ? 1 : 0.05;
        }});
      }}
      function clearHighlight() {{
        nodeSel.style("opacity", 1);
        labelSel.style("opacity", 1);
        linkSel.style("opacity", null);  // back to CSS-defined stroke alpha
      }}

      sim.on("tick", () => {{
        linkSel
          .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        nodeSel.attr("cx", d => d.x).attr("cy", d => d.y);
        labelSel.attr("x", d => d.x).attr("y", d => d.y + radiusFor(d) + 14);
      }});

      function showDetail(b) {{
        const total = nodes.reduce((s, n) => s + n.size, 0);
        const pct = total > 0 ? (100 * (b.size || 0) / total) : 0;
        clearChildren(detail);
        const head = el("div");
        head.appendChild(el("span", "basin-id", b.id || "?"));
        head.appendChild(document.createTextNode(" · "));
        head.appendChild(document.createTextNode(
          (b.size || 0).toLocaleString() + " prompts (" + pct.toFixed(1) + "% of corpus)"));
        detail.appendChild(head);
        // Representatives — the top-K prompts closest to centroid.
        // This is the headline drill-down: TF-IDF top_terms surface
        // vocabulary, but representatives surface what the user was
        // actually asking. Surface them first so users see real prompts.
        if (Array.isArray(b.representatives) && b.representatives.length) {{
          detail.appendChild(el("div", "topics-reps-label",
            "Most-representative prompts (closest to centroid)"));
          const ul = el("ul", "topics-reps-list");
          b.representatives.forEach(rep => {{
            const li = el("li", "topics-rep", rep.snippet || rep.id || "");
            ul.appendChild(li);
          }});
          detail.appendChild(ul);
        }}
        if (Array.isArray(b.top_terms) && b.top_terms.length) {{
          const tline = el("div");
          tline.style.marginTop = "10px";
          tline.appendChild(el("span", "row-label", "Top terms: "));
          tline.appendChild(document.createTextNode(b.top_terms.join(", ")));
          detail.appendChild(tline);
        }}
        const idCount = Array.isArray(b.prompt_ids) ? b.prompt_ids.length : null;
        if (idCount !== null && idCount !== (b.size || 0)) {{
          // Pre-2026-05-12 topics.json files were written with prompt_ids
          // truncated to 50. New writes carry the full list. If they
          // diverge, the user has a stale on-disk topics.json — surface it.
          const note = el("div", "row-label");
          note.style.marginTop = "4px";
          note.style.fontSize = "12px";
          note.appendChild(document.createTextNode(
            "Stale topology: prompt_ids carries " + idCount + " entries vs basin size " +
            (b.size || 0) + ". Re-run trinity-local lens-build to refresh."));
          detail.appendChild(note);
        }}
      }}
    }}

    function highlightJson(text) {{
      // Token-level highlight — returns a DocumentFragment. Standalone
      // (no library) so we don't pull a JSON renderer just for this.
      const frag = document.createDocumentFragment();
      const re = /("[^"\\\\]*(?:\\\\.[^"\\\\]*)*")(\\s*:)?|\\b(true|false|null)\\b|(-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)/g;
      let last = 0;
      let m;
      while ((m = re.exec(text)) !== null) {{
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        if (m[1]) {{
          const span = el("span", m[2] ? "json-key" : "json-str", m[1]);
          frag.appendChild(span);
          if (m[2]) frag.appendChild(document.createTextNode(m[2]));
        }} else if (m[3]) {{
          frag.appendChild(el("span", m[3] === "null" ? "json-null" : "json-bool", m[3]));
        }} else if (m[4]) {{
          frag.appendChild(el("span", "json-num", m[4]));
        }}
        last = re.lastIndex;
      }}
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      return frag;
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
