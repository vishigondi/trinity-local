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
    wordcloud_src = "https://cdn.jsdelivr.net/npm/wordcloud@1.2.2/src/wordcloud2.min.js"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trinity · Memory viewer</title>
  <script src="{marked_src}"></script>
  <script src="{wordcloud_src}"></script>
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
    /* topics.json reader — distribution of prompts across basins. */
    .topics-cloud-wrap {{
      background: white;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      display: flex;
      justify-content: center;
    }}
    .topics-cloud-canvas {{
      width: 100%;
      max-width: 720px;
      height: 320px;
      display: block;
    }}
    .topics-cloud-fallback {{
      color: var(--meta);
      font-size: 13px;
      padding: 20px;
      text-align: center;
    }}
    .topics-summary {{
      font-size: 13px;
      color: var(--meta);
      margin-bottom: 16px;
    }}
    .topics-summary strong {{ color: var(--fg); }}
    .basin-row {{
      display: grid;
      grid-template-columns: 56px 1fr 80px;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.1s;
      margin-bottom: 4px;
    }}
    .basin-row:hover {{ background: var(--code-bg); }}
    .basin-id {{
      font-family: ui-monospace, monospace;
      font-size: 12px;
      color: var(--accent);
      font-weight: 600;
    }}
    .basin-bar-wrap {{
      position: relative;
      height: 22px;
      background: var(--code-bg);
      border-radius: 4px;
      overflow: hidden;
    }}
    .basin-bar-fill {{
      position: absolute;
      top: 0;
      left: 0;
      bottom: 0;
      background: linear-gradient(90deg, #6366f1, #8b5cf6);
      border-radius: 4px;
    }}
    .basin-bar-label {{
      position: absolute;
      left: 10px;
      top: 0;
      bottom: 0;
      right: 10px;
      display: flex;
      align-items: center;
      font-size: 12px;
      color: white;
      font-weight: 600;
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      pointer-events: none;
    }}
    .basin-pct {{
      font-family: ui-monospace, monospace;
      font-size: 12px;
      color: var(--meta);
      text-align: right;
    }}
    .basin-detail {{
      margin: 2px 0 12px 68px;
      padding: 10px 14px;
      background: var(--code-bg);
      border-radius: 6px;
      font-size: 12px;
      color: var(--meta);
      display: none;
    }}
    .basin-detail.open {{ display: block; }}
    .basin-detail .row-label {{ color: var(--fg); font-weight: 500; }}
    /* JSON syntax highlight (used for topics.json Raw view + others) */
    .json-body {{ font-family: ui-monospace, monospace; font-size: 12px; }}
    .json-key {{ color: #6366f1; }}
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
      // The centroid is 768-d — never shown directly. We visualize size
      // distribution across basins so users see what they ask about most.
      const basins = Array.isArray(topics.basins) ? topics.basins.slice() : [];
      if (basins.length === 0) {{
        target.appendChild(el("p", "meta", "No topics yet — run trinity-local lens-build to compute basins."));
        return;
      }}

      const total = basins.reduce((s, b) => s + (typeof b.size === "number" ? b.size : 0), 0);
      const maxSize = basins.reduce((m, b) => Math.max(m, b.size || 0), 1);

      // Cloud first — visual punch. wordcloud2.js packs words on a canvas
      // sized by weight; the bars below give exact numbers.
      const cloudWrap = el("div", "topics-cloud-wrap");
      const canvas = document.createElement("canvas");
      canvas.className = "topics-cloud-canvas";
      // Set explicit pixel dimensions — wordcloud2 uses these directly,
      // not CSS dimensions. 1440×640 gives a 2:1 aspect at a comfortable
      // resolution for high-DPI screens.
      canvas.width = 1440;
      canvas.height = 640;
      cloudWrap.appendChild(canvas);
      target.appendChild(cloudWrap);

      // Words: each basin's top_terms[0] sized by basin.size.
      // De-dupe in case two basins share a top term (rare but possible
      // after a reseed — keep the larger).
      const wordMap = new Map();
      basins.forEach(b => {{
        const word = (b.top_terms && b.top_terms[0]) || b.id;
        if (!word) return;
        const prev = wordMap.get(word) || 0;
        if ((b.size || 0) > prev) wordMap.set(word, b.size || 0);
      }});
      const list = Array.from(wordMap.entries()); // [[word, weight], ...]

      if (typeof window.WordCloud === "function" && list.length > 0) {{
        // wordcloud2 raw weight → font px is linear. With basin sizes
        // ranging 23 → 2990, linear scaling makes the smallest words
        // invisible. Sqrt-scale so the small basins still read at ~14px
        // while the largest hits ~160px. Tuned for the 1440×640 canvas.
        const cloudMax = list.reduce((m, w) => Math.max(m, w[1]), 1);
        const TARGET_MAX_PX = 160;
        const TARGET_MIN_PX = 16;
        // Build a derived list where each weight is the desired font-px;
        // weightFactor stays 1 so wordcloud2 uses our values directly.
        const scaledList = list.map(([word, raw]) => {{
          const t = Math.sqrt(raw / cloudMax);  // sqrt — emphasis on smaller words
          const px = TARGET_MIN_PX + (TARGET_MAX_PX - TARGET_MIN_PX) * t;
          return [word, px];
        }});
        try {{
          window.WordCloud(canvas, {{
            list: scaledList,
            gridSize: 8,
            weightFactor: 1,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            fontWeight: 600,
            color: function (word, weight) {{
              // Indigo-violet gradient — bigger words darker for hierarchy.
              const t = Math.min(1, weight / TARGET_MAX_PX);
              const hue = 246 - 22 * t;
              const sat = 65 + 10 * t;
              const light = 58 - 26 * t;
              return "hsl(" + hue + "," + sat + "%," + light + "%)";
            }},
            rotateRatio: 0.25,
            rotationSteps: 2,
            backgroundColor: "transparent",
            shrinkToFit: true,
            drawOutOfBound: false,
          }});
        }} catch (err) {{
          cloudWrap.removeChild(canvas);
          cloudWrap.appendChild(el("div", "topics-cloud-fallback",
            "Cloud render failed (" + err.message + "). Showing bars below."));
        }}
      }} else {{
        cloudWrap.removeChild(canvas);
        cloudWrap.appendChild(el("div", "topics-cloud-fallback",
          "Cloud library not loaded — showing bars below."));
      }}

      const summary = el("div", "topics-summary");
      summary.appendChild(document.createTextNode(basins.length + " basins · "));
      summary.appendChild(el("strong", null, total.toLocaleString() + " prompts"));
      summary.appendChild(document.createTextNode(" clustered. Largest: "));
      const largest = basins.reduce((a, b) => (a.size || 0) >= (b.size || 0) ? a : b);
      summary.appendChild(el("strong", null,
        (largest.top_terms && largest.top_terms[0]) || largest.id || "?"));
      summary.appendChild(document.createTextNode(
        " (" + (largest.size || 0).toLocaleString() + " prompts, " +
        Math.round(100 * (largest.size || 0) / Math.max(total, 1)) + "%)."));
      target.appendChild(summary);

      // Sort descending by size — biggest topics first, since that's the
      // "what dominates your asking" story.
      basins.sort((a, b) => (b.size || 0) - (a.size || 0));

      basins.forEach(b => {{
        const id = b.id || "?";
        const size = b.size || 0;
        const pct = total > 0 ? (100 * size / total) : 0;
        const widthPct = (size / maxSize) * 100;
        const label = (b.top_terms && b.top_terms[0]) || "(no top term)";

        const row = el("div", "basin-row");
        row.appendChild(el("span", "basin-id", id));

        const barWrap = el("div", "basin-bar-wrap");
        const fill = el("div", "basin-bar-fill");
        fill.style.width = widthPct + "%";
        barWrap.appendChild(fill);
        barWrap.appendChild(el("span", "basin-bar-label",
          (b.top_terms || []).slice(0, 3).join(" · ") || label));
        row.appendChild(barWrap);

        row.appendChild(el("span", "basin-pct",
          size.toLocaleString() + " · " + pct.toFixed(1) + "%"));

        const detail = el("div", "basin-detail");
        // top_terms full list
        if (Array.isArray(b.top_terms) && b.top_terms.length) {{
          const tline = el("div");
          tline.appendChild(el("span", "row-label", "Top terms: "));
          tline.appendChild(document.createTextNode(b.top_terms.join(", ")));
          detail.appendChild(tline);
        }}
        // prompt_ids count (we don't show the ids themselves — they're opaque)
        const idCount = Array.isArray(b.prompt_ids) ? b.prompt_ids.length : null;
        if (idCount !== null) {{
          const pline = el("div");
          pline.appendChild(el("span", "row-label", "Assigned prompt IDs: "));
          pline.appendChild(document.createTextNode(idCount.toLocaleString()));
          if (idCount !== size) {{
            pline.appendChild(document.createTextNode(
              " (size " + size.toLocaleString() + " — drift means topology was recomputed; rerun lens-build)"));
          }}
          detail.appendChild(pline);
        }}
        // centroid presence indicator (don't dump 768 floats)
        const cline = el("div");
        cline.appendChild(el("span", "row-label", "Centroid: "));
        cline.appendChild(document.createTextNode(
          Array.isArray(b.centroid) ? (b.centroid.length + "-d embedding (hidden)") : "(missing)"));
        detail.appendChild(cline);

        row.addEventListener("click", () => detail.classList.toggle("open"));
        target.appendChild(row);
        target.appendChild(detail);
      }});
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
