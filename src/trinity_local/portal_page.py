from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from .council_status import council_status_dir
from .council_runtime import council_outcomes_dir, load_prompt_bundle
from .design_system import render_html_footer, render_html_head
from .dispatch_registry import make_dispatch_action
from .scoreboard import state_dir
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .signal_page import write_signal_page
from .telemetry import build_elo_snapshot, launchpad_telemetry_state


EXAMPLE_PROMPTS = [
    "Write a launch announcement for Trinity Local",
    "Research this company: [company name]",
    "Draft a product specification",
    "Plan an onboarding email sequence",
    "Debug this error: [error message]",
    "Explain this concept",
    "Write a technical blog post outline",
    "Create a project proposal",
]

PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"
CHART_JS_SRC = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"
TRINITY_APP_NAME = "Trinity.app"
LAUNCHPAD_ICON_RELATIVE_PATH = Path("assets") / "binary_code.jpg"
LEGACY_LAUNCHPAD_LINK_NAMES = (
    "Trinity Launchpad.webloc",
    "Trinity.webloc",
    "Trinity Launchpad.app",
)


def portal_pages_dir() -> Path:
    path = state_dir() / "portal_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_launchpad_link_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / "Desktop",
        home / "Applications",
    ]


def _remove_launchpad_artifact(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def _cleanup_legacy_launchpad_links(destination_dir: Path) -> None:
    for name in LEGACY_LAUNCHPAD_LINK_NAMES:
        legacy = destination_dir / name
        if legacy.exists() or legacy.is_symlink():
            _remove_launchpad_artifact(legacy)


def _launchpad_applescript(launchpad_path: Path) -> str:
    launchpad = str(launchpad_path.expanduser().resolve())
    # Use shell to open in default browser
    return f'do shell script "open \\"file://{launchpad}\\""\n'


def _compile_launchpad_app(target: Path, script: str) -> None:
    if target.exists() or target.is_symlink():
        _remove_launchpad_artifact(target)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "launchpad.applescript"
        source_path.write_text(script, encoding="utf-8")
        subprocess.run(
            ["osacompile", "-o", str(target), str(source_path)],
            check=True,
            capture_output=True,
            text=True,
        )


def _find_launchpad_icon_source() -> Path | None:
    candidate = _project_root() / LAUNCHPAD_ICON_RELATIVE_PATH
    if candidate.exists():
        return candidate
    return None


def _apply_launchpad_icon(app_path: Path, image_path: Path | None) -> None:
    if image_path is None or not image_path.exists():
        return
    try:
        from PIL import Image
    except ImportError:
        return

    resources_dir = app_path / "Contents" / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    target_icon = resources_dir / "applet.icns"
    with Image.open(image_path) as image:
        image = image.convert("RGBA")
        width, height = image.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        square = image.crop((left, top, left + side, top + side))
        square.save(
            target_icon,
            format="ICNS",
            sizes=[(size, size) for size in (16, 32, 64, 128, 256, 512, 1024)],
        )


def write_launchpad_app(destination_dir: Path, launchpad_path: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_legacy_launchpad_links(destination_dir)
    target = destination_dir / TRINITY_APP_NAME
    _compile_launchpad_app(target, _launchpad_applescript(launchpad_path))
    _apply_launchpad_icon(target, _find_launchpad_icon_source())
    return target


def install_launchpad_shortcuts(
    *,
    launchpad_path: Path | None = None,
    destinations: list[Path] | None = None,
) -> list[Path]:
    launchpad_path = launchpad_path or write_portal_html()
    destinations = destinations or _default_launchpad_link_dirs()
    written: list[Path] = []
    for destination in destinations:
        written.append(write_launchpad_app(destination, launchpad_path))
    return written


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _truncate(text: str, length: int = 88) -> str:
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


def _load_recent_councils(limit: int = 10) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for path in council_outcomes_dir().glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        bundle_id = raw.get("bundle_id")
        prompt = "[Council prompt unavailable]"
        if bundle_id:
            try:
                bundle = load_prompt_bundle(bundle_id)
                prompt = bundle.task_text.strip() or prompt
            except Exception:
                pass
        council_id = raw.get("council_run_id") or path.stem
        signal_path = write_signal_page(council_id)
        items.append(
            {
                "council_id": council_id,
                "bundle_id": bundle_id,
                "title": _truncate(prompt),
                "winner_provider": raw.get("winner_provider"),
                "created_at": raw.get("created_at"),
                "review_page_path": str((state_dir() / "review_pages" / f"{council_id}.html").resolve()),
                "signal_page_path": str(signal_path.resolve()) if signal_path else None,
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _elo_chart_data(snapshot: dict) -> dict:
    providers = snapshot.get("providers", {})
    labels = [provider.title() for provider in providers.keys()]
    values = [provider_data.get("elo", 1500) for provider_data in providers.values()]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Your Trinity rating",
                "data": values,
                "backgroundColor": "rgba(37, 88, 71, 0.18)",
                "borderColor": "#255847",
                "borderWidth": 2,
                "borderRadius": 10,
            }
        ],
    }


def _radar_chart_data(snapshot: dict) -> dict | None:
    providers = snapshot.get("providers", {})
    if not providers:
        return None

    provider_names = list(providers.keys())
    if len(provider_names) < 2:
        return None

    datasets = []
    colors = [
        {"bg": "rgba(37, 88, 71, 0.15)", "border": "#255847"},
        {"bg": "rgba(88, 65, 37, 0.15)", "border": "#8b6f47"},
        {"bg": "rgba(65, 37, 88, 0.15)", "border": "#6b4b8b"},
        {"bg": "rgba(88, 37, 65, 0.15)", "border": "#8b4b6f"},
    ]

    for idx, provider_name in enumerate(provider_names):
        provider_data = providers.get(provider_name, {})
        elo = provider_data.get("elo", 1500)
        elo_normalized = min(100, max(0, (elo - 1400) / 2))

        total_games = provider_data.get("total_games", 0)
        wins = provider_data.get("wins", 0)
        win_rate = (wins / total_games * 100) if total_games > 0 else 0

        color = colors[idx % len(colors)]
        datasets.append({
            "label": provider_name.replace("_", " ").title(),
            "data": [
                min(100, elo_normalized),
                min(100, win_rate),
                min(100, provider_data.get("consistency", 50)),
            ],
            "borderColor": color["border"],
            "backgroundColor": color["bg"],
            "borderWidth": 2,
            "pointRadius": 5,
            "pointBackgroundColor": color["border"],
            "pointBorderColor": "#fff",
            "pointBorderWidth": 2,
        })

    return {
        "labels": ["Elo Rating", "Win Rate", "Consistency"],
        "datasets": datasets,
    }


def _settings_links() -> dict[str, str]:
    enable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-enable"},
            metadata={"kind": "telemetry_enable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    disable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-disable"},
            metadata={"kind": "telemetry_disable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    reset = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-reset-id"},
            metadata={"kind": "telemetry_reset"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    return {
        "enable": enable.url,
        "disable": disable.url,
        "reset": reset.url,
    }


def render_launchpad_html(*, title: str = "Trinity Launchpad") -> str:
    recent_councils = _load_recent_councils(limit=8)
    telemetry = launchpad_telemetry_state()
    elo_snapshot = build_elo_snapshot()
    chart_data = _elo_chart_data(elo_snapshot)
    radar_data = _radar_chart_data(elo_snapshot)
    settings_links = _settings_links()

    page_data = {
        "shortcutName": DEFAULT_SHORTCUT_NAME,
        "examplePrompts": EXAMPLE_PROMPTS,
        "defaultGoal": "Find the strongest answer.",
        "defaultMembers": ["claude", "gemini", "codex"],
        "defaultPrimaryProvider": "claude",
        "recentCouncils": recent_councils,
        "telemetry": telemetry,
        "settingsLinks": settings_links,
        "eloChart": chart_data,
        "radarChart": radar_data,
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
    }

    recent_cards = "".join(
        f"""
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <a href="file://{_esc(item['review_page_path'])}" style="text-decoration: none; cursor: pointer;" class="council-card-link">
            <article class="card council-card">
              <div class="eyebrow">Council</div>
              <h3 class="council-title">{_esc(str(item['title']))}</h3>
              <p class="meta">{_esc((item.get('winner_provider') or 'No winner yet').replace('_', ' ').title())} · {_esc(item.get('created_at') or 'unknown')}</p>
            </article>
          </a>
          {f'<a href="file://{_esc(item["signal_page_path"])}" style="color: var(--action); font-weight: 600; text-decoration: none;">Rate & Compare</a>' if item.get('signal_page_path') else ''}
        </div>
        """
        for item in recent_councils
        if item.get('review_page_path')
    ) or '<p class="meta">No councils yet. Launch one above to get started.</p>'

    extra_head = f"""
  <script src="{CHART_JS_SRC}"></script>
"""
    head = render_html_head(f"{title} — Council First", extra_head=extra_head)
    footer = render_html_footer()

    return f"""{head}
  <style>
    .launchpad-shell {{
      display: grid;
      gap: 32px;
    }}

    .hero-shell {{
      display: grid;
      gap: 24px;
    }}

    .launch-grid {{
      display: grid;
      gap: 24px;
      grid-template-columns: 1.35fr 0.9fr;
    }}

    @media (max-width: 900px) {{
      .launch-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    textarea {{
      width: 100%;
      min-height: 132px;
      padding: 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      font-family: inherit;
      font-size: 16px;
      resize: vertical;
      background: var(--surface);
      color: var(--text-primary);
    }}

    textarea:focus {{
      outline: none;
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.1);
    }}

    .examples-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 8px;
      margin-top: 8px;
    }}

    .example-btn {{
      padding: 10px 12px;
      background: var(--surface-muted);
      border: 1px solid var(--border);
      border-radius: 12px;
      cursor: pointer;
      font-size: 13px;
      color: var(--text-secondary);
      text-align: left;
    }}

    .example-btn:hover {{
      border-color: var(--action);
      color: var(--action);
      background: var(--surface);
    }}

    .telemetry-box {{
      display: grid;
      gap: 12px;
    }}

    .settings-list {{
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }}

    .setting-row {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 10px 0;
      border-top: 1px solid var(--border);
    }}

    .setting-row:first-child {{
      border-top: none;
    }}

    .chart-shell {{
      position: relative;
      height: 280px;
      margin-top: 16px;
    }}

    .council-card-link {{
      display: block;
      color: inherit;
    }}

    .council-card {{
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      cursor: pointer;
    }}

    .council-card-link:hover .council-card {{
      transform: translateY(-3px);
      border-color: var(--action);
      box-shadow: 0 12px 30px rgba(37, 88, 71, 0.14);
    }}

    .council-title {{
      margin-bottom: 8px;
    }}

    .subtle-note {{
      font-size: 14px;
      color: var(--text-muted);
    }}

    .launch-status {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
      padding: 16px;
      border: 1px solid rgba(37, 88, 71, 0.18);
      border-radius: 16px;
      background: rgba(37, 88, 71, 0.05);
    }}

    .spinner-row {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
    }}

    .spinner {{
      width: 18px;
      height: 18px;
      border-radius: 999px;
      border: 2px solid rgba(37, 88, 71, 0.18);
      border-top-color: var(--action);
      animation: trinity-spin 0.8s linear infinite;
    }}

    .status-error {{
      color: #8b1e1e;
    }}

    .status-message {{
      font-weight: 500;
      min-height: 24px;
      transition: opacity 0.3s ease;
    }}

    @keyframes trinity-spin {{
      to {{
        transform: rotate(360deg);
      }}
    }}

    @keyframes fade-in {{
      from {{
        opacity: 0;
      }}
      to {{
        opacity: 1;
      }}
    }}
  </style>

  <main>
    <div class="launchpad-shell" id="launchpad-app" v-scope="LaunchpadApp(pageData)">
      <section class="card hero-shell" style="display: flex; justify-content: space-between; align-items: start;">
        <div>
          <div class="eyebrow">Trinity Launchpad</div>
          <h1>Run Your First Council</h1>
          <p class="lede">Ask the same question. See all the answers. Let Trinity compare real models on your real work.</p>
        </div>
        <button type="button" @click="settingsOpen = !settingsOpen" style="background: none; border: none; cursor: pointer; padding: 8px; opacity: 0.7;" title="Settings">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M12 1v6m0 6v6M4.22 4.22l4.24 4.24m2.98 2.98l4.24 4.24M1 12h6m6 0h6M4.22 19.78l4.24-4.24m2.98-2.98l4.24-4.24M19.78 19.78l-4.24-4.24m-2.98-2.98l-4.24-4.24"></path>
          </svg>
        </button>
      </section>

      <section class="settings-modal" v-if="settingsOpen" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;">
        <div class="card" style="max-width: 400px; margin: 20px;">
          <button @click="settingsOpen = false" style="position: absolute; top: 16px; right: 16px; background: none; border: none; cursor: pointer; font-size: 20px;">×</button>
          <div class="eyebrow">Sharing</div>
          <h2>Anonymous benchmark settings</h2>
          <p class="meta">Telemetry is opt-in. Trinity can share anonymous Launchpad views and Elo summaries, but not raw prompts, outputs, code, or file paths.</p>

          <div class="settings-list">
            <div class="setting-row">
              <span class="meta">Sharing enabled</span>
              <span :class="telemetryEnabled ? 'badge success' : 'badge'">{{{{ telemetryEnabled ? 'On' : 'Off' }}}}</span>
            </div>
            <div class="setting-row">
              <span class="meta">Endpoint</span>
              <span class="meta">{{{{ telemetryEndpoint || 'Not configured' }}}}</span>
            </div>
            <div class="setting-row">
              <span class="meta">Anonymous ID</span>
              <code style="word-break: break-all;">{{{{ shareInstallId || 'unassigned' }}}}</code>
            </div>
          </div>

          <div class="actions">
            <a class="button primary" :href="settingsLinks.enable" @click="settingsOpen = false">Enable sharing</a>
            <a class="button secondary" :href="settingsLinks.disable" @click="settingsOpen = false">Disable sharing</a>
            <a class="button ghost" :href="settingsLinks.reset" @click="settingsOpen = false">Reset anonymous ID</a>
          </div>
        </div>
      </section>

      <section class="launch-grid">
        <article class="card">
          <div class="eyebrow">Council</div>
          <h2>Compare a task across models</h2>
          <p class="meta">This is the fastest first win. Trinity packages the task, runs the council, and opens the review page when it finishes.</p>
          <label class="label mb-sm" for="council-prompt">Task</label>
          <textarea id="council-prompt" v-model="prompt" placeholder="Write a launch announcement for Trinity Local"></textarea>

          <div class="label mb-sm" style="margin-top: 16px;">Quick start examples</div>
          <div class="examples-grid">
            <button type="button" class="example-btn" v-for="example in examplePrompts" @click="prompt = example">{{{{ example }}}}</button>
          </div>

          <div class="actions" style="margin-top: 18px;">
            <button type="button" class="button primary" @click="launchCouncil" :disabled="busy">Launch Council</button>
          </div>

          <section class="launch-status" v-if="busy || launchError">
            <div class="spinner-row" v-if="busy">
              <span class="spinner" aria-hidden="true"></span>
              <strong class="status-message">{{{{ currentStatusMessage }}}}</strong>
            </div>
            <p class="subtle-note" v-if="busy">Trinity Dispatch is running the council locally. This tab will open the result as soon as the review page is ready.</p>
            <p class="meta" v-if="busy && pendingPrompt">{{{{ pendingPrompt }}}}</p>
            <p class="status-error" v-if="launchError">{{{{ launchError }}}}</p>
          </section>
        </article>
      </section>

      <section class="card">
        <div class="eyebrow">Your ratings</div>
        <h2>Current provider scores</h2>
        <p class="meta">These local scores are derived from completed councils. Public Elo comes later, once telemetry aggregation is live.</p>
        <div class="chart-shell">
          <canvas id="provider-elo-chart"></canvas>
        </div>
      </section>

      <section class="card" v-if="hasRadarChart">
        <div class="eyebrow">Strengths</div>
        <h2>Provider performance profile</h2>
        <p class="meta">Multi-dimensional comparison across Elo rating, win rate, and consistency.</p>
        <div class="chart-shell">
          <canvas id="provider-radar-chart"></canvas>
        </div>
      </section>

      <section class="card">
        <div class="eyebrow">Recent councils</div>
        <h2>Rate and compare previous runs</h2>
        <p class="meta">Open the signal page to compare answers and record which model you preferred.</p>
        <div class="grid grid-2" style="margin-top: 20px;">
          {recent_cards}
        </div>
      </section>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';

    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    function buildShortcutUrl(payload) {{
      const name = encodeURIComponent(pageData.shortcutName || 'Trinity Dispatch');
      const text = encodeURIComponent(JSON.stringify(payload));
      return `shortcuts://run-shortcut?name=${{name}}&input=text&text=${{text}}`;
    }}

    window.__TRINITY_COUNCIL_STATUS__ = window.__TRINITY_COUNCIL_STATUS__ || {{}};

    function loadStatusScript(token, onComplete) {{
      const base = pageData.statusScriptBaseUrl;
      if (!base) return;
      const script = document.createElement('script');
      script.src = `${{base}}/council_status_${{encodeURIComponent(token)}}.js?t=${{Date.now()}}`;
      script.async = true;
      script.onload = () => {{
        const status = window.__TRINITY_COUNCIL_STATUS__?.[token];
        onComplete(status || null);
        script.remove();
      }};
      script.onerror = () => {{
        onComplete(null);
        script.remove();
      }};
      document.body.appendChild(script);
    }}

    function maybeSendTelemetry() {{
      const telemetry = pageData.telemetry || {{}};
      const settings = telemetry.settings || {{}};
      if (!settings.sharing_enabled || !settings.endpoint) {{
        return;
      }}

      const endpoint = settings.endpoint;
      const send = (payload) => {{
        const body = JSON.stringify(payload);
        if (navigator.sendBeacon) {{
          const blob = new Blob([body], {{ type: 'application/json' }});
          navigator.sendBeacon(endpoint, blob);
          return;
        }}
        fetch(endpoint, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body,
          keepalive: true,
          mode: 'cors',
        }}).catch(() => null);
      }};

      if (settings.share_usage_events !== false && telemetry.view_event) {{
        send(telemetry.view_event);
      }}

      if (settings.share_elo_summaries !== false && telemetry.elo_event && telemetry.snapshot_hash) {{
        const hashKey = `trinity:last-elo-hash:${{settings.share_install_id || 'default'}}`;
        const tsKey = `trinity:last-elo-ts:${{settings.share_install_id || 'default'}}`;
        const lastHash = localStorage.getItem(hashKey);
        const lastTs = Number(localStorage.getItem(tsKey) || '0');
        const dayMs = 24 * 60 * 60 * 1000;
        if (lastHash !== telemetry.snapshot_hash || (Date.now() - lastTs) > dayMs) {{
          send(telemetry.elo_event);
          localStorage.setItem(hashKey, telemetry.snapshot_hash);
          localStorage.setItem(tsKey, String(Date.now()));
        }}
      }}
    }}

    function renderChart() {{
      if (!window.Chart) return;
      const chartData = pageData.eloChart;
      if (!chartData || !chartData.labels || !chartData.labels.length) return;
      const ctx = document.getElementById('provider-elo-chart');
      new Chart(ctx, {{
        type: 'bar',
        data: chartData,
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
          }},
          scales: {{
            y: {{
              min: 1400,
              ticks: {{
                color: '#5f554d',
              }},
              grid: {{
                color: 'rgba(215, 204, 185, 0.45)',
              }},
            }},
            x: {{
              ticks: {{
                color: '#5f554d',
              }},
              grid: {{
                display: false,
              }},
            }},
          }},
        }},
      }});
    }}

    function renderRadarChart() {{
      if (!window.Chart) return;
      const radarData = pageData.radarChart;
      if (!radarData || !radarData.labels || !radarData.labels.length) return;
      const ctx = document.getElementById('provider-radar-chart');
      new Chart(ctx, {{
        type: 'radar',
        data: radarData,
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{
                color: '#5f554d',
                padding: 16,
              }},
            }},
          }},
          scales: {{
            r: {{
              min: 0,
              max: 100,
              ticks: {{
                color: '#5f554d',
                backdropColor: 'transparent',
              }},
              grid: {{
                color: 'rgba(215, 204, 185, 0.45)',
              }},
            }},
          }},
        }},
      }});
    }}

    function LaunchpadApp(pageData) {{
      return {{
        prompt: '',
        busy: false,
        launchError: '',
        pendingPrompt: '',
        pendingStatusToken: '',
        statusPollHandle: null,
        statusRotateHandle: null,
        currentStatusIndex: 0,
        settingsOpen: false,
        statusMessages: [
          'Running member responses...',
          'Peer review in progress...',
          'Synthesizing results...',
          'Compiling analysis...',
        ],
        examplePrompts: pageData.examplePrompts || [],
        settingsLinks: pageData.settingsLinks || {{}},
        telemetryEnabled: !!pageData.telemetry?.settings?.sharing_enabled,
        telemetryEndpoint: pageData.telemetry?.settings?.endpoint || '',
        shareInstallId: pageData.telemetry?.settings?.share_install_id || '',
        get currentStatusMessage() {{
          return this.statusMessages[this.currentStatusIndex % this.statusMessages.length];
        }},
        get hasRadarChart() {{
          return !!pageData.radarChart && pageData.radarChart.labels && pageData.radarChart.labels.length > 0;
        }},
        triggerShortcut(url) {{
          const link = document.createElement('a');
          link.href = url;
          link.rel = 'noreferrer';
          document.body.appendChild(link);
          link.click();
          link.remove();
        }},
        startCouncilPolling(token) {{
          if (this.statusPollHandle) {{
            clearInterval(this.statusPollHandle);
          }}
          if (this.statusRotateHandle) {{
            clearInterval(this.statusRotateHandle);
          }}
          this.currentStatusIndex = 0;
          this.statusRotateHandle = window.setInterval(() => {{
            this.currentStatusIndex++;
          }}, 2500);
          const check = () => {{
            loadStatusScript(token, (status) => {{
              if (!status) return;
              if (status.status === 'running') {{
                return;
              }}
              if (status.status === 'failed') {{
                this.busy = false;
                this.launchError = status.error || 'Council failed.';
                if (this.statusPollHandle) {{
                  clearInterval(this.statusPollHandle);
                  this.statusPollHandle = null;
                }}
                if (this.statusRotateHandle) {{
                  clearInterval(this.statusRotateHandle);
                  this.statusRotateHandle = null;
                }}
                return;
              }}
              if (status.status === 'completed' && status.review_path) {{
                this.busy = false;
                if (this.statusPollHandle) {{
                  clearInterval(this.statusPollHandle);
                  this.statusPollHandle = null;
                }}
                if (this.statusRotateHandle) {{
                  clearInterval(this.statusRotateHandle);
                  this.statusRotateHandle = null;
                }}
                window.location.href = `file://${{encodeURI(status.review_path)}}`;
              }}
            }});
          }};
          check();
          this.statusPollHandle = window.setInterval(check, 1500);
        }},
        launchCouncil() {{
          const prompt = this.prompt.trim();
          if (!prompt) {{
            window.alert('Please enter a task first.');
            return;
          }}
          const statusToken = `launch_${{Date.now().toString(36)}}_${{Math.random().toString(36).slice(2, 8)}}`;
          this.busy = true;
          this.launchError = '';
          this.pendingPrompt = prompt;
          this.pendingStatusToken = statusToken;
          this.prompt = '';
          const payload = {{
            name: 'launch_council',
            args: {{
              task: prompt,
              goal: pageData.defaultGoal,
              members: pageData.defaultMembers,
              primary_provider: pageData.defaultPrimaryProvider,
              cwd: '.',
              status_token: statusToken,
              notify: true,
              open_browser: false,
            }},
            metadata: {{
              kind: 'launch_council',
              source: 'launchpad',
            }},
          }};
          this.startCouncilPolling(statusToken);
          this.triggerShortcut(buildShortcutUrl(payload));
        }},
      }};
    }}

    createApp({{ LaunchpadApp, pageData }}).mount();
    maybeSendTelemetry();
    renderChart();
    renderRadarChart();
  </script>
{footer}"""


def write_portal_html(*, title: str = "Trinity Launchpad", video_url: str | None = None) -> Path:
    path = portal_pages_dir() / "launchpad.html"
    path.write_text(render_launchpad_html(title=title), encoding="utf-8")
    return path
