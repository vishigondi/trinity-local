from __future__ import annotations

import json

from .design_system import render_html_footer, render_html_head
from .portal_runtime import portal_runtime_js

PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"
CHART_JS_SRC = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"


def render_launchpad_html(*, page_data: dict, recent_cards: str, title: str = "Trinity Launchpad") -> str:
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
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
    }}

    .launch-grid {{
      display: grid;
      gap: 24px;
      grid-template-columns: 1fr;
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

    .suggestions-panel {{
      margin-top: 14px;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--surface);
      box-shadow: 0 16px 36px rgba(57, 44, 26, 0.12);
      overflow: hidden;
    }}

    .suggestions-header {{
      padding: 12px 16px 10px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
    }}

    .suggestion-item {{
      width: 100%;
      padding: 14px 16px;
      background: transparent;
      border: none;
      border-top: 1px solid rgba(215, 204, 185, 0.5);
      cursor: pointer;
      text-align: left;
      color: var(--text-primary);
      font-size: 15px;
      line-height: 1.4;
      transition: background 0.18s ease, color 0.18s ease;
    }}

    .suggestion-item:first-of-type {{
      border-top: none;
    }}

    .suggestion-item:hover,
    .suggestion-item:focus-visible {{
      background: rgba(37, 88, 71, 0.06);
      color: var(--action);
      outline: none;
    }}

    .suggestion-empty {{
      padding: 14px 16px;
      color: var(--text-muted);
      font-size: 14px;
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

    .provider-health-list {{
      display: grid;
      gap: 12px;
      margin-top: 16px;
    }}

    .provider-health-item {{
      padding: 14px 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface-muted);
      display: grid;
      gap: 10px;
    }}

    .provider-health-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}

    .provider-command {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      flex-wrap: wrap;
    }}

    .provider-command code {{
      flex: 1 1 240px;
      word-break: break-word;
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

    .setting-value {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      justify-content: flex-end;
      flex-wrap: wrap;
    }}

    .icon-action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--action);
      cursor: pointer;
      transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
      padding: 0;
    }}

    .icon-action:hover {{
      border-color: var(--action);
      transform: translateY(-1px);
      box-shadow: 0 6px 18px rgba(37, 88, 71, 0.12);
    }}

    .icon-action:focus-visible {{
      outline: 2px solid rgba(37, 88, 71, 0.28);
      outline-offset: 2px;
    }}

    .icon-action:disabled {{
      opacity: 0.55;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
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
      color: var(--action);
    }}

    .provider-status-list {{
      display: grid;
      gap: 10px;
      margin: 4px 0 0;
    }}

    .provider-status-row {{
      display: grid;
      grid-template-columns: 88px 84px 1fr;
      gap: 12px;
      align-items: start;
      font-size: 15px;
      color: var(--text-primary);
    }}

    .provider-status-name {{
      font-weight: 600;
      text-transform: lowercase;
    }}

    .provider-status-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 74px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: var(--surface-muted);
      color: var(--text-secondary);
      border: 1px solid var(--border);
    }}

    .provider-status-badge.done {{
      background: rgba(45, 106, 79, 0.1);
      color: var(--success);
      border-color: rgba(45, 106, 79, 0.28);
    }}

    .provider-status-badge.running {{
      background: rgba(37, 88, 71, 0.08);
      color: var(--action);
      border-color: rgba(37, 88, 71, 0.22);
    }}

    .provider-status-badge.pending {{
      background: var(--surface-muted);
      color: var(--text-muted);
      border-color: var(--border);
    }}

    .provider-status-badge.failed {{
      background: rgba(139, 30, 30, 0.08);
      color: #8b1e1e;
      border-color: rgba(139, 30, 30, 0.2);
    }}

    .provider-status-detail {{
      color: var(--text-secondary);
      line-height: 1.4;
    }}

    .provider-status-detail.empty {{
      color: var(--text-muted);
    }}

    .launch-status-actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
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

    .rating-toggle {{
      display: flex;
      gap: 12px;
      font-size: 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 4px;
      background: var(--surface-muted);
    }}

    .toggle-btn {{
      padding: 6px 12px;
      background: none;
      border: none;
      cursor: pointer;
      color: var(--text-secondary);
      font-weight: 400;
      transition: color 0.2s ease;
    }}

    .toggle-btn:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
    }}

    .toggle-btn.active {{
      color: var(--action);
      font-weight: 600;
      background: var(--surface);
      border-radius: 6px;
      box-shadow: inset 0 0 0 1px rgba(37, 88, 71, 0.18);
    }}

    .toggle-btn:focus-visible {{
      outline: 2px solid rgba(37, 88, 71, 0.28);
      outline-offset: 2px;
      border-radius: 6px;
    }}

    .sharing-toggle {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      background: var(--surface-muted);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin: 16px 0;
    }}

    .toggle-switch {{
      position: relative;
      display: inline-block;
      width: 44px;
      height: 24px;
      cursor: pointer;
    }}

    .toggle-switch input {{
      opacity: 0;
      width: 0;
      height: 0;
    }}

    .toggle-slider {{
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: #ccc;
      transition: 0.3s;
      border-radius: 24px;
    }}

    .toggle-slider:before {{
      position: absolute;
      content: '';
      height: 20px;
      width: 20px;
      left: 2px;
      bottom: 2px;
      background-color: white;
      transition: 0.3s;
      border-radius: 50%;
    }}

    input:checked + .toggle-slider {{
      background: var(--action);
    }}

    input:checked + .toggle-slider:before {{
      transform: translateX(20px);
    }}

    .benchmark-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}

    .benchmark-table thead {{
      background: var(--surface-muted);
      border-bottom: 1px solid var(--border);
    }}

    .benchmark-table th {{
      padding: 12px;
      text-align: left;
      font-weight: 600;
      color: var(--text-primary);
    }}

    .benchmark-table td {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
    }}

    .benchmark-table tbody tr:hover {{
      background: var(--surface-muted);
    }}

    .benchmark-category {{
      font-weight: 500;
      color: var(--text-primary);
    }}

    .benchmark-score {{
      text-align: right;
      color: var(--action);
      font-weight: 500;
    }}

    .benchmark-unit {{
      font-size: 12px;
      color: var(--text-muted);
      display: block;
      font-weight: 400;
    }}

    .ratings-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 18px;
    }}

    .chart-panel {{
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      background: var(--surface);
    }}

    .chart-panel h3 {{
      margin-bottom: 8px;
    }}

    .chart-panel .meta {{
      margin-bottom: 12px;
    }}
  </style>

  <main>
    <div class="launchpad-shell" id="launchpad-app" v-scope="LaunchpadApp(pageData)" @vue:mounted="init">
      <section class="card hero-shell">
        <div>
          <div class="eyebrow">Trinity Launchpad</div>
          <h1>Run Your First Council</h1>
          <p class="lede">Ask the same question. See all the answers. Let Trinity compare real models on your real work.</p>
        </div>
        <button type="button" @click="settingsOpen = !settingsOpen" style="background: none; border: none; cursor: pointer; padding: 8px; opacity: 0.7; flex-shrink: 0;" title="Settings">
          <span aria-hidden="true" style="font-size: 24px; line-height: 1;">⚙</span>
        </button>
      </section>

      <section class="settings-modal" v-if="settingsOpen" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;">
        <div class="card" style="max-width: 460px; margin: 20px; position: relative;">
          <button @click="settingsOpen = false" style="position: absolute; top: 16px; right: 16px; background: none; border: none; cursor: pointer; font-size: 24px; opacity: 0.6; transition: opacity 0.2s;">×</button>
          <div class="eyebrow">Settings</div>
          <h2>Launchpad controls</h2>
          <p class="meta">Telemetry is opt-in. Trinity can share anonymous Launchpad views and Elo summaries, but not raw prompts, outputs, code, or file paths.</p>

          <div class="settings-list">
            <div class="setting-row">
              <span class="meta">Sharing enabled</span>
              <span :class="telemetry.enabled ? 'badge success' : 'badge'">{{{{ telemetry.enabled ? 'On' : 'Off' }}}}</span>
            </div>
            <div class="setting-row">
              <span class="meta">Endpoint</span>
              <span class="meta">{{{{ telemetry.endpoint || 'Not configured' }}}}</span>
            </div>
            <div class="setting-row">
              <span class="meta">Anonymous ID</span>
              <div class="setting-value">
                <code style="word-break: break-all;">{{{{ telemetry.shareInstallId || 'unassigned' }}}}</code>
                <button
                  type="button"
                  class="icon-action"
                  @click="resetAnonymousId"
                  title="Generate a new anonymous sharing ID"
                  aria-label="Reset anonymous ID"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M23 4v6h-6"></path>
                    <path d="M1 20v-6h6"></path>
                    <path d="M3.51 9a9 9 0 0 1 14.13-3.36L23 10"></path>
                    <path d="M20.49 15a9 9 0 0 1-14.13 3.36L1 14"></path>
                  </svg>
                </button>
              </div>
            </div>
            <div class="setting-row">
              <span class="meta">Auto ingest transcripts</span>
              <div class="setting-value">
                <span :class="telemetry.autoIngest ? 'badge success' : 'badge'">{{{{ telemetry.autoIngest ? 'On' : 'Off' }}}}</span>
                <button
                  type="button"
                  class="icon-action"
                  @click="ingestOnce"
                  :disabled="busy"
                  title="Ingest transcripts once now"
                  aria-label="Ingest transcripts once now"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                </button>
              </div>
            </div>
            <div class="setting-row">
              <span class="meta">Auto-ingest daemon</span>
              <span class="meta">{{{{ telemetry.daemonMessage }}}}</span>
            </div>
          </div>

          <div class="sharing-toggle">
            <span class="meta">Sharing enabled</span>
            <label class="toggle-switch">
              <input type="checkbox" :checked="telemetry.enabled" @change="toggleSharing">
              <span class="toggle-slider"></span>
            </label>
          </div>

          <div class="sharing-toggle" style="margin-top: 0;">
            <span class="meta">Auto ingest transcripts</span>
            <label class="toggle-switch">
              <input type="checkbox" :checked="telemetry.autoIngest" @change="toggleAutoIngest">
              <span class="toggle-slider"></span>
            </label>
          </div>

          <section class="provider-health-list" v-if="providerHealth.providers.length">
            <div class="eyebrow">Providers</div>
            <div class="provider-health-item" v-for="provider in providerHealth.providers">
              <div class="provider-health-head">
                <strong>{{{{ provider.label }}}}</strong>
                <span :class="provider.installed ? 'badge success' : 'badge'">{{{{ provider.installed ? 'Installed' : 'Missing' }}}}</span>
              </div>
              <p class="meta" v-if="provider.detail">{{{{ provider.detail }}}}</p>
              <div class="provider-command" v-if="!provider.installed">
                <code>{{{{ provider.installCommand }}}}</code>
                <button
                  type="button"
                  class="icon-action"
                  @click="copyText(provider.installCommand)"
                  title="Copy install command"
                  aria-label="Copy install command"
                >
                  ⧉
                </button>
              </div>
            </div>
            <p class="meta" v-if="providerHealth.hasMissing">{{{{ providerHealth.footerNote }}}}</p>
          </section>
        </div>
      </section>

      <section class="launch-grid">
        <article class="card">
          <div class="eyebrow">Council</div>
          <h2>Compare a task across models</h2>
          <p class="meta">This is the fastest first win. Trinity packages the task, runs the council, and opens the review page when it finishes.</p>
          <label class="label mb-sm" for="council-prompt">Task</label>
          <textarea
            id="council-prompt"
            v-model="prompt"
            placeholder="Ask a council question..."
            @focus="openSuggestions"
            @input="handlePromptInput"
            @blur="closeSuggestionsSoon"
          ></textarea>

          <div class="suggestions-panel" v-if="showSuggestions">
            <div class="suggestions-header">{{{{ suggestionsHeader }}}}</div>
            <button
              type="button"
              class="suggestion-item"
              v-for="suggestion in filteredCouncilSuggestions"
              @mousedown.prevent="applySuggestion(suggestion)"
            >{{{{ suggestion }}}}</button>
            <div class="suggestion-empty" v-if="!filteredCouncilSuggestions.length">No matching council queries yet.</div>
          </div>

          <div class="actions" style="margin-top: 18px;">
            <button type="button" class="button primary" @click="launchCouncil" :disabled="busy">Launch Council</button>
          </div>

              <section class="launch-status" v-if="operation || launchError">
                <div class="spinner-row" v-if="busy">
                  <span class="spinner" aria-hidden="true"></span>
                  <strong class="status-message">{{{{ operationHeading }}}}</strong>
                </div>
                <strong v-if="operation && !busy">{{{{ operationHeading }}}}</strong>
                <p class="meta" v-if="operation && operation.label">{{{{ operation.label }}}}</p>
                <p class="subtle-note" v-if="operation">{{{{ operationStatusNote }}}}</p>
                <p class="status-message" v-if="busy">{{{{ currentStatusMessage }}}}</p>
                <div class="provider-status-list" v-if="showProviderRows">
                  <div class="provider-status-row" v-for="row in providerStatusRows">
                    <div class="provider-status-name">{{{{ row.provider }}}}</div>
                    <div class="provider-status-badge" :class="row.statusClass">{{{{ row.statusLabel }}}}</div>
                    <div class="provider-status-detail" :class="{{ empty: !row.detail }}">{{{{ row.detail || '' }}}}</div>
                  </div>
                </div>
                <p class="status-error" v-if="launchError || operation?.error">{{{{ launchError || operation?.error }}}}</p>
                <div class="launch-status-actions" v-if="operation">
                  <button type="button" class="button ghost" v-if="operation.kind === 'council'" @click="openLiveReview">View live review</button>
                  <button type="button" class="button ghost" v-if="operation.kind === 'council' && busy" @click="stopCurrentCouncil">Stop council</button>
                  <button type="button" class="button ghost" v-if="!busy" @click="dismissOperation">Dismiss</button>
                </div>
              </section>
        </article>
      </section>

      <section class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <div>
            <div class="eyebrow">Ratings</div>
            <h2>My ratings</h2>
          </div>
          <div class="rating-toggle">
                <button
                  type="button"
                  class="toggle-btn"
                  :class="{{ active: !showReferenceRatings }}"
                  :aria-pressed="!showReferenceRatings"
                  @click="showReferenceRatings = false"
                >My ratings</button>
                <button
                  type="button"
                  class="toggle-btn"
                  :class="{{ active: showReferenceRatings }}"
                  :aria-pressed="showReferenceRatings"
                  @click="showReferenceRatings = true"
                >Reference evals</button>
          </div>
        </div>
        <p class="meta">{{{{ !showReferenceRatings ? 'Local scores and strengths from your saved council preferences.' : 'Public reference evals mapped to Trinity capability categories.' }}}}</p>

        <div v-show="!showReferenceRatings" class="ratings-grid">
          <section class="chart-panel">
            <h3>Current provider scores</h3>
            <p class="meta">Elo-style local rankings from your saved council preferences.</p>
            <div class="chart-shell">
              <canvas id="provider-elo-chart"></canvas>
            </div>
          </section>
        </div>

        <div v-show="showReferenceRatings">
          <table class="benchmark-table">
            <thead>
              <tr>
                <th>Benchmark</th>
                <th v-for="provider in benchmarkProviders" style="text-align: right;">{{{{ provider.toUpperCase() }}}}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(data, category) in globalBenchmarks">
                <td>
                  <div class="benchmark-category">{{{{ category.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }}}}</div>
                  <span class="benchmark-unit">{{{{ data.benchmark }}}}</span>
                </td>
                <td v-for="provider in benchmarkProviders" style="text-align: right;">
                  <span class="benchmark-score">{{{{ formatScore(data.models[provider], data.unit) }}}}</span>
                  <span class="benchmark-unit">{{{{ data.unit }}}}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <div class="eyebrow">Recent councils</div>
        <h2>Open previous council reviews</h2>
        <p class="meta">Reopen any review page and save your preferred model directly there.</p>
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

    {portal_runtime_js()}

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

    function normalizeOperation(raw, fallback = null) {{
      if (!raw) {{
        return fallback;
      }}
      const kind = raw.kind || raw.metadata?.kind || fallback?.kind || 'council';
      const memberMap = raw.members || fallback?.members || {{}};
      const fallbackOrder = fallback?.memberOrder || [];
      const rawOrder = raw.memberOrder || raw.metadata?.members || Object.keys(memberMap);
      return {{
        ...fallback,
        ...raw,
        kind,
        statusToken: raw.statusToken || raw.status_token || fallback?.statusToken || '',
        label: raw.label || raw.task_text || fallback?.label || '',
        memberOrder: rawOrder?.length ? rawOrder : fallbackOrder,
        members: memberMap,
        activeProvider: raw.activeProvider || raw.active_provider || fallback?.activeProvider || null,
        activeProviders: raw.activeProviders || raw.active_providers || fallback?.activeProviders || [],
        synthesis: raw.synthesis || fallback?.synthesis || {{}},
        reviewPath: raw.reviewPath || raw.review_path || fallback?.reviewPath || '',
        error: raw.error || fallback?.error || '',
      }};
    }}

    function LaunchpadApp(pageData) {{
      return {{
        prompt: '',
        suggestionsOpen: false,
        launchError: '',
        operation: normalizeOperation(pageData.activeOperation || null),
        statusPollHandle: null,
        statusRotateHandle: null,
        currentStatusIndex: 0,
        settingsOpen: false,
        showReferenceRatings: false,
        councilSuggestions: pageData.councilSuggestions || [],
        settingsLinks: pageData.settingsLinks || {{}},
        providerHealth: pageData.providerHealth || {{ providers: [], hasMissing: false, footerNote: '' }},
        telemetry: {{
          enabled: !!pageData.telemetry?.settings?.sharing_enabled,
          endpoint: pageData.telemetry?.settings?.endpoint || '',
          shareInstallId: pageData.telemetry?.settings?.share_install_id || '',
          autoIngest: !!pageData.telemetry?.settings?.auto_ingest_transcript,
          daemonMessage: pageData.daemon?.message || 'Watcher daemon status unavailable.',
          daemonRunning: !!pageData.daemon?.running,
        }},
        globalBenchmarks: pageData.globalBenchmarks || {{}},
        benchmarkProviders: pageData.benchmarkProviders || [],
        statusScriptBaseUrl: pageData.statusScriptBaseUrl || '',
        councilStatusMessages: pageData.councilLoadingMessages || [],
        ingestStatusMessages: [
          'Scanning recent transcripts...',
          'Extracting task signals...',
          'Writing launchpad updates...',
        ],
        init() {{
          if (this.operation?.statusToken) {{
            this.startOperationPolling(this.operation.statusToken);
          }}
        }},
        get normalizedPrompt() {{
          return (this.prompt || '').trim().toLowerCase();
        }},
        get filteredCouncilSuggestions() {{
          const suggestions = this.councilSuggestions || [];
          const query = this.normalizedPrompt;
          if (!query) {{
            return suggestions.slice(0, 6);
          }}
          const queryTokens = query.split(/\\s+/).filter(Boolean);
          return suggestions.filter((item) => {{
            const value = item.toLowerCase();
            return queryTokens.every((token) => value.includes(token));
          }}).slice(0, 6);
        }},
        get showSuggestions() {{
          return this.suggestionsOpen && !this.busy && this.councilSuggestions.length > 0;
        }},
        get suggestionsHeader() {{
          return this.normalizedPrompt ? 'Matching previous council queries' : 'Top used council queries';
        }},
        get busy() {{
          return !!this.operation && this.operation.status === 'running';
        }},
        get operationHeading() {{
          if (!this.operation) {{
            return '';
          }}
          if (this.operation.status === 'failed') {{
            return this.operation.kind === 'ingest' ? 'Transcript ingest failed' : 'Council failed';
          }}
          if (this.operation.status === 'canceled') {{
            return 'Council stopped';
          }}
          return this.operation.kind === 'ingest' ? 'Transcript ingest running' : 'Council running';
        }},
        get operationStatusNote() {{
          if (!this.operation) {{
            return '';
          }}
          if (this.operation.status === 'canceled') {{
            return 'This run was stopped before the final page was ready.';
          }}
          if (this.operation.status === 'failed') {{
            return 'Something went wrong while Trinity was running locally.';
          }}
          if (this.operation.kind === 'ingest') {{
            return 'Trinity is scanning recent transcripts once. This page will refresh when the new tasks and actions are ready.';
          }}
          return 'Trinity Dispatch is running the council locally. You can jump back into the live review page at any time while it finishes.';
        }},
        get currentStatusMessage() {{
          const messages = this.operation?.kind === 'ingest' ? this.ingestStatusMessages : this.councilStatusMessages;
          const message = messages[this.currentStatusIndex % messages.length] || 'Working...';
          if (this.operation?.kind === 'council') {{
            const synthesisStatus = this.operation?.synthesis?.status;
            if (synthesisStatus === 'running') {{
              return 'Synthesizing the strongest answer...';
            }}
            const activeProvider = this.operation?.activeProvider;
            if (activeProvider) {{
              return `${{activeProvider}}: ${{message}}`;
            }}
          }}
          return message;
        }},
        get showProviderRows() {{
          return this.operation?.kind === 'council' && this.providerStatusRows.length > 0;
        }},
        get providerStatusRows() {{
          if (this.operation?.kind !== 'council') {{
            return [];
          }}
          const memberMap = this.operation?.members || {{}};
          const providers = this.operation?.memberOrder?.length ? this.operation.memberOrder : Object.keys(memberMap);
          return providers.map((provider) => {{
            const item = memberMap[provider] || {{}};
            const status = item.status || 'pending';
            return {{
              provider,
              statusLabel: status === 'done' ? 'Done' : status === 'failed' ? 'Failed' : status === 'running' ? 'Running' : 'Queued',
              statusClass: status === 'done' ? 'done' : status === 'failed' ? 'failed' : status === 'running' ? 'running' : 'pending',
              detail: status === 'done'
                ? (item.reasoning_summary || 'Response ready.')
                : status === 'failed'
                  ? (item.reasoning_summary || 'Provider failed.')
                  : '',
            }};
          }});
        }},
        liveReviewUrlFor(operation) {{
          if (!operation?.statusToken) {{
            return pageData.liveReviewUrl;
          }}
          const params = new URLSearchParams({{
            status_token: operation.statusToken,
            task: operation.label || '',
          }});
          return `${{pageData.liveReviewUrl}}?${{params.toString()}}`;
        }},
        copyText(value) {{
          if (!value) {{
            return;
          }}
          if (navigator.clipboard?.writeText) {{
            navigator.clipboard.writeText(value).catch(() => null);
            return;
          }}
          window.prompt('Copy this command:', value);
        }},
        formatScore(score, unit) {{
          if (score === null || score === undefined) {{
            return '—';
          }}
          if (unit.includes('score')) {{
            return score.toFixed(1);
          }}
          if (unit.includes('%')) {{
            return score.toFixed(1);
          }}
          return score.toFixed(1);
        }},
        triggerShortcut(url) {{
          const link = document.createElement('a');
          link.href = url;
          link.rel = 'noreferrer';
          document.body.appendChild(link);
          link.click();
          link.remove();
        }},
        scheduleLaunchpadReload(delay = 1400) {{
          window.setTimeout(() => {{
            window.location.reload();
          }}, delay);
        }},
        triggerSettingsAction(url, beforeTrigger = null) {{
          if (beforeTrigger) {{
            beforeTrigger();
          }}
          this.triggerShortcut(url);
          this.settingsOpen = false;
          this.scheduleLaunchpadReload();
        }},
        toggleSharing(event) {{
          const isNowEnabled = event.target.checked;
          const url = isNowEnabled ? this.settingsLinks.enable : this.settingsLinks.disable;
          this.telemetry.enabled = isNowEnabled;
          this.triggerSettingsAction(url);
        }},
        toggleAutoIngest(event) {{
          const isNowEnabled = event.target.checked;
          const url = isNowEnabled ? this.settingsLinks.autoIngestEnable : this.settingsLinks.autoIngestDisable;
          this.telemetry.autoIngest = isNowEnabled;
          this.telemetry.daemonRunning = isNowEnabled;
          this.telemetry.daemonMessage = 'Updating watcher daemon…';
          this.triggerSettingsAction(url);
        }},
        resetAnonymousId() {{
          this.triggerSettingsAction(
            this.settingsLinks.reset,
            () => {{
              this.telemetry.shareInstallId = 'resetting…';
            }},
          );
        }},
        openLiveReview() {{
          if (!this.operation) {{
            return;
          }}
          window.location.href = this.liveReviewUrlFor(this.operation);
        }},
        dismissOperation() {{
          this.launchError = '';
          this.clearOperation();
        }},
        stopCurrentCouncil() {{
          if (!this.operation?.statusToken || this.operation.kind !== 'council' || !this.busy) {{
            return;
          }}
          const payload = {{
            name: 'stop_council',
            args: {{
              status_token: this.operation.statusToken,
            }},
            metadata: {{
              kind: 'stop_council',
              source: 'launchpad',
            }},
          }};
          this.triggerShortcut(buildShortcutUrl(payload));
        }},
        openSuggestions() {{
          this.suggestionsOpen = true;
        }},
        closeSuggestionsSoon() {{
          window.setTimeout(() => {{
            this.suggestionsOpen = false;
          }}, 120);
        }},
        handlePromptInput() {{
          this.suggestionsOpen = true;
        }},
        applySuggestion(suggestion) {{
          this.prompt = suggestion;
          this.suggestionsOpen = false;
        }},
        beginOperation(operation) {{
          this.operation = normalizeOperation({{
            ...operation,
            status: 'running',
            members: Object.fromEntries((operation.memberOrder || []).map((provider) => [provider, {{ status: 'pending' }}])),
            synthesis: {{ status: 'pending' }},
          }});
          this.launchError = '';
          this.suggestionsOpen = false;
          this.startOperationPolling(operation.statusToken);
        }},
        stopOperationPolling() {{
          if (this.statusPollHandle) {{
            clearInterval(this.statusPollHandle);
            this.statusPollHandle = null;
          }}
          if (this.statusRotateHandle) {{
            clearInterval(this.statusRotateHandle);
            this.statusRotateHandle = null;
          }}
        }},
        clearOperation() {{
          this.operation = null;
          this.stopOperationPolling();
        }},
        startOperationPolling(token) {{
          this.stopOperationPolling();
          this.currentStatusIndex = 0;
          this.statusRotateHandle = window.setInterval(() => {{
            this.currentStatusIndex++;
          }}, 2500);
          const check = () => {{
            loadStatusScript(token, (status) => {{
              if (!status) return;
              if (!this.operation) {{
                return;
              }}
              if (status.status === 'running') {{
                this.operation = normalizeOperation(status, this.operation);
                return;
              }}
              if (status.status === 'failed') {{
                this.launchError = status.error || 'Council failed.';
                this.operation = normalizeOperation({{ ...status, status: 'failed', error: this.launchError }}, this.operation);
                this.stopOperationPolling();
                return;
              }}
              if (status.status === 'canceled') {{
                this.launchError = status.error || 'Council stopped.';
                this.operation = normalizeOperation({{ ...status, status: 'canceled', error: this.launchError }}, this.operation);
                this.stopOperationPolling();
                return;
              }}
              if (status.status === 'completed') {{
                this.clearOperation();
                window.location.reload();
              }}
            }});
          }};
          check();
          this.statusPollHandle = window.setInterval(check, 1500);
        }},
        launchCouncil() {{
          if (this.busy) {{
            return;
          }}
          const prompt = this.prompt.trim();
          if (!prompt) {{
            window.alert('Please enter a task first.');
            return;
          }}
          const statusToken = `launch_${{Date.now().toString(36)}}_${{Math.random().toString(36).slice(2, 8)}}`;
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
          this.beginOperation({{
            kind: 'council',
            statusToken,
            label: prompt,
            memberOrder: [...pageData.defaultMembers],
          }});
          this.triggerShortcut(buildShortcutUrl(payload));
          window.setTimeout(() => {{
            window.location.href = this.liveReviewUrlFor(this.operation);
          }}, 120);
        }},
        ingestOnce() {{
          if (this.busy) {{
            return;
          }}
          const statusToken = `ingest_${{Date.now().toString(36)}}_${{Math.random().toString(36).slice(2, 8)}}`;
          const command = `trinity-local watch-once --notify --status-token ${{statusToken}}`;
          const payload = {{
            name: 'run_command',
            args: {{
              command,
            }},
            metadata: {{
              kind: 'launchpad_ingest_once',
              source: 'launchpad',
            }},
          }};
          this.beginOperation({{
            kind: 'ingest',
            statusToken,
            label: 'Scan recent transcripts once',
          }});
          this.settingsOpen = false;
          this.triggerShortcut(buildShortcutUrl(payload));
        }},
      }};
    }}

    createApp({{ LaunchpadApp, pageData }}).mount();
    maybeSendTelemetry();
    renderChart();
  </script>
{footer}"""
