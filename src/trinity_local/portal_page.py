from __future__ import annotations

import html
import json
from pathlib import Path

from .action_runtime import list_actions
from .design_system import render_html_footer, render_html_head
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
    head = render_html_head(f"{title} — Trinity")
    footer = render_html_footer()
    return f"""{head}
  <style>
    .tips {{
      display: grid;
      gap: 12px;
      margin-top: 16px;
      padding-left: 20px;
    }}
    .tips li {{
      color: var(--text-secondary);
    }}
  </style>
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
    <section class="card mb-lg">
      <h2>What This Page Can Do</h2>
      <ul class="tips">
        <li>Launch local automation through macOS Shortcuts links.</li>
        <li>Store lightweight local UI state in the browser, but file-based persistence is not reliable enough to be the source of truth.</li>
        <li>Show video, onboarding, copied commands, and provider actions without any backend.</li>
        <li>Mirror pending council and review actions written by Trinity.</li>
      </ul>
    </section>
    <section class="grid">
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
{footer}"""


def write_portal_html(*, title: str = "Trinity Launchpad", video_url: str | None = None) -> Path:
    path = portal_pages_dir() / "launchpad.html"
    path.write_text(render_portal_html(title=title, video_url=video_url), encoding="utf-8")
    return path
