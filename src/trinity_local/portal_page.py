from __future__ import annotations

import html
import json
from pathlib import Path

from .action_runtime import list_actions
from .dispatch_registry import make_dispatch_action
from .scoreboard import state_dir
from .shortcut_setup import write_shortcut_setup
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .task_runtime import load_task_record


def portal_pages_dir() -> Path:
    path = state_dir() / "portal_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _priority(kind: str) -> int:
    return {
        "start_council": 0,
        "review_ready": 1,
        "workflow_suggestion": 2,
        "recommendation": 3,
    }.get(kind, 9)


def _cta_label(kind: str) -> str:
    return {
        "start_council": "Start Council",
        "review_ready": "Open Review",
        "workflow_suggestion": "Create Workflow",
        "recommendation": "Run Suggestion",
    }.get(kind, "Run via Shortcuts")


def render_portal_html(*, title: str = "Trinity Launchpad", video_url: str | None = None) -> str:
    raw_actions = list_actions(status="pending")
    actions_by_task: dict[str, object] = {}
    for action in raw_actions:
        current = actions_by_task.get(action.task_id)
        if current is None or _priority(action.kind) < _priority(current.kind):
            actions_by_task[action.task_id] = action
    actions = sorted(actions_by_task.values(), key=lambda item: (_priority(item.kind), item.updated_at or "", item.task_id))
    cards: list[str] = []
    embedded_actions: list[dict] = []
    setup_path = write_shortcut_setup()
    setup_shortcut = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "open_path",
            args={"path": str(setup_path)},
            metadata={"kind": "setup_shortcut"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    refresh_portal = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local portal-html --open-browser"},
            metadata={"kind": "refresh_portal"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    for action in actions:
        task_title = action.message
        try:
            task = load_task_record(action.task_id)
            task_title = task.title
        except Exception:
            pass
        embedded_actions.append(action.to_dict())
        shortcut_button = ""
        if action.shortcut_url:
            shortcut_button = f'<a class="button primary" href="{_esc(action.shortcut_url)}">{_esc(_cta_label(action.kind))}</a>'
        command_hint = f"<code>{_esc(action.command_hint or '')}</code>" if action.command_hint else ""
        cards.append(
            f"""
            <article class="card">
              <div class="eyebrow">{_esc(action.kind.replace('_', ' '))}</div>
              <h3>{_esc(task_title)}</h3>
              <p>{_esc(action.message)}</p>
              <div class="meta">Status: {_esc(action.status)} · Task: {_esc(action.task_id)}</div>
              <div class="actions">
                {shortcut_button}
                <button class="button ghost copy-command" data-command="{_esc(action.command_hint or '')}">Copy command</button>
              </div>
              {f'<details><summary>Command</summary>{command_hint}</details>' if action.command_hint else ''}
            </article>
            """
        )
    video_block = ""
    if video_url:
        video_block = f"""
        <section class="hero card">
          <div>
            <div class="eyebrow">Onboarding</div>
            <h2>How Trinity works</h2>
            <p>Bookmark this page. When Trinity suggests a better tool or finishes a council run, the launch actions appear here.</p>
          </div>
          <div class="video-shell">
            <video controls playsinline preload="metadata" src="{_esc(video_url)}"></video>
          </div>
        </section>
        """
    actions_json = _esc(json.dumps(embedded_actions))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>
    :root {{
      --bg: #efe8dc;
      --paper: #fffdf8;
      --ink: #171512;
      --muted: #6f675a;
      --line: #d6ccb8;
      --accent: #145b4b;
      --accent-2: #db5c32;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(219,92,50,0.18), transparent 32%),
        radial-gradient(circle at right 10%, rgba(20,91,75,0.18), transparent 26%),
        linear-gradient(180deg, #f7f0e4 0%, var(--bg) 100%);
      font: 16px/1.5 Georgia, "Iowan Old Style", serif;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 18px 56px;
    }}
    .grid {{
      display: grid;
      gap: 18px;
    }}
    .cards {{
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.05);
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 20px;
      align-items: center;
      margin-bottom: 18px;
    }}
    @media (max-width: 860px) {{
      .hero {{ grid-template-columns: 1fr; }}
    }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    h1 {{ font-size: clamp(2rem, 4vw, 3.4rem); line-height: 0.95; }}
    h2 {{ font-size: 1.45rem; }}
    h3 {{ font-size: 1.15rem; }}
    .eyebrow {{
      margin-bottom: 10px;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font: 700 12px/1.1 ui-sans-serif, system-ui, sans-serif;
    }}
    .lede, .meta {{
      color: var(--muted);
      font-family: ui-sans-serif, system-ui, sans-serif;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      text-decoration: none;
      color: var(--ink);
      background: white;
      cursor: pointer;
      font: 600 13px/1.2 ui-sans-serif, system-ui, sans-serif;
    }}
    .button.primary {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}
    .button.ghost {{
      background: transparent;
    }}
    video {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: #000;
    }}
    code, pre {{
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    details {{
      margin-top: 12px;
    }}
    .tips {{
      display: grid;
      gap: 10px;
      margin-top: 20px;
    }}
    .tips li {{
      margin-left: 18px;
    }}
  </style>
</head>
<body>
  <main>
    <section class="card">
      <div class="eyebrow">Trinity</div>
      <h1>{_esc(title)}</h1>
      <p class="lede">Bookmark this page on macOS. It is static, local-first, and designed to launch actions through <code>shortcuts://</code> links rather than a resident server.</p>
      <div class="actions">
        <a class="button primary" href="{_esc(refresh_portal.url)}">Refresh Via Shortcuts</a>
        <a class="button" href="{_esc(setup_shortcut.url)}">Open Shortcut Setup</a>
      </div>
    </section>
    {video_block}
    <section class="card" style="margin-bottom:18px;">
      <h2>What This Page Can Do</h2>
      <ul class="tips">
        <li>Launch local automation through macOS Shortcuts links.</li>
        <li>Store lightweight local UI state in the browser, but file-based persistence is not reliable enough to be the source of truth.</li>
        <li>Show video, onboarding, copied commands, and provider actions without any backend.</li>
        <li>Mirror pending council and review actions written by Trinity.</li>
      </ul>
    </section>
    <section class="grid cards">
      {''.join(cards) or '<section class="card"><h3>No pending actions</h3><p class="lede">When Trinity suggests a reroute or finishes a council run, it will appear here.</p></section>'}
    </section>
  </main>
  <script type="application/json" id="trinity-actions">{actions_json}</script>
  <script>
    const actions = JSON.parse(document.getElementById("trinity-actions").textContent || "[]");
    try {{
      localStorage.setItem("trinity-last-portal-open", new Date().toISOString());
    }} catch (error) {{
      console.warn("localStorage unavailable for this file:", error);
    }}
    document.querySelectorAll(".copy-command").forEach((button) => {{
      button.addEventListener("click", async () => {{
        const command = button.dataset.command || "";
        if (!command) return;
        try {{
          await navigator.clipboard.writeText(command);
          button.textContent = "Copied";
          setTimeout(() => button.textContent = "Copy command", 1500);
        }} catch (error) {{
          window.prompt("Copy this command", command);
        }}
      }});
    }});
  </script>
</body>
</html>
"""


def write_portal_html(*, title: str = "Trinity Launchpad", video_url: str | None = None) -> Path:
    path = portal_pages_dir() / "launchpad.html"
    path.write_text(render_portal_html(title=title, video_url=video_url), encoding="utf-8")
    return path
