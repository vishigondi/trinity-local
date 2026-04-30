from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .council_feedback import latest_feedback_by_council
from .council_schema import CouncilOutcome, PromptBundle
from .council_status import council_status_dir
from .design_system import render_html_footer, render_html_head
from .dispatch_registry import make_dispatch_action
from .markdown_utils import render_markdown
from .portal_runtime import portal_runtime_js
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import portal_pages_dir, review_pages_dir


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _pretty_label(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _pretty_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    month = parsed.strftime("%b")
    day = parsed.day
    year = parsed.year
    hour = parsed.hour % 12 or 12
    minute = parsed.strftime("%M")
    suffix = parsed.strftime("%p")
    return f"{month} {day}, {year} at {hour}:{minute} {suffix}"


def _member_card(provider: str, model: str | None, output_text: str) -> str:
    body = render_markdown(output_text)
    return f"""
    <section class="card member">
      <div class="meta">{_esc(provider)} · {_esc(model or "unknown")}</div>
      <div class="markdown-body">{body}</div>
    </section>
    """


def _peer_review_card(outcome: CouncilOutcome) -> str:
    review_cards = "\n".join(
        f"""
        <section class="card member">
          <div class="meta">{_esc(review.reviewer_provider)} · {_esc(review.reviewer_model or "unknown")}</div>
          <p><strong>Ranking:</strong> {_esc(' > '.join(review.ranked_labels) or 'none parsed')}</p>
          <p><strong>Agreement:</strong> {_esc(review.agreement or 'n/a')}</p>
          <p><strong>Strengths:</strong> {_esc('; '.join(review.strengths) or 'n/a')}</p>
          <p><strong>Weaknesses:</strong> {_esc('; '.join(review.weaknesses) or 'n/a')}</p>
          <details>
            <summary>Raw review</summary>
            <pre>{_esc(review.review_text.strip() or "(no review output)")}</pre>
          </details>
          <details>
            <summary>Review prompt</summary>
            <pre>{_esc(review.review_prompt or "(not recorded)")}</pre>
          </details>
        </section>
        """
        for review in outcome.peer_reviews
    )
    aggregate = ""
    if outcome.aggregate_ranking and outcome.aggregate_ranking.ordered_labels:
        rows = "".join(
            "<tr>"
            f"<td>{_esc(label)}</td>"
            f"<td>{_esc(outcome.aggregate_ranking.label_to_provider.get(label, 'unknown'))}</td>"
            f"<td>{_esc(str(outcome.aggregate_ranking.label_scores.get(label, 0.0)))}</td>"
            "</tr>"
            for label in outcome.aggregate_ranking.ordered_labels
        )
        aggregate = f"""
        <section class="card">
          <h2>Aggregate Ranking</h2>
          <table>
            <thead><tr><th>Label</th><th>Provider</th><th>Score</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """
    return f"""
    <section class="card mb-md">
      <h2>Peer Reviews</h2>
      {aggregate}
      <div class="grid grid-members">
        {review_cards or '<p class="meta">No peer reviews recorded.</p>'}
      </div>
    </section>
    """




PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"
LIVE_COUNCIL_LOADING_MESSAGES = [
    "Reticulating splines...",
    "Generating witty dialog...",
    "Tokenizing real life...",
    "Convincing AI not to turn evil...",
    "Computing chance of success...",
    "Optimizing the optimizer...",
    "Keeping all the 1's and removing all the 0's...",
    "Pushing pixels...",
]


def render_unified_council_page(bundle: PromptBundle, outcome: CouncilOutcome) -> str:
    """Unified page combining synthesis analysis + response cards + voting."""
    council_id = outcome.council_run_id
    prior_feedback = latest_feedback_by_council().get(council_id, {})
    selected_provider = prior_feedback.get("provider")
    selected_label = prior_feedback.get("answer_label")
    launchpad_path = (portal_pages_dir() / "launchpad.html").resolve()

    # Build response cards with voting
    answers_html = []
    answers_payload = []
    for i, member in enumerate(outcome.member_results):
        provider = member.provider
        answer_label = chr(65 + i)
        output = member.output_text or ""

        dispatch = make_dispatch_action(
            "rate_council",
            args={
                "council_id": council_id,
                "provider": provider,
                "answer_label": answer_label,
            },
            metadata={"kind": "council_feedback"},
        )
        shortcut = make_shortcut_invocation(dispatch=dispatch, shortcut_name=DEFAULT_SHORTCUT_NAME)
        answers_payload.append({
            "label": answer_label,
            "provider": provider,
            "shortcut_url": shortcut.url,
        })

        body = render_markdown(output)
        answers_html.append(f"""
    <article
      class="card answer-card"
      :class="{{selected: selectedLabel === '{_esc(answer_label)}'}}"
      role="button"
      tabindex="0"
      @click="chooseAnswer('{_esc(answer_label)}', '{_esc(provider)}', '{_esc(shortcut.url)}')"
      @keydown.enter.prevent="chooseAnswer('{_esc(answer_label)}', '{_esc(provider)}', '{_esc(shortcut.url)}')"
      @keydown.space.prevent="chooseAnswer('{_esc(answer_label)}', '{_esc(provider)}', '{_esc(shortcut.url)}')"
    >
      <div class="answer-card-head">
        <div class="eyebrow">{_esc(answer_label)}</div>
        <span class="rank-badge" v-if="selectedLabel === '{_esc(answer_label)}'">Preferred</span>
      </div>
      <h3>{_esc(provider.title())}</h3>
      <div class="markdown-body">{body}</div>
    </article>
    """)

    # Synthesis section
    synthesis_body = render_markdown(outcome.synthesis_output or "(synthesis not available)")

    head = render_html_head(
        f"Trinity — Council {council_id[:12]}",
        extra_head="",
    )
    footer = render_html_footer()

    page_data = {
        "councilId": council_id,
        "answers": answers_payload,
        "initialSelection": {
            "provider": selected_provider or "",
            "label": selected_label or "",
        },
        "launchpadUrl": f"file://{launchpad_path}",
    }

    # Use task text as title
    page_title = bundle.task_text or "Council Review"
    answers_grid_class = "answers-grid answers-grid-three" if len(outcome.member_results) == 3 else "answers-grid"

    return f"""{head}
  <style>
    .answers-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 24px;
      margin-top: 24px;
    }}

    .answers-grid-three {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}

    .answer-card {{
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      cursor: pointer;
      outline: none;
    }}

    .answer-card:hover {{
      transform: translateY(-3px);
      border-color: var(--action);
      box-shadow: 0 12px 30px rgba(37, 88, 71, 0.15);
    }}

    .answer-card:focus-visible {{
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.14), 0 12px 30px rgba(37, 88, 71, 0.15);
    }}

    .answer-card.selected {{
      border-color: var(--success);
      box-shadow: 0 0 0 3px rgba(45, 106, 79, 0.1), 0 12px 30px rgba(37, 88, 71, 0.15);
      background: rgba(45, 106, 79, 0.06);
    }}

    .synthesis-section {{
      margin-bottom: 32px;
    }}

    .confirmation-box {{
      margin-top: 24px;
      background: rgba(45, 106, 79, 0.06);
      border-color: var(--success);
    }}

    .answer-card-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}

    .rank-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 42px;
      padding: 4px 12px;
      border-radius: 999px;
      background: var(--success);
      color: #fff;
      font-size: 13px;
      font-weight: 600;
    }}

    @media (max-width: 1200px) {{
      .answers-grid-three {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}

    @media (max-width: 768px) {{
      .answers-grid,
      .answers-grid-three {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>

  <main>
    <div id="council-app" v-scope="CouncilApp(pageData)">
      <section class="card mb-lg">
        <div class="eyebrow">Council Review</div>
        <h1>{_esc(page_title)}</h1>
        <p class="lede">Read the analysis below, compare the responses, then pick your preference.</p>
      </section>

      <section class="card synthesis-section mb-lg">
        <h2>Comparative Analysis</h2>
        <div class="markdown-body">{synthesis_body}</div>
      </section>

      <section class="mb-lg">
        <h2>Full Responses</h2>
        <p class="meta">Click the answer you prefer. Trinity will save that choice for local ratings and future recommendations.</p>
        <div class="{answers_grid_class}">
          {"".join(answers_html)}
        </div>
      </section>

      <section class="card confirmation-box" v-if="feedbackSaved && selectedProvider">
        <div class="eyebrow">Preference saved</div>
        <h2>{{{{ selectedProviderTitle }}}} is currently your preferred answer</h2>
        <p class="meta">Refreshing this page will keep the selected state. Trinity will use this choice for local ratings and future routing.</p>
      </section>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';
    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    function CouncilApp(pageData) {{
      const initialProvider = pageData.initialSelection?.provider || '';
      const initialLabel = pageData.initialSelection?.label || '';
      const savedProvider = pageData.initialSelection?.provider || '';
      const initialAnswer = (pageData.answers || []).find((answer) => answer.label === initialLabel || answer.provider === initialProvider);

      return {{
        selectedLabel: initialLabel,
        selectedProvider: initialProvider,
        selectedShortcutUrl: initialAnswer?.shortcut_url || '',
        savedProvider,
        feedbackSaved: !!savedProvider && savedProvider === initialProvider,
        get selectedProviderTitle() {{
          return this.selectedProvider ? this.selectedProvider.replace(/_/g, ' ').replace(/\\b\\w/g, (c) => c.toUpperCase()) : '';
        }},
        chooseAnswer(label, provider, shortcutUrl) {{
          this.selectedLabel = label;
          this.selectedProvider = provider;
          this.selectedShortcutUrl = shortcutUrl;
          this.savedProvider = this.selectedProvider;
          this.feedbackSaved = true;
          if (shortcutUrl) {{
            window.location.href = shortcutUrl;
          }}
        }},
      }};
    }}

    createApp({{ CouncilApp, pageData }}).mount();
  </script>
{footer}"""


def write_unified_council_page(bundle: PromptBundle, outcome: CouncilOutcome) -> Path:
    """Write unified council review + voting page."""
    path = review_pages_dir() / f"{outcome.council_run_id}.html"
    path.write_text(render_unified_council_page(bundle, outcome), encoding="utf-8")
    return path


def render_live_council_page() -> str:
    head = render_html_head("Trinity — Council Running")
    footer = render_html_footer()
    launchpad_path = (portal_pages_dir() / "launchpad.html").resolve()
    page_data = {
        "launchpadUrl": f"file://{launchpad_path}",
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
        "loadingMessages": LIVE_COUNCIL_LOADING_MESSAGES,
        "shortcutName": DEFAULT_SHORTCUT_NAME,
    }
    return f"""{head}
  <style>
    .live-shell {{
      display: grid;
      gap: 24px;
    }}

    .launch-status {{
      display: grid;
      gap: 12px;
      padding: 18px;
      border: 1px solid rgba(37, 88, 71, 0.18);
      border-radius: 18px;
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

    .status-message {{
      font-weight: 500;
      min-height: 24px;
      color: var(--action);
    }}

    .provider-status-list {{
      display: grid;
      gap: 10px;
      margin-top: 4px;
    }}

    .provider-status-row {{
      display: grid;
      grid-template-columns: 88px 84px 1fr;
      gap: 12px;
      align-items: start;
      font-size: 15px;
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

    .live-actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}

    .live-actions .button {{
      text-decoration: none;
    }}

    .status-error {{
      color: #8b1e1e;
    }}

    @keyframes trinity-spin {{
      to {{
        transform: rotate(360deg);
      }}
    }}
  </style>
  <main>
    <div id="live-council-app" v-scope="LiveCouncilApp(pageData)" @vue:mounted="init">
      <section class="card">
        <div class="eyebrow">Trinity</div>
        <h1>Council Review</h1>
        <p class="lede">This page will fill in automatically as the council finishes. You can leave and come back without losing the run.</p>
      </section>

      <section class="card launch-status">
        <div class="spinner-row" v-if="busy">
          <span class="spinner" aria-hidden="true"></span>
          <strong>Council running</strong>
        </div>
        <strong v-if="!busy && !failed && !canceled">Council complete</strong>
        <strong v-if="failed" class="status-error">Council failed</strong>
        <strong v-if="canceled" class="status-error">Council stopped</strong>
        <p class="meta" v-if="taskText">{{{{ taskText }}}}</p>
        <p class="status-message" v-if="busy">{{{{ currentStatusMessage }}}}</p>
        <p class="meta" v-if="busy">Trinity is running the council locally. This page will switch to the finished review as soon as it is ready.</p>
        <div class="provider-status-list" v-if="providerStatusRows.length">
          <div class="provider-status-row" v-for="row in providerStatusRows">
            <div class="provider-status-name">{{{{ row.provider }}}}</div>
            <div class="provider-status-badge" :class="row.statusClass">{{{{ row.statusLabel }}}}</div>
            <div class="provider-status-detail" :class="{{ empty: !row.detail }}">{{{{ row.detail || '' }}}}</div>
          </div>
        </div>
        <p class="status-error" v-if="errorText">{{{{ errorText }}}}</p>
        <div class="live-actions" v-if="busy">
          <button type="button" class="button ghost" @click="stopCouncil">Stop council</button>
        </div>
      </section>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';
    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    {portal_runtime_js()}

    function getParams() {{
      const params = new URLSearchParams(window.location.search);
      return {{
        statusToken: params.get('status_token') || '',
        taskText: params.get('task') || '',
      }};
    }}

    function normalizeStatus(raw, fallback = null) {{
      if (!raw) {{
        return fallback;
      }}
      return {{
        ...fallback,
        ...raw,
        statusToken: raw.statusToken || raw.status_token || fallback?.statusToken || '',
        taskText: raw.taskText || raw.task_text || fallback?.taskText || '',
        activeProvider: raw.activeProvider || raw.active_provider || fallback?.activeProvider || null,
        activeProviders: raw.activeProviders || raw.active_providers || fallback?.activeProviders || [],
        members: raw.members || fallback?.members || {{}},
        synthesis: raw.synthesis || fallback?.synthesis || {{}},
        reviewPath: raw.reviewPath || raw.review_path || fallback?.reviewPath || '',
        error: raw.error || fallback?.error || '',
      }};
    }}

    function LiveCouncilApp(pageData) {{
      const params = getParams();
      return {{
        statusToken: params.statusToken,
        taskText: params.taskText,
        runState: null,
        currentStatusIndex: 0,
        statusPollHandle: null,
        statusRotateHandle: null,
        busy: true,
        failed: false,
        canceled: false,
        errorText: '',
        launchpadUrl: pageData.launchpadUrl,
        init() {{
          this.startPolling();
        }},
        get currentStatusMessage() {{
          const message = pageData.loadingMessages[this.currentStatusIndex % pageData.loadingMessages.length] || 'Working...';
          const synthesisStatus = this.runState?.synthesis?.status;
          if (synthesisStatus === 'running') {{
            return 'Synthesizing the strongest answer...';
          }}
          const active = this.runState?.activeProvider;
          if (active) {{
            return `${{active}}: ${{message}}`;
          }}
          return message;
        }},
        get providerStatusRows() {{
          const memberMap = this.runState?.members || {{}};
          const providers = Object.keys(memberMap);
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
        stopCouncil() {{
          if (!this.statusToken) {{
            return;
          }}
          const payload = {{
            name: 'stop_council',
            args: {{
              status_token: this.statusToken,
            }},
            metadata: {{
              kind: 'stop_council',
              source: 'live_review',
            }},
          }};
          window.location.href = buildShortcutUrl(payload);
        }},
        clearPolling() {{
          if (this.statusPollHandle) {{
            clearInterval(this.statusPollHandle);
            this.statusPollHandle = null;
          }}
          if (this.statusRotateHandle) {{
            clearInterval(this.statusRotateHandle);
            this.statusRotateHandle = null;
          }}
        }},
        startPolling() {{
          if (!this.statusToken) {{
            this.busy = false;
            this.failed = true;
            this.errorText = 'Missing council status token.';
            return;
          }}
          this.statusRotateHandle = window.setInterval(() => {{
            this.currentStatusIndex += 1;
          }}, 2500);
          const check = () => {{
            loadStatusScript(this.statusToken, (status) => {{
              if (!status) {{
                return;
              }}
              this.taskText = status.task_text || this.taskText;
              if (status.status === 'running') {{
                this.busy = true;
                this.failed = false;
                this.canceled = false;
                this.errorText = '';
                this.runState = normalizeStatus(status, this.runState);
                return;
              }}
              if (status.status === 'completed' && status.review_path) {{
                this.clearPolling();
                window.location.href = `file://${{encodeURI(status.review_path)}}`;
                return;
              }}
              if (status.status === 'failed') {{
                this.clearPolling();
                this.busy = false;
                this.failed = true;
                this.canceled = false;
                this.errorText = status.error || 'Council failed.';
                return;
              }}
              if (status.status === 'canceled') {{
                this.clearPolling();
                this.busy = false;
                this.failed = false;
                this.canceled = true;
                this.errorText = status.error || 'Council stopped.';
              }}
            }});
          }};
          check();
          this.statusPollHandle = window.setInterval(check, 1500);
        }},
      }};
    }}

    createApp({{ LiveCouncilApp, pageData }}).mount();
  </script>
{footer}"""


def write_live_council_page(*, status_token: str = "", task_text: str = "") -> Path:
    path = review_pages_dir() / "live_council.html"
    path.write_text(render_live_council_page(), encoding="utf-8")
    return path
