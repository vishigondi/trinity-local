from __future__ import annotations

import json

from .design_system import render_html_footer, render_html_head
from .launchpad_runtime import launchpad_runtime_js

PETITE_VUE_MODULE = "./vendor/petite-vue.es.js"
CHART_JS_SRC = "./vendor/chart.umd.min.js"


def render_launchpad_html(*, page_data: dict, recent_cards: str, title: str = "Trinity · Your taste, ported") -> str:
    extra_head = f"""
  <script src="{CHART_JS_SRC}"></script>
"""
    head = render_html_head(title, extra_head=extra_head)
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
      min-height: 84px;
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

    .suggestion-text {{
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .suggestion-thread {{
      display: -webkit-box;
      -webkit-line-clamp: 1;
      -webkit-box-orient: vertical;
      overflow: hidden;
      margin-top: 4px;
      font-size: 12px;
      color: var(--text-secondary);
    }}

    .suggestion-thread-label {{
      font-weight: 600;
      margin-right: 6px;
    }}

    .suggestion-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 6px;
      align-items: center;
    }}

    .suggestion-chip {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: rgba(37, 88, 71, 0.08);
      color: var(--action);
      border: 1px solid rgba(37, 88, 71, 0.18);
    }}

    /* Cross-memory chip — shared base for the small bordered pill links
       that surface across the cortex card (→ topology), the lens card
       (basin ids), and the recent council card (→ pick / → routing /
       → topology). Three surfaces, one visual: bumping the look here
       updates all three. Specific contexts add their overrides via the
       modifier classes below. */
    .cross-memory-chip {{
      font-size: 10px;
      color: var(--text-secondary);
      text-decoration: none;
      padding: 1px 6px;
      border: 1px solid var(--border);
      border-radius: 3px;
      background: var(--surface);
      vertical-align: middle;
      white-space: nowrap;
      transition: background 0.12s ease, color 0.12s ease;
    }}
    .cross-memory-chip:hover {{
      color: var(--action);
      background: rgba(37, 88, 71, 0.06);
    }}
    /* Label variant — uppercase short text like "→ topology". Used by
       the cortex card and recent-card xlinks. */
    .cross-memory-chip--label {{
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    /* Id variant — monospace short id like "b03". Used by lens basins. */
    .cross-memory-chip--id {{
      font-family: ui-monospace, monospace;
    }}
    /* Inline next to a row's primary anchor (cortex card basin link). */
    .cross-memory-chip--inline {{
      margin-left: 8px;
    }}
    /* Pill variant — slightly larger + rounder. Used by the recent
       council card row of chips below the title. */
    .cross-memory-chip--pill {{
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
    }}

    /* Tick #79: ↻ Rebuild chip shared by the lens-rebuild (tick #76)
       and cortex-rebuild (tick #77) eyebrow chips on the launchpad.
       Inline styles drifted to ~200-char copies on each chip; one
       class + .lp-rebuild-chip references keeps them in sync. The
       memory viewer's .viewer-rebuild-chip is a sibling visual (see
       memory_viewer.py) — both render the same '↻ Rebuild' copy
       (unified in tick #79) but live in different CSS contexts. */
    .lp-rebuild-chip {{
      font-family: ui-monospace, monospace;
      font-size: 11px;
      color: var(--text-secondary, #6e6058);
      background: transparent;
      border: 1px solid var(--border, #d7ccb9);
      border-radius: 999px;
      padding: 2px 10px;
      cursor: pointer;
      white-space: nowrap;
      font-weight: 400;
      text-transform: none;
      letter-spacing: 0;
      opacity: 0.9;
    }}

    .suggestion-winner {{
      font-size: 12px;
      color: var(--text-muted);
      margin-left: auto;
    }}

    /* "Your taste, distilled" — magazine-style profile card with one share. */
    .taste-card .taste-block {{
      margin-top: 22px;
    }}
    .taste-block-label {{
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(37, 88, 71, 0.7);
      font-weight: 600;
      margin-bottom: 10px;
    }}
    .taste-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }}
    .taste-list li {{
      padding: 12px 14px;
      background: rgba(37, 88, 71, 0.04);
      border-left: 3px solid rgba(37, 88, 71, 0.35);
      border-radius: 0 8px 8px 0;
      line-height: 1.5;
    }}
    .taste-list-title {{
      display: block;
      font-weight: 600;
      color: #1a1a1a;
      font-size: 15px;
      margin-bottom: 2px;
    }}
    .taste-list-why {{
      display: block;
      font-size: 14px;
      color: #444;
    }}
    .taste-failure-modes {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      margin-top: 4px;
    }}
    .taste-failure-line {{
      font-size: 13px;
      color: #444;
    }}
    .taste-list-quotes li {{
      font-size: 15px;
      color: #1a1a1a;
      font-style: italic;
      border-left-color: rgba(107, 63, 160, 0.4);
      background: rgba(107, 63, 160, 0.04);
    }}
    .taste-vocab {{
      margin-top: 22px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: #555;
    }}
    .taste-vocab-label {{
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: rgba(37, 88, 71, 0.7);
      font-weight: 600;
      margin-right: 4px;
    }}
    .taste-vocab-chip {{
      padding: 3px 10px;
      background: var(--surface-muted);
      border: 1px solid var(--border);
      border-radius: 999px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 12px;
      color: #333;
    }}
    .taste-share-row {{
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      margin-top: 26px;
      padding-top: 18px;
      border-top: 1px solid var(--border);
    }}
    .taste-share-btn {{
      flex-shrink: 0;
    }}
    .taste-share-meta {{
      flex: 1;
      min-width: 240px;
      font-size: 12px;
      line-height: 1.45;
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

    .routing-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-top: 12px;
    }}

    .routing-table thead {{
      background: var(--surface-muted);
      border-bottom: 1px solid var(--border);
    }}

    .routing-table th {{
      padding: 12px;
      text-align: left;
      font-weight: 600;
      color: var(--text-primary);
    }}

    .routing-table td {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
    }}

    .routing-table tbody tr:hover {{
      background: var(--surface-muted);
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

    /* Recent-councils filter — pill chips + search.
       Matches the launchpad's existing chip aesthetic (see
       .cross-memory-chip) so the filter row reads as part of the
       same UI family as the in-card cross-memory chips. */
    .recent-filter-chip {{
      padding: 6px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--surface);
      color: var(--text-secondary);
      font-family: inherit;
      font-size: 13px;
      cursor: pointer;
      transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }}
    .recent-filter-chip:hover {{
      border-color: var(--action);
      color: var(--text-primary);
    }}
    .recent-filter-chip.active {{
      background: var(--accent, #b57438);
      border-color: var(--accent, #b57438);
      color: #fff;
    }}
    #recent-filter-search:focus {{
      outline: none;
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.12);
    }}
  </style>

  <main>
    <div class="launchpad-shell" id="launchpad-app" v-scope="LaunchpadApp(pageData)" @vue:mounted="init">
      <section class="card hero-shell">
        <div>
          <div class="eyebrow">Trinity</div>
          <h1>{{{{ heroTitle }}}}</h1>
          <p class="lede">{{{{ heroLede }}}}</p>
          <p class="meta hero-mechanism" v-if="heroMechanism">{{{{ heroMechanism }}}}</p>
        </div>
        <button type="button" @click="settingsOpen = !settingsOpen" style="background: none; border: none; cursor: pointer; padding: 8px; opacity: 0.7; flex-shrink: 0;" title="Settings" aria-label="Open settings">
          <span aria-hidden="true" style="font-size: 24px; line-height: 1;">⚙</span>
        </button>
      </section>

      <section class="settings-modal" v-if="settingsOpen" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;">
        <div class="card" style="max-width: 460px; margin: 20px; position: relative;">
          <button @click="settingsOpen = false" style="position: absolute; top: 16px; right: 16px; background: none; border: none; cursor: pointer; font-size: 24px; opacity: 0.6; transition: opacity 0.2s;" aria-label="Close settings">×</button>
          <div class="eyebrow">Settings</div>
          <h2>Launchpad controls</h2>
          <p class="meta">Telemetry is opt-in. Trinity can share anonymous Launchpad views and routing labels (provider scores by task type, winner, confidence) — never raw prompts, outputs, code, or file paths.</p>
          <p class="meta" style="margin-top: 8px; padding: 10px 12px; background: rgba(37, 88, 71, 0.06); border-left: 3px solid rgba(37, 88, 71, 0.4); border-radius: 0 6px 6px 0; font-size: 13px;">
            <b>Catch more issues like the bugs you've hit by enabling sharing.</b>
            Anonymous usage events let Trinity surface broken flows (silent dispatches, stale tabs, missing prompts) across users — issues a single install can't see on its own.
          </p>

          <div class="settings-list">
            <div class="setting-row">
              <span class="meta">Endpoint</span>
              <span class="meta">{{{{ displayedEndpoint }}}}</span>
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
              <span class="meta">Ingest transcripts</span>
              <div class="setting-value">
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
          </div>

          <div class="sharing-toggle">
            <span class="meta">Sharing enabled</span>
            <label class="toggle-switch">
              <input type="checkbox" :checked="telemetry.enabled" @change="toggleSharing">
              <span class="toggle-slider"></span>
            </label>
          </div>

          <!-- Auto-chain + polish-auto-iterate toggles retired 2026-05-17.
               Users click the auto-chain button on the council review page
               when they want sequential refinement; no global setting. -->

          <section class="provider-health-list" v-if="providerHealth.hasMissing">
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
                  @click="copyText(provider.installCommand, 'install-' + provider.provider)"
                  title="Copy install command"
                  aria-label="Copy install command"
                >
                  <!-- Tick #82: pass a flash key so the icon swaps to ✓
                       on click. Same shape as the rebuild chips (#76,
                       #77, #79) — gives the user confirmation the copy
                       actually landed. Without this the button stays
                       ⧉ forever and the click feels unobservable. -->
                  <span v-if="copiedKey === 'install-' + provider.provider">✓</span>
                  <span v-else>⧉</span>
                </button>
              </div>
            </div>
            <p class="meta" v-if="providerHealth.hasMissing">{{{{ providerHealth.footerNote }}}}</p>
          </section>
        </div>
      </section>

      <!-- Handoff demo nudge — info-style banner that surfaces the
           60-second cross-provider continuity demo when conditions
           are met (≥2 providers + ≥1 indexed prompt). Mirrors the
           CLI status 'try this next' hint. Silent when the install
           can't actually run the demo yet. Tick post-#115. -->
      <section
        class="card"
        v-if="pageData.handoffNudge && pageData.handoffNudge.applicable"
        style="border-left: 3px solid #3b6bd6; background: rgba(59, 107, 214, 0.04);"
      >
        <div class="eyebrow" style="color: #3b6bd6;">Try the 60-second demo</div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          Hand off a conversation across models — no copy-paste
        </h2>
        <p class="meta" style="margin-top: 8px;">
          Have a conversation in Claude Code, then run
          <code>trinity-local handoff {{{{ pageData.handoffNudge.target }}}}</code>
          in a terminal. {{{{ pageData.handoffNudge.target }}}} will pick up exactly where Claude left off —
          using your {{{{ pageData.handoffNudge.source_count > 5 ? pageData.handoffNudge.source_count + '+' : pageData.handoffNudge.source_count }}}}
          indexed prompts as the cross-provider context bridge.
        </p>
        <p class="meta" style="margin-top: 8px;">
          The wedge: no provider can build this — Anthropic can't read OpenAI's transcripts.
          Only the layer above the labs can do continuity across them.
        </p>
      </section>

      <!-- Phase 4 dispatch banner — single global banner that opens
           when a click hits tier 3 (no extension + no Shortcut) or when
           the extension is present but install-extension wasn't run.
           Dismissible; a failed click reopens it. Bias toward the
           extension path in copy (per launch-arc workstream #1: the
           extension is the future, Shortcuts is the legacy). -->
      <section
        class="card memory-health-card"
        v-if="dispatchBannerOpen"
        style="border-left: 3px solid #b57438; background: rgba(181, 116, 56, 0.06);"
      >
        <div class="eyebrow" style="color: #b57438;">
          <span v-if="dispatchBannerReason === 'native-host-unavailable'">Extension installed, host not registered</span>
          <span v-else>No dispatch path is wired up</span>
        </div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          <span v-if="dispatchBannerReason === 'native-host-unavailable'">
            Trinity reached the extension but the native host wasn't found
          </span>
          <span v-else>
            Install the Trinity browser extension to dispatch from any platform
          </span>
        </h2>
        <p class="meta" style="margin-top: 8px;" v-if="dispatchBannerReason === 'native-host-unavailable'">
          The Chrome extension is loaded and responding, but the local helper
          (<code>trinity-local-capture-host</code>) isn't registered. Run:
          <code>trinity-local install-extension --extension-id &lt;ID&gt;</code>
          and reload the launchpad.
        </p>
        <p class="meta" style="margin-top: 8px;" v-else>
          1. Open <code>chrome://extensions</code> in Chrome, enable Developer mode,
          and load the <code>browser-extension/</code> folder.<br>
          2. Copy the 32-character ID Chrome assigns.<br>
          3. Run <code>trinity-local install-extension --extension-id &lt;ID&gt;</code>.
        </p>
        <p class="meta" style="margin-top: 8px;">
          <a href="#" @click.prevent="dismissDispatchBanner">Dismiss</a>
          — a failed click reopens this.
        </p>
      </section>

      <!-- Memory health — only renders when something is stale. Silent
           on a fresh install. Maps directly to the four signals built
           into pageData.memoryHealth.issues. -->
      <section class="card memory-health-card" v-if="memoryHealth && memoryHealth.issues && memoryHealth.issues.length">
        <div class="eyebrow">Memory health</div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          {{{{ memoryHealth.issues.length }}}} memor{{{{ memoryHealth.issues.length === 1 ? 'y' : 'ies' }}}} need{{{{ memoryHealth.issues.length === 1 ? 's' : '' }}}} attention
          <span class="meta" style="font-weight: 400; font-size: 13px; margin-left: 8px;">·
            {{{{ memoryHealth.ok_count }}}} of {{{{ memoryHealth.total_count }}}} healthy
          </span>
        </h2>
        <ul class="memory-health-list" style="list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 6px;">
          <li v-for="issue in memoryHealth.issues" :key="issue.name + issue.status"
              style="display: flex; align-items: baseline; gap: 10px; padding: 8px 12px; background: rgba(178, 106, 31, 0.06); border-left: 3px solid var(--warning, #b26a1f); border-radius: 0 6px 6px 0; font-size: 13px; flex-wrap: wrap;">
            <code style="font-size: 12px; color: var(--accent, #b57438); white-space: nowrap;">{{{{ issue.name }}}}</code>
            <span class="meta" style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.7;">{{{{ issue.status }}}}</span>
            <span style="color: var(--text-primary, #1f1a17); flex: 1; min-width: 200px;">{{{{ issue.hint }}}}</span>
            <!-- click-to-copy command chip — wraps the existing copyText
                 helper so the user can paste-and-run with one click
                 instead of highlight-copy-paste. Per the action-from-view
                 forward arc: the viewer surfaces drift; the chip closes
                 the loop. -->
            <button v-if="issue.command"
                    type="button"
                    @click="copyHealthCommand(issue)"
                    :title="'Copy: ' + issue.command"
                    style="font-family: ui-monospace, monospace; font-size: 12px; color: var(--text-primary, #1f1a17); background: var(--bg-base, #f5efe3); border: 1px solid var(--border, #d7ccb9); border-radius: 4px; padding: 4px 10px; cursor: pointer; white-space: nowrap;">
              <span v-if="copiedKey === 'health-' + issue.name + issue.status">✓ Copied</span>
              <span v-else>{{{{ issue.command }}}}</span>
            </button>
            <a v-if="issue.href"
               :href="issue.href"
               style="font-size: 12px; color: var(--accent, #b57438); text-decoration: none; padding: 4px 10px; border: 1px solid var(--border, #d7ccb9); border-radius: 4px; white-space: nowrap;">
              Inspect →
            </a>
          </li>
        </ul>
      </section>

      <section class="launch-grid">
        <article class="card">
          <div class="eyebrow">Council</div>
          <h2>Ask every model at once</h2>
          <p class="meta">Every model you use — frontier and local — answers in parallel. A local chairman synthesizes — agreed claims, disagreed claims with <em>why_matters</em>, picked winner. You override; that click trains the local router.</p>
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
            >
              <div class="suggestion-text">{{{{ suggestionText(suggestion) }}}}</div>
              <div class="suggestion-thread" v-if="suggestionPriorPreview(suggestion)">
                <span class="suggestion-thread-label">Prior thread:</span>
                <span class="suggestion-thread-text">{{{{ suggestionPriorPreview(suggestion) }}}}</span>
              </div>
              <div class="suggestion-meta" v-if="suggestionWinner(suggestion)">
                <span class="suggestion-winner">Winner: {{{{ suggestionWinner(suggestion) }}}}</span>
              </div>
            </button>
          </div>

          <p class="meta" v-if="polishHintVisible" style="background: rgba(99, 102, 241, 0.08); border-left: 3px solid #6366f1; padding: 8px 12px; margin-top: 12px; border-radius: 4px;">
            💡 Polish task detected. Click "Auto-chain" on the council page to iterate up to 3 rounds toward convergence.
          </p>

          <div class="actions" style="margin-top: 18px;">
            <button type="button" class="button primary" @click="launchCouncil" :disabled="busy">Launch Council</button>
          </div>
          <p class="meta" style="margin-top: 12px; font-size: 13px; opacity: 0.7;">
            Or drive Trinity from inside Claude Code: type <code>/trinity</code> after running <code>trinity-local install-mcp</code>. Same chairman, no tab switch.
          </p>

              <section class="launch-status" v-if="operation || launchError">
                <div class="spinner-row" v-if="busy">
                  <span class="spinner" aria-hidden="true"></span>
                  <strong class="status-message">{{{{ operationHeading }}}}</strong>
                </div>
                <strong v-if="operation && !busy">{{{{ operationHeading }}}}</strong>
                <p class="meta" v-if="operation && operation.label">{{{{ operation.label }}}}</p>
                <p class="status-message" v-if="busy">{{{{ currentStatusMessage }}}}</p>
                <div class="provider-status-list" v-if="showProviderRows">
                  <div class="provider-status-row" v-for="row in providerStatusRows">
                    <div class="provider-status-name">{{{{ row.label }}}}</div>
                    <div class="provider-status-badge" :class="row.statusClass">{{{{ row.statusLabel }}}}</div>
                    <div class="provider-status-detail" :class="{{ empty: !row.detail }}">{{{{ row.detail || '' }}}}</div>
                  </div>
                </div>
                <p class="status-error" v-if="launchError || operation?.error">{{{{ launchError || operation?.error }}}}</p>
                <div class="launch-status-actions" v-if="operation">
                  <a class="button ghost" v-if="operation.kind === 'council' && busy" :href="liveCouncilUrl">Open council page</a>
                  <button type="button" class="button ghost" v-if="operation.kind === 'council' && busy" @click="stopCurrentCouncil">Stop council</button>
                  <button type="button" class="button ghost" v-if="!busy" @click="dismissOperation">Dismiss</button>
                </div>
              </section>
        </article>
      </section>

      <section class="card" v-if="cortexRules && cortexRules.rules.length">
        <div class="eyebrow" style="display: flex; align-items: center; gap: 8px;">
          <span>What Trinity has learned about you</span>
          <!-- Rebuild chip — same shape as the lens-rebuild chip from
               tick #76 (forward-arc action-from-view). Re-running
               consolidate is what makes new councils produce new rules;
               without an in-page affordance the user had to remember
               the command or scroll to the explanatory paragraph
               below. -->
          <button type="button"
                  class="lp-rebuild-chip"
                  @click.stop="copyText('trinity-local consolidate', 'cortex-rebuild')"
                  title="Copy: trinity-local consolidate">
            <span v-if="copiedKey === 'cortex-rebuild'">✓ Copied</span>
            <span v-else>↻ Rebuild</span>
          </button>
        </div>
        <h2>Routing patterns extracted from your councils</h2>
        <p class="meta">
          The cortex layer reads {{{{ cortexRules.total_basins }}}} basin{{{{ cortexRules.total_basins === 1 ? '' : 's' }}}} of council outcomes and extracts one routing rule per kind of question. Trust score is computed from sample size, agreement consistency, recency, and basin diversity — it gates when the rule drives `ask` instead of the kNN fallback.
        </p>
        <table class="routing-table cortex-rules-table" style="margin-top: 16px;">
          <thead>
            <tr>
              <th style="text-align: left;">Kind of question</th>
              <th>Primary</th>
              <th>Challenger</th>
              <th>Trust</th>
              <th>Health</th>
              <th style="text-align: left;">Why</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in cortexRules.rules">
              <td style="font-weight: 500;">
                <!-- Cross-memory deep-link: basin_id → memory.html with
                     this basin focused. Memory viewer's picks Reader
                     surfaces failure_modes + the routing-scores xlink
                     this table doesn't show. Plain-text fallback when
                     no basin_id (defensive — shouldn't happen). -->
                <a v-if="r.basin_id"
                   :href="'../portal_pages/memory.html?file=picks.json&task=' + encodeURIComponent(r.basin_id)"
                   style="color: inherit; text-decoration: none; border-bottom: 1px dotted var(--text-muted);"
                   :title="'View ' + r.basin_id + ' in memory viewer'">
                  {{{{ r.basin_id.replace(/_/g, ' ') }}}}
                </a>
                <span v-else>{{{{ r.basin_id.replace(/_/g, ' ') }}}}</span>
                <!-- → topology chip: only renders when the rule's basin
                     centroid has a match into topics.json. Visually quiet
                     so the primary basin_id link stays dominant. Same
                     shape as the routing-table topology chip (tick #33). -->
                <a v-if="r.topology_basin"
                   :href="'../portal_pages/memory.html?file=topics.json&basin=' + encodeURIComponent(r.topology_basin)"
                   class="cortex-topology-chip cross-memory-chip cross-memory-chip--label cross-memory-chip--inline"
                   :title="basinHoverLabel(r.topology_basin)">
                  → topology
                </a>
              </td>
              <td><span class="suggestion-chip">{{{{ formatProviderLabel(r.primary) }}}}</span></td>
              <td><span class="meta">{{{{ r.challenger ? formatProviderLabel(r.challenger) : '—' }}}}</span></td>
              <td>
                <strong>{{{{ r.trust_score.toFixed(2) }}}}</strong>
                <span class="meta" style="display: block; font-size: 11px;">{{{{ r.trust_band }}}}</span>
              </td>
              <td>
                <span class="meta" v-if="ruleHealthLabel(r)" :title="ruleHealthTitle(r)">{{{{ ruleHealthLabel(r) }}}}</span>
                <span class="meta" v-if="!ruleHealthLabel(r)">—</span>
              </td>
              <td class="meta" style="font-size: 13px;">
                {{{{ r.reason || '—' }}}}
                <div v-if="r.evidence && r.evidence.length" style="margin-top: 6px;">
                  <span class="meta" style="font-size: 11px; opacity: 0.7;">
                    From {{{{ r.n_episodes }}}} councils, view:
                  </span>
                  <a v-for="cid in r.evidence"
                     :key="cid"
                     :href="evidenceUrl(cid)"
                     class="suggestion-chip"
                     style="font-size: 11px; margin-left: 4px; text-decoration: none;"
                     :title="'Open council ' + cid">
                    {{{{ cid.replace('council_', '').slice(0, 8) }}}}
                  </a>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="meta" style="margin-top: 12px; font-size: 13px; opacity: 0.7;">
          High trust ({{{{ cortexRules.trust_use_rule }}}}+) → the rule drives routing. Medium ({{{{ cortexRules.trust_knn_fallback }}}}–{{{{ cortexRules.trust_use_rule }}}}) → rule + kNN fallback. Below {{{{ cortexRules.trust_knn_fallback }}}} → kNN only. Rebuild with <code>trinity-local consolidate</code>; add <code>--audit</code> to flag drift via an independent chairman.
        </p>
        <p class="meta" style="margin-top: 6px; font-size: 13px; opacity: 0.7;">
          Disagree with a rule? Ask Claude to call <code>mark_pick_wrong(basin_id="...")</code> via MCP, or run <code>trinity-local cortex-override --basin &lt;id&gt;</code>. Each click halves effective trust; persists across consolidations.
        </p>
      </section>

      <section class="card" v-if="!cortexRules">
        <div class="eyebrow">What Trinity will learn about you</div>
        <h2>Run <code>trinity-local consolidate</code> after a few councils</h2>
        <p class="meta">
          Once you've rated a handful of councils, the cortex layer extracts routing patterns from them: which provider wins for which kind of question, why, and the failure modes of the losers. Those rules then drive the next ask call — Trinity learns at two levels (hippocampus for episodes, cortex for patterns).
        </p>
      </section>

      <section class="card">
        <div class="eyebrow">Ratings</div>
        <h2>Which model wins for which kind of question</h2>
        <p class="meta" v-if="personalRoutingTable && personalRoutingTable.councils_aggregated">
          From your own {{{{ personalRoutingTable.councils_aggregated }}}} councils — the bars sharpen with every rating. Categories match LMArena so you can compare against public evals later.
        </p>
        <p class="meta" v-else>
          Once you run <code>trinity-local replay-history --limit 20</code>, this chart fills in with per-category strength for each provider, computed from your own council preferences.
        </p>

        <div class="chart-shell" v-if="personalRoutingTable && personalRoutingTable.councils_aggregated">
          <canvas id="personal-preference-chart"></canvas>
        </div>

        <p class="meta" style="margin-top: 12px;" v-if="personalRoutingTable && personalRoutingTable.councils_aggregated">
          <span v-for="provider in benchmarkProviders" style="margin-right: 14px;">
            <strong>{{{{ provider.toUpperCase() }}}}</strong>
            <span v-if="providerModels && providerModels[provider]"> · {{{{ providerModels[provider] }}}}</span>
          </span>
        </p>

        <details style="margin-top: 16px;" v-if="personalRoutingTable && personalRoutingTable.councils_aggregated">
          <summary class="meta" style="cursor: pointer;">Local Elo (raw)</summary>
          <div class="chart-shell" style="margin-top: 8px;">
            <canvas id="provider-elo-chart"></canvas>
          </div>
        </details>
      </section>

      <section class="card" v-if="personalRoutingTable">
        <div class="eyebrow">Routing</div>
        <h2>Best model per task type, from your own councils</h2>
        <p class="meta">
          Built from {{{{ personalRoutingTable.councils_aggregated || 0 }}}} councils. The chairman blends your data with global benchmarks — the personalization % below shows how much your data drives the pick today.
        </p>
        <p class="meta" v-if="coreStatus.state === 'stale'" style="background: rgba(245, 158, 11, 0.08); border-left: 3px solid #f59e0b; padding: 8px 12px; margin-top: 12px; border-radius: 4px;">
          ⚠️ Your <code>core.md</code> is stale — a memory file was updated since the last dream. Run <code>trinity-local dream</code> so the chairman reads the freshest synthesis on the next council.
        </p>
        <p class="meta" v-if="coreStatus.state === 'missing'" style="background: rgba(99, 102, 241, 0.08); border-left: 3px solid #6366f1; padding: 8px 12px; margin-top: 12px; border-radius: 4px;">
          💡 You have core memories but no distillation yet. Run <code>trinity-local dream</code> to produce <code>~/.trinity/core.md</code> — the one paragraph chairmen read first.
        </p>
        <table class="routing-table">
          <thead>
            <tr>
              <th>Task type</th>
              <th>Best</th>
              <th style="text-align: right;">Personalization</th>
              <th v-for="provider in routingTableProviders" style="text-align: right;">{{{{ provider.toUpperCase() }}}}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(scores, taskType) in personalRoutingTable.by_task_type">
              <td>
                <!-- Cross-memory link mirroring the cortex card from tick
                     #19. Personal routing table row → routing.json viewer
                     focused on this task_type. Memory viewer shows the
                     full provider × score matrix (this card only shows
                     the user's own data; the viewer also surfaces the
                     "↔ pick" xlink + computed_at timestamp). -->
                <a :href="'../portal_pages/memory.html?file=routing.json&task=' + encodeURIComponent(taskType)"
                   style="color: inherit; text-decoration: none; border-bottom: 1px dotted var(--text-muted);"
                   :title="'View ' + taskType + ' in routing.json viewer'">
                  <div class="benchmark-category">{{{{ taskType.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') }}}}</div>
                </a>
              </td>
              <td><span class="suggestion-chip">{{{{ formatProviderLabel(personalRoutingTable.best_per_task_type[taskType] || '') }}}}</span></td>
              <td style="text-align: right;">
                <span class="benchmark-score" v-if="coldStartFor(taskType)">{{{{ coldStartFor(taskType).personalization_pct }}}}%</span>
                <span class="benchmark-unit" v-if="coldStartFor(taskType)">n={{{{ coldStartFor(taskType).n_personal }}}}</span>
                <span class="benchmark-unit" v-if="!coldStartFor(taskType)">—</span>
              </td>
              <td v-for="provider in routingTableProviders" style="text-align: right;">
                <span class="benchmark-score" v-if="scores[provider]">{{{{ scores[provider].overall.toFixed(1) }}}}</span>
                <span class="benchmark-unit" v-if="!scores[provider]">—</span>
                <span class="benchmark-unit" v-if="scores[provider]">n={{{{ scores[provider].n }}}}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card" v-if="!personalRoutingTable">
        <div class="eyebrow">Routing</div>
        <h2>Run replay-history to learn which model works best for you</h2>
        <p class="meta">
          Trinity will re-run your highest-leverage past prompts against the current model lineup
          and show you per-task-type winners. One overnight run gives you a personal routing plan.
        </p>
        <pre class="md-code-block"><code>trinity-local replay-history --limit 20</code></pre>
      </section>

      <!-- Empirical benchmark — most-recent eval-run result rendered
           inline. When no runs have completed yet, renders an empty
           state with the right CTA depending on whether the eval set
           has been built. Surfaces the personalized-benchmark axis
           (workstream #116) where the user already lives, so the
           output of `trinity-local eval-run` isn't buried in JSON.
           Tick post-Surface 29 / task #122 / #116. -->
      <section class="card eval-summary-card" v-if="pageData.evalSummary && pageData.evalSummary.has_results">
        <div class="eyebrow">Personalized benchmark</div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          {{{{ pageData.evalSummary.target }}}}
          <span v-if="pageData.evalSummary.model" class="meta" style="font-weight: normal;">
            ({{{{ pageData.evalSummary.model }}}})
          </span>
          <span style="float: right; font-variant-numeric: tabular-nums;">
            <span v-if="pageData.evalSummary.aggregate_score !== null">
              {{{{ pageData.evalSummary.aggregate_score.toFixed(2) }}}}
            </span>
            <span v-else class="meta">— /1.00</span>
          </span>
        </h2>
        <p class="meta" style="margin-top: 4px;">
          scored against {{{{ pageData.evalSummary.items_completed }}}} of
          {{{{ pageData.evalSummary.items_total }}}} items from your rejection signal
          <span v-if="pageData.evalSummary.total_runs > 1"> · {{{{ pageData.evalSummary.total_runs }}}} runs on disk</span>
        </p>
        <ul style="list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 4px; font-variant-numeric: tabular-nums;">
          <li v-for="axis in pageData.evalSummary.axes" :key="axis.name"
              style="display: grid; grid-template-columns: 110px 50px 1fr 80px; gap: 8px; align-items: center; font-size: 13px;">
            <span>{{{{ axis.name }}}}</span>
            <span class="meta">n={{{{ axis.count }}}}</span>
            <span style="position: relative; height: 6px; background: rgba(0,0,0,0.06); border-radius: 3px;">
              <span :style="'position: absolute; left: 0; top: 0; bottom: 0; width: ' + (axis.mean * 100) + '%; background: #3b6bd6; border-radius: 3px;'"></span>
            </span>
            <span style="text-align: right;">{{{{ axis.mean.toFixed(2) }}}}</span>
          </li>
        </ul>
        <!-- Cross-provider comparison: when Trinity has benchmark data
             for ≥2 providers, surface the leaderboard side-by-side.
             A journalist screenshotting the launchpad sees the wedge
             ("Trinity scores models against YOUR rejections") only when
             multiple providers are visible. Single-target renders just
             the per-axis bars above; multi-target adds this leaderboard. -->
        <div v-if="pageData.evalSummary.comparison && pageData.evalSummary.comparison.length >= 2"
             style="margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(0,0,0,0.08);">
          <div class="eyebrow" style="font-size: 11px;">Cross-provider leaderboard · YOUR corpus</div>
          <ul style="list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-direction: column; gap: 4px; font-variant-numeric: tabular-nums;">
            <li v-for="(row, i) in pageData.evalSummary.comparison" :key="row.target"
                style="display: grid; grid-template-columns: 24px 80px 50px 1fr 70px 70px; gap: 8px; align-items: center; font-size: 13px;">
              <span class="meta" style="text-align: right;">{{{{ i + 1 }}}}.</span>
              <span style="font-weight: 600;">{{{{ row.target }}}}</span>
              <span class="meta">n={{{{ row.items_completed }}}}</span>
              <span style="position: relative; height: 6px; background: rgba(0,0,0,0.06); border-radius: 3px;">
                <span v-if="row.aggregate_score !== null"
                      :style="'position: absolute; left: 0; top: 0; bottom: 0; width: ' + (row.aggregate_score * 100) + '%; background: #2d8a3e; border-radius: 3px;'"></span>
              </span>
              <span style="text-align: right;">
                <span v-if="row.aggregate_score !== null">{{{{ row.aggregate_score.toFixed(3) }}}}</span>
                <span v-else class="meta">—</span>
              </span>
              <span class="meta" style="text-align: right;" v-if="row.judge">judge: {{{{ row.judge }}}}</span>
              <span class="meta" style="text-align: right;" v-else></span>
            </li>
          </ul>
          <p class="meta" style="margin-top: 8px; font-size: 12px;">
            Each row is the most-recent <code>eval-run</code> per target. Judges
            are rotated (a model never grades itself). The strongest score on
            YOUR rejections wins, not the global leaderboard.
          </p>
        </div>
        <p class="meta" style="margin-top: 12px;">
          <code>trinity-local eval-show</code> renders the same with top/bottom samples.
          Re-run anytime with <code>eval-run --target {{{{ pageData.evalSummary.target }}}}</code>.
        </p>
      </section>

      <!-- Rate-limit-saves: the Day-1 launch metric (docs/launch-package.md).
           "Trinity routed N work-units around rate limits in the last
           N days" is the case-study anchor for the post-Dreaming
           positioning. Surfaces only when there's data — saves are a
           side effect of using Trinity, not an action the user takes.
           Empty until first save fires; once present, this is the
           number the launch copy will quote. -->
      <section class="card rate-limit-saves-card"
               v-if="pageData.rateLimitSaves && pageData.rateLimitSaves.has_data"
               style="border-left: 3px solid #2d8a3e; background: rgba(45, 138, 62, 0.04);">
        <div class="eyebrow" style="color: #2d8a3e;">Rate-limit saves · last {{{{ pageData.rateLimitSaves.window_days }}}}d</div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          Work continued when Claude hit its limit
          <span style="float: right; font-variant-numeric: tabular-nums; color: #2d8a3e;">
            {{{{ pageData.rateLimitSaves.total_saves }}}}×
          </span>
        </h2>
        <p class="meta" style="margin-top: 4px;">
          {{{{ pageData.rateLimitSaves.total_saves }}}} of
          {{{{ pageData.rateLimitSaves.total_calls }}}} ask calls were routed around a
          rate-limited primary
          ({{{{ (pageData.rateLimitSaves.save_rate * 100).toFixed(1) }}}}% save rate)
        </p>
        <ul style="list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 4px; font-variant-numeric: tabular-nums; font-size: 13px;">
          <li v-for="row in pageData.rateLimitSaves.by_failure_kind" :key="row.kind"
              style="display: grid; grid-template-columns: 140px 60px 1fr; gap: 8px; align-items: center;">
            <span>{{{{ row.kind }}}}</span>
            <span class="meta">{{{{ row.count }}}}</span>
            <span style="position: relative; height: 6px; background: rgba(0,0,0,0.06); border-radius: 3px;">
              <span :style="'position: absolute; left: 0; top: 0; bottom: 0; width: ' + (row.count / pageData.rateLimitSaves.total_saves * 100) + '%; background: #2d8a3e; border-radius: 3px;'"></span>
            </span>
          </li>
        </ul>
        <p class="meta" style="margin-top: 12px;">
          The Day-1 case-study number. Raw events live in
          <code>~/.trinity/analytics/dispatch_outcomes.jsonl</code>; this
          card grows as you use Trinity through real rate-limit hits.
        </p>
      </section>

      <!-- Surface 33 (v1.6) — Browser capture activity. Shows per-
           provider counts + last-capture timestamp. Empty state has
           a CTA (install the extension); populated state surfaces
           silent-breakage signal when last capture > 24h ago. -->
      <section class="card browser-capture-card"
               v-if="pageData.browserCapture && pageData.browserCapture.has_data"
               :style="pageData.browserCapture.stale ? 'border-left: 3px solid #c4791f; background: rgba(196, 121, 31, 0.04);' : 'border-left: 3px solid #4a90e2; background: rgba(74, 144, 226, 0.04);'">
        <div class="eyebrow" :style="pageData.browserCapture.stale ? 'color: #c4791f;' : 'color: #4a90e2;'">
          Browser capture<span v-if="pageData.browserCapture.captured_24h > 0"> · last 24h</span>
        </div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          <span v-if="pageData.browserCapture.captured_24h > 0">
            {{{{ pageData.browserCapture.captured_24h }}}} conversation<span v-if="pageData.browserCapture.captured_24h !== 1">s</span> captured
          </span>
          <span v-else>
            {{{{ pageData.browserCapture.total_captured }}}} conversation<span v-if="pageData.browserCapture.total_captured !== 1">s</span> captured
            <span class="meta" style="font-weight: normal;">(none in last 24h)</span>
          </span>
          <span style="float: right; font-variant-numeric: tabular-nums;"
                :style="pageData.browserCapture.stale ? 'color: #c4791f;' : 'color: #4a90e2;'">
            {{{{ pageData.browserCapture.providers.length }}}} provider<span v-if="pageData.browserCapture.providers.length !== 1">s</span>
          </span>
        </h2>
        <ul style="list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 4px; font-variant-numeric: tabular-nums; font-size: 13px;">
          <li v-for="row in pageData.browserCapture.providers" :key="row.provider"
              style="display: grid; grid-template-columns: 140px 60px 1fr; gap: 8px; align-items: center;">
            <span>{{{{ row.provider }}}}</span>
            <span class="meta">{{{{ row.count }}}}</span>
            <span style="position: relative; height: 6px; background: rgba(0,0,0,0.06); border-radius: 3px;">
              <span :style="'position: absolute; left: 0; top: 0; bottom: 0; width: ' + (row.count / pageData.browserCapture.total_captured * 100) + '%; background: ' + (pageData.browserCapture.stale ? '#c4791f' : '#4a90e2') + '; border-radius: 3px;'"></span>
            </span>
          </li>
        </ul>
        <p class="meta" style="margin-top: 12px;" v-if="!pageData.browserCapture.stale">
          Last capture {{{{ pageData.browserCapture.last_capture_ago_human }}}} ago. Run
          <code>trinity-local ingest-recent</code> to pull new captures into the prompt index.
        </p>
        <p class="meta" style="margin-top: 12px; color: #c4791f;" v-else>
          ⚠ No new captures in the last 24h (last was {{{{ pageData.browserCapture.last_capture_ago_human }}}} ago).
          Check the service-worker console at <code>chrome://extensions</code> — the extension may have been
          disabled or the provider may have refactored their API. Details in
          <code>browser-extension/README.md</code>.
        </p>
      </section>

      <section class="card browser-capture-card"
               v-if="pageData.browserCapture && !pageData.browserCapture.has_data"
               style="border-left: 3px dashed rgba(74, 144, 226, 0.4); background: rgba(74, 144, 226, 0.02);">
        <div class="eyebrow" style="color: #4a90e2;">Browser capture</div>
        <h2 style="margin-top: 4px; font-size: 18px;">
          Capture every Claude / ChatGPT conversation automatically
        </h2>
        <p class="meta" style="margin-top: 4px;">
          Trinity reads transcripts already on your machine — for the chat web UIs that means
          installing the v1.6 browser extension. One-time, no server, no daemon. Every message
          you send on claude.ai or chatgpt.com lands in <code>~/.trinity/conversations/</code>
          and flows into your cortex / lens / picks.
        </p>
        <pre class="md-code-block"><code>{{{{ pageData.browserCapture.install_command }}}}</code></pre>
        <p class="meta" style="margin-top: 8px;">
          Full ritual in <code>browser-extension/README.md</code>.
        </p>
      </section>

      <section class="card taste-card" v-if="tasteLenses">
        <div class="eyebrow" style="display: flex; align-items: center; gap: 8px;">
          <span>Your taste, distilled</span>
          <!-- Rebuild chip — closes the forward-arc gap "See a rejected
               lens → rebuild lens.md link" (tick #76). Click copies the
               command so the user can paste-and-run instead of typing
               from memory. Only renders when lens already exists; the
               empty-state card below still shows the bare command. -->
          <button v-if="tasteLenses"
                  type="button"
                  class="lp-rebuild-chip"
                  @click.stop="copyText('trinity-local lens-build', 'lens-rebuild')"
                  title="Copy: trinity-local lens-build">
            <span v-if="copiedKey === 'lens-rebuild'">✓ Copied</span>
            <span v-else>↻ Rebuild</span>
          </button>
        </div>
        <h2>The patterns in how you think</h2>
        <p class="meta">
          Trinity surfaced the tensions your decisions encode (lenses) and
          the principles you redirect away from. Refreshes when lens-build runs.
        </p>

        <div class="taste-block" v-if="tasteLenses.paired_lenses && tasteLenses.paired_lenses.length">
          <div class="taste-block-label">{{{{ tasteLenses.paired_lenses.length === 1 ? 'Paired lens (the tension you live in)' : 'Paired lenses (the tensions you live in)' }}}}</div>
          <ol class="taste-list">
            <li v-for="(p, idx) in tasteLenses.paired_lenses" :key="'pair-' + idx">
              <span class="taste-list-title">{{{{ p.pole_a }}}} ↔ {{{{ p.pole_b }}}}</span>
              <span class="taste-list-why taste-failure-modes" v-if="p.failure_a || p.failure_b">
                <span class="taste-failure-line">pure-{{{{ p.pole_a }}}} fails as <b>{{{{ p.failure_a || '?' }}}}</b></span>
                <span class="taste-failure-line">pure-{{{{ p.pole_b }}}} fails as <b>{{{{ p.failure_b || '?' }}}}</b></span>
              </span>
              <!-- Spans-basins chips: each basin id deep-links to the
                   topology view focused on that basin (tick #36). Closes
                   the forward-arc gap "lens card → source prompts" by
                   linking the tension to the basins it lives across. -->
              <span class="lens-basins-row" v-if="p.basins_spanned && p.basins_spanned.length"
                style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px;">
                <span class="meta" style="font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase; opacity: 0.7;">Spans</span>
                <a v-for="bid in p.basins_spanned" :key="'lb-' + idx + '-' + bid"
                   class="lens-basin-chip cross-memory-chip cross-memory-chip--id"
                   :href="'../portal_pages/memory.html?file=topics.json&basin=' + encodeURIComponent(bid)"
                   :title="basinHoverLabel(bid)">
                  {{{{ bid }}}}
                </a>
              </span>
            </li>
          </ol>
        </div>

        <div class="taste-block" v-if="tasteLenses.orderings && tasteLenses.orderings.length">
          <div class="taste-block-label">Orderings (preferences without dual evidence)</div>
          <ul class="taste-list">
            <li v-for="(o, idx) in tasteLenses.orderings" :key="'ord-' + idx">
              <span class="taste-list-title">{{{{ o.pole_a }}}} &gt; {{{{ o.pole_b }}}}</span>
            </li>
          </ul>
        </div>

        <div class="taste-block" v-if="tasteLenses.rejections && tasteLenses.rejections.length">
          <div class="taste-block-label">What you redirect away from</div>
          <ol class="taste-list">
            <li v-for="(lens, idx) in tasteLenses.rejections" :key="'rej-' + idx">
              <span class="taste-list-title">{{{{ lens.title }}}}</span>
              <span class="taste-list-why">{{{{ lens.why_matters }}}}</span>
            </li>
          </ol>
        </div>

        <div class="taste-block" v-if="tasteLenses.abstract_lenses.length">
          <div class="taste-block-label">The lenses you think through</div>
          <ul class="taste-list taste-list-quotes">
            <li v-for="(l, idx) in tasteLenses.abstract_lenses" :key="'lens-' + idx">{{{{ l.statement }}}}</li>
          </ul>
        </div>

        <div class="taste-vocab" v-if="tasteLenses.vocabulary.length">
          <span class="taste-vocab-label">Phrases you keep using:</span>
          <span v-for="(v, idx) in tasteLenses.vocabulary" :key="'voc-' + idx" class="taste-vocab-chip">"{{{{ v.phrase }}}}"</span>
        </div>

        <div class="taste-share-row">
          <button class="button primary taste-share-btn" @click="copyLens(tasteLenses.combined_share_text, 'taste-share')">
            <span v-if="copiedKey === 'taste-share'">✓ Copied — paste anywhere</span>
            <span v-else>Copy as text</span>
          </button>
          <button class="button ghost taste-share-btn" @click="renderMeCard" :disabled="busy" style="margin-left: 8px;">
            <span v-if="copiedKey === 'me-card'">✓ Rendered — opening</span>
            <span v-else>Save as PNG card</span>
          </button>
          <!-- Cross-memory link: lens card preview → full lens.md viewer.
               The "Your lens" chip card below also links to the same place,
               but a user reading the lens preview here shouldn't have to
               scroll down to find that chip. Closes the gap. -->
          <a class="button ghost taste-share-btn" href="../portal_pages/memory.html?file=lens.md" style="margin-left: 8px; text-decoration: none;">
            View full lens →
          </a>
          <span class="meta taste-share-meta" style="display: block; margin-top: 8px;">
            PNG renders the strongest lens as a 1200×630 card — the social object. Text version: one clean paste, pair-wise context (what the model said / what you said back) stays private.
          </span>
        </div>
      </section>

      <section class="card" v-if="!tasteLenses">
        <div class="eyebrow">Your taste, distilled</div>
        <h2>Run lens-build to extract your pair-wise taste lenses</h2>
        <p class="meta">
          The chairman reads your prompt history and surfaces a lens document with
          implicit rejections (model-said vs. you-substituted), vocabulary you
          repeat, and abstract lenses your interactions encode. Each card is
          shareable — paste a single lens to socials without exposing the prompts.
        </p>
        <pre class="md-code-block"><code>trinity-local lens-build</code></pre>
      </section>

      <section class="card">
        <div class="eyebrow">Your lens</div>
        <h2>The four files that compose your cognitive memory</h2>
        <p class="meta">
          One artifact, four levels — read top-down by the chairman on every
          council. <code>picks.json</code> and <code>routing.json</code> are
          operational scoreboards (model-selection bookkeeping derived from
          your verdicts) and surface on the routing card above; they're not
          part of the lens.
        </p>
        <div class="memory-links" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; margin-top: 16px;">
          <a class="memory-chip" href="../portal_pages/memory.html?file=core.md"
             style="display: block; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; text-decoration: none; color: inherit;">
            <code style="color: var(--accent-warm); font-size: 13px;">core.md</code>
            <span class="meta" style="display: block; font-size: 11px; margin-top: 2px;">identity · manifesto paragraph</span>
          </a>
          <a class="memory-chip" href="../portal_pages/memory.html?file=lens.md"
             style="display: block; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; text-decoration: none; color: inherit;">
            <code style="color: var(--accent-warm); font-size: 13px;">lens.md</code>
            <span class="meta" style="display: block; font-size: 11px; margin-top: 2px;">value · paired tensions</span>
          </a>
          <a class="memory-chip" href="../portal_pages/memory.html?file=topics.json"
             style="display: block; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; text-decoration: none; color: inherit;">
            <code style="color: var(--accent-warm); font-size: 13px;">topics.json</code>
            <span class="meta" style="display: block; font-size: 11px; margin-top: 2px;">semantic · basins + evidence map</span>
          </a>
          <a class="memory-chip" href="../portal_pages/memory.html?file=vocabulary.md"
             style="display: block; padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; text-decoration: none; color: inherit;">
            <code style="color: var(--accent-warm); font-size: 13px;">vocabulary.md</code>
            <span class="meta" style="display: block; font-size: 11px; margin-top: 2px;">linguistic · anchors / homonyms / synonyms</span>
          </a>
        </div>
      </section>

      <section class="card">
        <div class="eyebrow">
          Your training history
          <!-- Tick #98: thread-level count when threads != outcomes
               (multi-round chains). The cards below group by thread,
               so showing "3 of 14 threads rated" matches what the user
               sees. Title attribute carries the outcome-level number
               so a power user can hover to see the underlying count.
               Falls back to outcome-only when the two are equal. -->
          <span v-if="pageData.verdictStats && pageData.verdictStats.threads_total > 0
                       && pageData.verdictStats.threads_total !== pageData.verdictStats.total"
                class="meta" style="font-weight: 400; opacity: 0.7;"
                :title="'Per-outcome: ' + pageData.verdictStats.rated + ' of ' + pageData.verdictStats.total + ' rounds rated (multi-round chains count each round)'">
            · {{{{ pageData.verdictStats.threads_rated }}}} of {{{{ pageData.verdictStats.threads_total }}}} threads rated
          </span>
          <span v-else-if="pageData.verdictStats && pageData.verdictStats.total > 0"
                class="meta" style="font-weight: 400; opacity: 0.7;">
            · {{{{ pageData.verdictStats.rated }}}} of {{{{ pageData.verdictStats.total }}}} rated
          </span>
        </div>
        <h2>Every council you've taught the router</h2>
        <p class="meta">Reopen any thread to change your verdict. Every rating feeds your routing above — the moat is this ledger, not any one answer.</p>
        <p class="meta" v-if="pageData.verdictStats && pageData.verdictStats.total >= 5 && pageData.verdictStats.rate < 0.5" style="color: var(--accent); margin-top: -4px;">
          Only {{{{ Math.round(pageData.verdictStats.rate * 100) }}}}% of councils have your verdict. Pick a card below — the ledger learns from every click.
        </p>

        <!-- Recent-councils filter row. Replaces the retired `council-last`
             CLI shortcut — instead of one CLI to find your last thread,
             you filter the list down to what matters. Chips drive a JS
             filter over the .council-card elements (data-rated /
             data-title attrs); the search box does case-insensitive
             substring match on the card title. -->
        <div class="recent-filter-row" style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 18px;">
          <input
            type="search"
            id="recent-filter-search"
            placeholder="Filter by title…"
            aria-label="Filter recent councils by title"
            style="flex: 1 1 200px; max-width: 320px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 10px; font-family: inherit; font-size: 14px; background: var(--surface); color: var(--text-primary);">
          <div class="recent-filter-chips" role="tablist" style="display: flex; gap: 6px;">
            <button type="button" class="recent-filter-chip active" data-filter="all" role="tab" aria-selected="true">All</button>
            <button type="button" class="recent-filter-chip" data-filter="unrated" role="tab" aria-selected="false">Unrated</button>
            <button type="button" class="recent-filter-chip" data-filter="rated" role="tab" aria-selected="false">Rated</button>
          </div>
        </div>

        <div class="grid grid-2" id="recent-councils-grid" style="margin-top: 20px;">
          {recent_cards}
        </div>
        <p class="meta" id="recent-filter-empty" style="display: none; margin-top: 16px;">
          No councils match this filter. Try a different chip or clear the search box.
        </p>
      </section>

      <p class="meta" style="text-align: center; margin-top: 24px; opacity: 0.55; font-size: 12px;" v-if="debugMode">
        Page generated {{{{ pageData.regeneratedAt }}}} · stale? run <code>trinity-local portal-html</code> + Cmd+Shift+R
      </p>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';

    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    {launchpad_runtime_js()}

    function maybeSendTelemetry() {{
      const telemetry = pageData.telemetry || {{}};
      const settings = telemetry.settings || {{}};
      if (!settings.sharing_enabled || !settings.endpoint) {{
        return;
      }}
      // Skip obvious test/placeholder endpoints — sending to them produces
      // ERR_NAME_NOT_RESOLVED noise in the console with no upside.
      // example.invalid is the RFC 6761 reserved stub used during dev.
      if (/example\\.invalid|localhost(?:[:/]|$)|127\\.0\\.0\\.1/.test(settings.endpoint)) {{
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
      const baseScales = {{
        y: {{ ticks: {{ color: '#5f554d' }}, grid: {{ color: 'rgba(215, 204, 185, 0.45)' }} }},
        x: {{ ticks: {{ color: '#5f554d' }}, grid: {{ display: false }} }},
      }};

      const eloData = pageData.eloChart;
      const eloCtx = document.getElementById('provider-elo-chart');
      if (eloCtx && eloData && eloData.labels && eloData.labels.length) {{
        new Chart(eloCtx, {{
          type: 'bar',
          data: eloData,
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{
              y: {{ ...baseScales.y, min: 1400 }},
              x: baseScales.x,
            }},
          }},
        }});
      }}

      // Provider color palette shared across both /100 charts.
      const palette = {{
        claude: 'rgba(213, 130, 79, 0.85)',
        gemini: 'rgba(86, 120, 156, 0.85)',
        codex: 'rgba(78, 138, 109, 0.85)',
        mlx: 'rgba(124, 96, 130, 0.85)',
      }};

      // Trinity task_type → category map, injected from the server's
      // canonical CATEGORY_REGISTRY so the launchpad chart never drifts
      // out-of-sync with new task_types. Unknown kinds bucket into
      // `defaultCategoryForUnknownTaskKind` (default: hard_prompts) instead
      // of disappearing from the chart.
      const TASK_KIND_TO_CATEGORY = pageData.taskKindToCategory || {{}};
      const DEFAULT_CATEGORY = pageData.defaultCategoryForUnknownTaskKind || 'overall';

      const benchmarks = pageData.globalBenchmarks || {{}};
      const providers = pageData.benchmarkProviders || [];
      const categories = Object.keys(benchmarks);
      const labels = categories.map((c) => c.charAt(0).toUpperCase() + c.slice(1));

      function buildGroupedBar(ctxId, datasets) {{
        const ctx = document.getElementById(ctxId);
        if (!ctx) return;
        new Chart(ctx, {{
          type: 'bar',
          data: {{ labels, datasets }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#5f554d' }} }} }},
            scales: {{
              y: {{ ...baseScales.y, min: 0, max: 100 }},
              x: baseScales.x,
            }},
          }},
        }});
      }}

      // Reference evals chart.
      if (providers.length && categories.length) {{
        const datasets = providers.map((provider) => ({{
          label: provider.charAt(0).toUpperCase() + provider.slice(1),
          data: categories.map((cat) => {{
            const v = benchmarks[cat]?.models?.[provider];
            return (v === null || v === undefined) ? null : v;
          }}),
          backgroundColor: palette[provider] || 'rgba(120, 120, 120, 0.85)',
          borderRadius: 4,
        }}));
        buildGroupedBar('reference-evals-chart', datasets);
      }}

      // Personal preference chart — uses the LMArena-aligned CATEGORY_REGISTRY
      // for its X-axis (NOT the globalBenchmarks keys, which are a different
      // scheme: ArtificialAnalysis intelligence/coding/agentic). Reusing the
      // benchmarks X-axis was the original bug — task_types bucketed into
      // hard_prompts / overall / etc never matched intelligence / agentic.
      const personal = pageData.personalRoutingTable;
      const personalCtx = document.getElementById('personal-preference-chart');
      const personalCategoryKeys = pageData.personalChartCategoryKeys || [];
      const personalCategoryLabels = pageData.personalChartCategoryLabels || {{}};
      if (personalCtx && personal && providers.length && personalCategoryKeys.length) {{
        const byTaskType = personal.by_task_type || {{}};
        const personalDatasets = providers.map((provider) => ({{
          label: provider.charAt(0).toUpperCase() + provider.slice(1),
          data: personalCategoryKeys.map((cat) => {{
            // Average overall scores for any task_type that maps to this category.
            const scores = [];
            for (const [taskKind, providerScores] of Object.entries(byTaskType)) {{
              const mappedCat = TASK_KIND_TO_CATEGORY[taskKind] || DEFAULT_CATEGORY;
              if (mappedCat !== cat) continue;
              const entry = providerScores?.[provider];
              if (entry && typeof entry.overall === 'number') {{
                scores.push(entry.overall);
              }}
            }}
            if (!scores.length) return null;
            const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
            return Math.round(mean * 10 * 10) / 10;  // 0-10 → 0-100, 1 decimal
          }}),
          backgroundColor: palette[provider] || 'rgba(120, 120, 120, 0.85)',
          borderRadius: 4,
        }}));
        // Only render if at least one bar has data.
        const hasAny = personalDatasets.some((d) => d.data.some((v) => v !== null));
        if (hasAny) {{
          // Build chart inline — it uses a DIFFERENT X-axis from buildGroupedBar
          // (which is closed over the global `labels` from globalBenchmarks).
          new Chart(personalCtx, {{
            type: 'bar',
            data: {{
              labels: personalCategoryKeys.map((k) => personalCategoryLabels[k] || k),
              datasets: personalDatasets,
            }},
            options: {{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#5f554d' }} }} }},
              scales: {{
                y: {{ ...baseScales.y, min: 0, max: 100 }},
                x: baseScales.x,
              }},
            }},
          }});
        }}
      }}
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

    function formatProviderLabel(provider) {{
      if (!provider) {{
        return '';
      }}
      const normalized = String(provider).trim().toLowerCase();
      const labels = {{
        claude: 'Claude',
        gemini: 'Gemini',
        codex: 'Codex',
        mlx: 'MLX',
        openai: 'OpenAI',
      }};
      if (labels[normalized]) {{
        return labels[normalized];
      }}
      return normalized
        .split(/[_\\s-]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
    }}

    function LaunchpadApp(pageData) {{
      const initialOperation = normalizeOperation(pageData.activeOperation || null);
      return {{
        prompt: '',
        suggestionsOpen: false,
        launchError: '',
        // Phase 4 — single global banner that opens when dispatch hits
        // tier 3 (no extension + no Shortcut) or when the extension is
        // present but install-extension wasn't run (`native-host-unavailable`).
        // Per codex's verdict: ONE inline banner, not per-button replacement.
        // Buttons stay clickable; failed click reopens the banner if dismissed.
        dispatchBannerOpen: false,
        dispatchBannerReason: '',  // 'no-route' | 'native-host-unavailable'
        operation: initialOperation,
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
        }},
        coreStatus: pageData.coreStatus || {{ state: 'empty' }},
        memoryHealth: pageData.memoryHealth || {{ issues: [], ok_count: 0, total_count: 0 }},
        liveReviewUrlBase: pageData.liveReviewUrl || '',
        globalBenchmarks: pageData.globalBenchmarks || {{}},
        benchmarkProviders: pageData.benchmarkProviders || [],
        providerModels: pageData.providerModels || {{}},
        personalRoutingTable: pageData.personalRoutingTable || null,
        cortexRules: pageData.cortexRules || null,
        tasteLenses: pageData.tasteLenses || null,
        // Tooltip lookup for cross-memory chips that deep-link to
        // topology basins. {{basin_id: "top_term1 · top_term2 · ..."}}
        // Resolved server-side from topics.json (tick #38). Empty
        // when no consolidation; chips fall back to "Open basin <id>".
        topologyBasinLabels: pageData.topologyBasinLabels || {{}},
        // Used by .lens-basin-chip + .cortex-topology-chip tooltips.
        basinHoverLabel(bid) {{
          if (!bid) return '';
          const terms = this.topologyBasinLabels[bid];
          if (terms) return 'Basin ' + bid + ' — ' + terms;
          return 'Open basin ' + bid + ' in the topology graph';
        }},
        formatProviderLabel,
        copiedKey: '',
        debugMode: new URLSearchParams(location.search).has('debug'),
        copyLens(text, key) {{
          if (!text) return;
          const restore = () => {{ this.copiedKey = ''; }};
          const setCopied = () => {{
            this.copiedKey = key;
            setTimeout(restore, 1800);
          }};
          if (navigator.clipboard?.writeText) {{
            navigator.clipboard.writeText(text).then(setCopied, () => {{
              this._copyFallback(text);
              setCopied();
            }});
          }} else {{
            this._copyFallback(text);
            setCopied();
          }}
        }},
        _copyFallback(text) {{
          // file:// pages on some browsers block navigator.clipboard. Use the
          // legacy textarea + execCommand path so the lens copies even when
          // the launchpad is opened directly from disk.
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          try {{ document.execCommand('copy'); }} catch (_) {{ /* ignore */ }}
          document.body.removeChild(ta);
        }},
        get routingTableProviders() {{
          if (!this.personalRoutingTable?.by_task_type) return [];
          const set = new Set();
          for (const taskType in this.personalRoutingTable.by_task_type) {{
            for (const provider in this.personalRoutingTable.by_task_type[taskType]) {{
              set.add(provider);
            }}
          }}
          return Array.from(set).sort();
        }},
        coldStartFor(taskType) {{
          // Returns {{n_personal, alpha, personalization_pct}} for a task_type
          // when the cold-start block is present (server-side computed by
          // launchpad_data._load_personal_routing_table). Null when the block
          // is missing (older launchpad_data without the augmentation) so the
          // column degrades to a "—" gracefully.
          return this.personalRoutingTable?.cold_start?.[taskType] || null;
        }},
        ruleHealthLabel(r) {{
          // The Health column on the cortex rules card surfaces signals
          // the trust score already encodes — bimodality, audit verdict,
          // and user overrides — because their meaning is operational
          // (recommend an action) while trust is just a number. Override
          // wins precedence: the user's veto is more authoritative than
          // any system-derived signal. Returns empty string when nothing
          // fires; caller renders "—".
          const overrides = r.override_count || 0;
          if (overrides > 0) {{
            return overrides === 1 ? '⊘ overridden' : `⊘ overridden (${{overrides}}×)`;
          }}
          if (r.bimodal_flag) return '⚠ bimodal';
          if (r.audit_status === 'disagreed') return '⚠ drift';
          if (r.audit_status === 'agreed') return '✓ audited';
          if (r.audit_status === 'unclear') return '? audit';
          return '';
        }},
        ruleHealthTitle(r) {{
          const overrides = r.override_count || 0;
          if (overrides > 0) {{
            const factor = Math.pow(0.5, overrides);
            const pct = Math.round((1 - factor) * 100);
            return `You've marked this rule wrong ${{overrides}} time(s). Effective trust is ${{(r.raw_trust_score || r.trust_score).toFixed(2)}} × ${{factor.toFixed(2)}} = ${{r.trust_score.toFixed(2)}} (${{pct}}% demoted). Use --reset on cortex-override / mark_pick_wrong(reset=true) to clear if you change your mind.`;
          }}
          if (r.bimodal_flag) return 'Basin embeddings split into two modes. The single rule.primary is wrong for half the queries — kNN fallback handles it for now. v1.6 will run HDBSCAN to split.';
          if (r.audit_status === 'disagreed') return 'An independent chairman read the same outcomes and disagreed with the extracted rule. Likely model drift; consider re-running consolidate.';
          if (r.audit_status === 'agreed') return 'An independent chairman read the same outcomes and confirmed the extracted rule. High confidence.';
          if (r.audit_status === 'unclear') return 'The audit chairman returned an unclear verdict on this rule.';
          return 'No audit has been run on this rule. Run consolidate --audit to check for drift.';
        }},
        evidenceUrl(councilId) {{
          // Each evidence chip links to the existing live council page for
          // that outcome. Uses ?thread_id= so the harness page renders the
          // full council UI with members + chairman synthesis. Falls back to
          // a plain `?council_id=` fragment when the launchpad's live-council
          // base URL isn't configured — degrades to a same-page anchor.
          const base = pageData.liveReviewUrl || '';
          if (base) {{
            const sep = base.includes('?') ? '&' : '?';
            return `${{base}}${{sep}}thread_id=${{encodeURIComponent(councilId)}}`;
          }}
          return `#${{councilId}}`;
        }},
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
            return suggestions.slice(0, 8);
          }}
          const queryTokens = query.split(/\\s+/).filter(Boolean);
          return suggestions.filter((item) => {{
            const value = (typeof item === 'string' ? item : (item.text || '')).toLowerCase();
            return queryTokens.every((token) => value.includes(token));
          }}).slice(0, 8);
        }},
        suggestionText(item) {{
          if (typeof item === 'string') return item;
          return item?.text || '';
        }},
        suggestionReasons(item) {{
          if (typeof item === 'string') return [];
          return Array.isArray(item?.reasons) ? item.reasons : [];
        }},
        suggestionWinner(item) {{
          if (typeof item === 'string') return null;
          if (!item?.winner) return null;
          const w = String(item.winner);
          return w.charAt(0).toUpperCase() + w.slice(1);
        }},
        suggestionPriorPreview(item) {{
          if (typeof item === 'string') return '';
          return item?.priorAssistantPreview || '';
        }},
        suggestionPriorFull(item) {{
          if (typeof item === 'string') return '';
          return item?.priorAssistantText || '';
        }},
        get showSuggestions() {{
          return this.suggestionsOpen && !this.busy && this.filteredCouncilSuggestions.length > 0;
        }},
        get suggestionsHeader() {{
          return this.normalizedPrompt ? 'Matching previous council queries' : 'Top used council queries';
        }},
        get busy() {{
          return !!this.operation && this.operation.status === 'running';
        }},
        // Mirror of Python `is_polish_task` (task_types.py). Heuristic
        // tuned for recall — better to over-suggest iteration than miss
        // a polish task. Two paths:
        //   1) literal polish phrase ("make this better", "tighten this",
        //      "any better?", …)
        //   2) ≤20 words AND contains a short imperative hint
        //      ("shorter", "simpler", "clearer", …)
        get isPolishLike() {{
          const text = (this.prompt || '').toLowerCase().trim();
          if (!text) return false;
          const phrases = [
            'make this better', 'make it better',
            'make this stronger', 'make it stronger',
            'make this sharper', 'make it sharper',
            'improve this', 'polish this', 'polish it',
            'tighten this', 'tighten it',
            'rewrite this', 'refine this', 'edit this',
            'is this clearer', 'is this stronger', 'is this better',
            'any better', 'does this make sense', 'is this right',
          ];
          for (const p of phrases) {{
            if (text.includes(p)) return true;
          }}
          const wordCount = text.split(/\\s+/).filter(Boolean).length;
          if (wordCount <= 20) {{
            const hints = ['shorter', 'simpler', 'clearer', 'stronger', 'punchier', 'crisper'];
            for (const h of hints) {{
              if (text.includes(h)) return true;
            }}
          }}
          return false;
        }},
        get polishHintVisible() {{
          // Only surface the hint once the user has actually typed something
          // and we recognized polish. No hint = no noise.
          return this.isPolishLike && (this.prompt || '').trim().length >= 8;
        }},
        get heroTitle() {{
          if (this.operation?.kind === 'council' && this.busy) {{
            return 'Council in Progress';
          }}
          if (this.operation?.kind === 'ingest' && this.busy) {{
            return 'Ingest in Progress';
          }}
          // Workspace-first: H1 names what this surface does. The tagline
          // lives in the lede below, where it has room to breathe.
          return 'Run a Council';
        }},
        // Hide developer/placeholder endpoint values from the settings UI;
        // example.invalid is the RFC 6761 stub used during dev, localhost
        // is a test value. Show "Not configured" so users don't think a
        // broken URL is intentional.
        get displayedEndpoint() {{
          const ep = this.telemetry?.endpoint || '';
          if (!ep) return 'Not configured';
          if (/example\\.invalid|^https?:\\/\\/(localhost|127\\.0\\.0\\.1)/.test(ep)) {{
            return 'Not configured';
          }}
          return ep;
        }},
        get heroLede() {{
          if (this.operation?.kind === 'council' && this.busy) {{
            return 'Trinity is asking every model you use. Routing JSON outcome lands when chairman finishes.';
          }}
          if (this.operation?.kind === 'ingest' && this.busy) {{
            return 'Trinity is refreshing your local context and getting the launchpad ready.';
          }}
          return 'Your taste, ported.';
        }},
        get heroMechanism() {{
          if (this.busy) {{
            return '';
          }}
          return 'No new app. No service. No API key.';
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
        get liveCouncilUrl() {{
          if (!this.operation?.statusToken || !this.liveReviewUrlBase) {{
            return '';
          }}
          const params = new URLSearchParams();
          params.set('status_token', this.operation.statusToken);
          if (this.operation.label) {{
            params.set('task', this.operation.label);
          }}
          if (this.operation.memberOrder?.length) {{
            params.set('members', this.operation.memberOrder.join(','));
          }}
          return `${{this.liveReviewUrlBase}}?${{params.toString()}}`;
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
              return `${{formatProviderLabel(activeProvider)}}: ${{message}}`;
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
          const rows = providers.map((provider) => {{
            const item = memberMap[provider] || {{}};
            const status = item.status || 'pending';
            const providerLabel = formatProviderLabel(provider);
            return {{
              provider,
              label: providerLabel,
              statusLabel: status === 'done' ? 'Done' : status === 'failed' ? 'Failed' : status === 'running' ? 'Running' : 'Queued',
              statusClass: status === 'done' ? 'done' : status === 'failed' ? 'failed' : status === 'running' ? 'running' : 'pending',
              detail: status === 'done'
                ? (item.reasoning_summary || 'Response ready.')
                : status === 'failed'
                  ? (item.reasoning_summary || 'Provider failed.')
                  : '',
            }};
          }});
          const synthesisStatus = this.operation?.synthesis?.status || 'pending';
          const memberPending = rows.slice(0, providers.length).some((row) => row.statusClass === 'pending' || row.statusClass === 'running');
          rows.push({{
            provider: 'analysis',
            label: 'Analysis',
            statusLabel: synthesisStatus === 'done' ? 'Done' : synthesisStatus === 'failed' ? 'Failed' : synthesisStatus === 'running' ? 'Running' : 'Queued',
            statusClass: synthesisStatus === 'done' ? 'done' : synthesisStatus === 'failed' ? 'failed' : synthesisStatus === 'running' ? 'running' : 'pending',
            detail: synthesisStatus === 'done'
              ? 'Final comparison complete.'
              : synthesisStatus === 'failed'
                ? 'Final comparison failed.'
                : synthesisStatus === 'running'
                  ? 'Comparing responses and writing the final recommendation.'
                  : memberPending
                    ? 'Waiting for member responses.'
                    : 'Ready to start final comparison.',
          }});
          return rows;
        }},
        copyText(value, flashKey) {{
          if (!value) {{
            return;
          }}
          if (navigator.clipboard?.writeText) {{
            navigator.clipboard.writeText(value).catch(() => null);
          }} else {{
            window.prompt('Copy this command:', value);
          }}
          // Optional flash-feedback: caller passes a string key that
          // template v-if expressions can compare against `copiedKey`
          // to show "✓ Copied" briefly. Resets after 2400ms — matches
          // copyHealthCommand's existing cadence so transient chips
          // animate consistently across the launchpad.
          if (flashKey) {{
            this.copiedKey = flashKey;
            setTimeout(() => {{
              if (this.copiedKey === flashKey) this.copiedKey = '';
            }}, 2400);
          }}
        }},
        copyHealthCommand(issue) {{
          // Build the per-issue flash key + delegate to copyText, which
          // owns the setTimeout + reset since tick #76 made the helper
          // accept (value, flashKey). The inline setTimeout that used
          // to live here was a duplicate of #76's flash logic — third
          // shape would have made principle #17 ("three inline shapes
          // = missing helper") fire on something that's already a helper.
          if (!issue || !issue.command) return;
          this.copyText(issue.command, 'health-' + issue.name + issue.status);
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
        thinkingLevel(provider) {{
          // Surface the variant tag the reference-eval source attaches to a
          // model name, e.g. "Adaptive Reasoning, Max Effort" or "xhigh" —
          // the bit in parens after the display name. Empty if no variant.
          const meta = this.referenceEvalsMeta && this.referenceEvalsMeta.providers;
          if (!meta || !meta[provider] || !meta[provider].name) return '';
          const m = String(meta[provider].name).match(/\\(([^)]+)\\)\\s*$/);
          return m ? m[1] : '';
        }},
        triggerShortcut(url) {{
          const link = document.createElement('a');
          link.href = url;
          link.rel = 'noreferrer';
          document.body.appendChild(link);
          link.click();
          link.remove();
        }},
        handleDispatchResult(result) {{
          // Phase 4: surface dispatch-tier failures inline. The dispatcher
          // returns {{tier: 'extension'|'shortcut'|'install-prompt', ok, response, reason}}.
          // We act on three cases:
          //   - tier === 'install-prompt': show the banner (neither path works)
          //   - tier === 'extension' && reason === 'native-host-unavailable':
          //       extension found but `install-extension` wasn't run — show
          //       the install-extension hint specifically, not the generic
          //       install banner
          //   - tier === 'extension' && !ok && other error: surface to the
          //       launchError ribbon
          if (!result) return;
          if (result.tier === 'install-prompt') {{
            this.dispatchBannerOpen = true;
            this.dispatchBannerReason = 'no-route';
          }} else if (result.tier === 'extension' && !result.ok) {{
            if (result.reason === 'native-host-unavailable') {{
              this.dispatchBannerOpen = true;
              this.dispatchBannerReason = 'native-host-unavailable';
            }} else {{
              const detail = result.response?.detail || result.response?.error || 'extension error';
              this.launchError = String(detail);
            }}
          }}
        }},
        dismissDispatchBanner() {{ this.dispatchBannerOpen = false; }},
        scheduleLaunchpadReload(delay = 1400) {{
          window.setTimeout(() => {{
            window.location.reload();
          }}, delay);
        }},
        triggerSettingsAction(entry) {{
          // Phase 4b — settings actions now ship as {{shortcutUrl, extensionKind}}.
          // Route through the dispatcher so they work on Linux/Windows when
          // the extension is wired; fall back to the shortcut URL on macOS.
          this.settingsOpen = false;
          const dispatcher = window.__TRINITY_DISPATCH__;
          if (dispatcher && entry?.extensionKind) {{
            dispatcher.dispatch({{
              extensionAction: {{ kind: entry.extensionKind }},
              shortcutUrl: entry.shortcutUrl,
              onResult: (r) => this.handleDispatchResult(r),
            }});
          }} else {{
            this.triggerShortcut(entry?.shortcutUrl || entry);
          }}
          this.scheduleLaunchpadReload();
        }},
        toggleSharing(event) {{
          event.target.checked = this.telemetry.enabled;
          const isNowEnabled = !this.telemetry.enabled;
          const entry = isNowEnabled ? this.settingsLinks.enable : this.settingsLinks.disable;
          this.triggerSettingsAction(entry);
        }},
        resetAnonymousId() {{
          this.triggerSettingsAction(this.settingsLinks.reset);
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
          // Phase 4b (council_bf1ab3f4dd70f75e residual-drift fix): route
          // through the dispatcher so Stop works cross-platform. Extension
          // tier fires `stop-council --status-token <X>`; macOS Shortcut
          // tier keeps the run_command payload as the legacy fallback.
          const dispatcher = window.__TRINITY_DISPATCH__;
          if (dispatcher) {{
            dispatcher.dispatch({{
              extensionAction: {{
                kind: 'stop-council',
                status_token: this.operation.statusToken,
              }},
              shortcutUrl: buildShortcutUrl(payload),
              onResult: (r) => this.handleDispatchResult(r),
            }});
          }} else {{
            this.triggerShortcut(buildShortcutUrl(payload));
          }}
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
          const text = this.suggestionText(suggestion);
          const prior = this.suggestionPriorFull(suggestion);
          // For thread-dependent prompts ("continue.", "Let me restart.")
          // prepend the prior assistant excerpt so fresh members see the
          // framing the user was responding to. Mirrors the canonical format
          // in src/trinity_local/thread_context.py.
          if (prior && text) {{
            const BUDGET = 1500;
            let excerpt = prior.trim();
            if (excerpt.length > BUDGET) {{
              const half = Math.floor(BUDGET / 2);
              excerpt = excerpt.slice(0, half).trimEnd()
                + '\\n[... excerpt truncated ...]\\n'
                + excerpt.slice(-half).trimStart();
            }}
            this.prompt =
              'Prior conversation context — the user is continuing a thread.\\n'
              + 'The previous assistant turn said:\\n'
              + '---\\n' + excerpt + '\\n---\\n\\n'
              + 'Current user message:\\n'
              + text;
          }} else {{
            this.prompt = text;
          }}
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
                if (status.review_path) {{
                  navigateToReviewPath(status.review_path);
                  return;
                }}
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
          // Phase 4: route through window.__TRINITY_DISPATCH__ which tries
          // the Chrome extension first, falls back to the macOS Shortcut,
          // and surfaces the install banner if neither is available. The
          // `extensionAction` shape matches capture_host's ACTION_ALLOWLIST
          // (kind=launch-council, task=…); `shortcutUrl` is the existing
          // path so macOS users keep working unchanged.
          const dispatcher = window.__TRINITY_DISPATCH__;
          if (dispatcher) {{
            dispatcher.dispatch({{
              extensionAction: {{
                kind: 'launch-council',
                task: prompt,
                goal: pageData.defaultGoal,
                primary_provider: pageData.defaultPrimaryProvider,
              }},
              shortcutUrl: buildShortcutUrl(payload),
              onResult: (r) => this.handleDispatchResult(r),
            }});
          }} else {{
            this.triggerShortcut(buildShortcutUrl(payload));
          }}
        }},
        renderMeCard() {{
          if (this.busy) return;
          // Render the strongest lens as a PNG + open it. Card is the
          // spec-v1 "social object". Phase 4b closes the last residual-
          // drift gap: extension tier fires `me-card --open` (the CLI
          // grew an --open flag so the host can't shell-chain); macOS
          // Shortcut tier keeps the run_command payload as fallback.
          const out = '~/.trinity/share/me_card.png';
          const command = `trinity-local me-card --out ${{out}} && open ${{out}}`;
          const payload = {{
            name: 'run_command',
            args: {{ command }},
            metadata: {{ kind: 'launchpad_me_card', source: 'launchpad' }},
          }};
          this.copiedKey = 'me-card';
          setTimeout(() => {{ if (this.copiedKey === 'me-card') this.copiedKey = ''; }}, 2400);
          const dispatcher = window.__TRINITY_DISPATCH__;
          if (dispatcher) {{
            dispatcher.dispatch({{
              extensionAction: {{ kind: 'render-me-card' }},
              shortcutUrl: buildShortcutUrl(payload),
              onResult: (r) => this.handleDispatchResult(r),
            }});
          }} else {{
            this.triggerShortcut(buildShortcutUrl(payload));
          }}
        }},
        ingestOnce() {{
          if (this.busy) {{
            return;
          }}
          const statusToken = `ingest_${{Date.now().toString(36)}}_${{Math.random().toString(36).slice(2, 8)}}`;
          // watch-once was retired 2026-05-18 (commit 07ea7da); the
          // launchpad's "Scan recent transcripts" button now fires
          // ingest-recent — the same passive cursor-based path MCP `ask`
          // hits. status-token guard removed since ingest-recent doesn't
          // write to ~/.trinity/portal_pages/status/.
          const command = `trinity-local ingest-recent`;
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
          // Phase 4: Same routing as launchCouncil — extension first,
          // then Shortcut, then install prompt. The `ingest-recent`
          // allowlist entry replaces the run_command/watch-once payload
          // (the extension surface is intentionally narrower than the
          // Shortcut bridge — the host doesn't run arbitrary commands).
          const dispatcher = window.__TRINITY_DISPATCH__;
          if (dispatcher) {{
            dispatcher.dispatch({{
              extensionAction: {{ kind: 'ingest-recent' }},
              shortcutUrl: buildShortcutUrl(payload),
              onResult: (r) => this.handleDispatchResult(r),
            }});
          }} else {{
            this.triggerShortcut(buildShortcutUrl(payload));
          }}
        }},
      }};
    }}

    createApp({{ LaunchpadApp, pageData }}).mount();
    maybeSendTelemetry();
    renderChart();

    // ── Recent-councils filter (replaces the retired `council-last` CLI)
    //
    // Pure JS over the .council-card-wrapper elements — no petite-vue
    // store, no server round-trip. Filters on the data-rated +
    // data-title attrs the server emits.
    (function() {{
      const grid = document.getElementById('recent-councils-grid');
      if (!grid) return;
      const search = document.getElementById('recent-filter-search');
      const emptyMsg = document.getElementById('recent-filter-empty');
      const chips = document.querySelectorAll('.recent-filter-chip');
      let activeFilter = 'all';

      function applyFilter() {{
        const term = (search && search.value || '').trim().toLowerCase();
        const cards = grid.querySelectorAll('.council-card-wrapper');
        let visible = 0;
        cards.forEach((card) => {{
          const rated = card.getAttribute('data-rated') === 'true';
          const title = card.getAttribute('data-title') || '';
          const ratedOk =
            activeFilter === 'all' ||
            (activeFilter === 'rated' && rated) ||
            (activeFilter === 'unrated' && !rated);
          const termOk = !term || title.includes(term);
          const show = ratedOk && termOk;
          card.style.display = show ? '' : 'none';
          if (show) visible += 1;
        }});
        if (emptyMsg) {{
          emptyMsg.style.display = (visible === 0 && cards.length > 0) ? '' : 'none';
        }}
      }}

      chips.forEach((chip) => {{
        chip.addEventListener('click', () => {{
          chips.forEach((c) => {{
            c.classList.remove('active');
            c.setAttribute('aria-selected', 'false');
          }});
          chip.classList.add('active');
          chip.setAttribute('aria-selected', 'true');
          activeFilter = chip.getAttribute('data-filter') || 'all';
          applyFilter();
        }});
      }});

      if (search) {{
        search.addEventListener('input', applyFilter);
      }}
    }})();
  </script>
{footer}"""
