from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote


_ROUTING_JSON_FENCE_STRIP_RE = re.compile(
    r"```\s*routing[-_ ]?json\s*\n.*?\n\s*```",
    re.IGNORECASE | re.DOTALL,
)


def _strip_routing_json_fence(text: str | None) -> str:
    """Remove the chairman's routing-json fenced block so it doesn't render
    as a raw code dump alongside the structured Routing label card."""
    if not text:
        return ""
    return _ROUTING_JSON_FENCE_STRIP_RE.sub("", text).strip()

from .council_feedback import latest_feedback_by_council
from .council_schema import CouncilOutcome, PromptBundle
from .design_system import render_html_footer, render_html_head
from .dispatch_registry import make_dispatch_action
from .markdown_utils import render_markdown
from .portal_runtime import portal_runtime_js
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import (
    council_outcomes_dir,
    council_status_dir,
    portal_pages_dir,
    review_pages_dir,
)


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _render_routing_label_section(outcome: CouncilOutcome) -> str:
    label = outcome.routing_label
    if label is None:
        return ""
    parts: list[str] = []
    parts.append('<section class="card routing-label-card mb-lg">')
    parts.append('  <div class="eyebrow">Routing label</div>')
    confidence_badge = (
        f'<span class="badge confidence-{_esc(label.confidence)}">{_esc(label.confidence.title())} confidence</span>'
    )
    winner_line = f"<strong>{_esc(label.winner.title() if label.winner else 'No winner')}</strong>"
    if label.runner_up:
        winner_line += f' &middot; runner-up: {_esc(label.runner_up.title())}'
    parts.append(f'  <p class="routing-winner">{winner_line} {confidence_badge}</p>')
    if label.task_type or label.task_domain:
        parts.append(
            f'  <p class="meta">task_type: {_esc(label.task_type or "—")} &middot; '
            f'task_domain: {_esc(label.task_domain or "—")}</p>'
        )
    if label.routing_lesson:
        parts.append(
            f'  <p class="routing-lesson"><span class="meta">Routing lesson:</span> {_esc(label.routing_lesson)}</p>'
        )
    if label.eval_seed:
        parts.append(
            f'  <p class="routing-eval-seed"><span class="meta">Eval seed:</span> {_esc(label.eval_seed)}</p>'
        )
    if label.major_failure_mode:
        parts.append(
            f'  <p class="routing-failure"><span class="meta">Failure mode:</span> {_esc(label.major_failure_mode)}</p>'
        )
    if label.provider_scores:
        rows = []
        for provider, scores in label.provider_scores.items():
            overall = scores.get("overall")
            if overall is None:
                continue
            rows.append(
                f'<tr><td>{_esc(provider.title())}</td><td>{overall:.1f}</td></tr>'
            )
        if rows:
            parts.append(
                '  <table class="routing-scores"><thead><tr><th>Provider</th><th>Overall</th></tr></thead><tbody>'
                + "".join(rows)
                + "</tbody></table>"
            )
    parts.append("</section>")
    return "\n".join(parts)




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
    synthesis_text = _strip_routing_json_fence(outcome.synthesis_output) or "(synthesis not available)"
    synthesis_body = render_markdown(synthesis_text)
    # Chairman attribution: name + model the user can read at a glance
    chairman_provider_label = (outcome.primary_provider or "unknown").replace("_", " ").title()
    chairman_model_label = (outcome.primary_model or "").strip()
    chairman_attribution = (
        f"Chaired by <strong>{_esc(chairman_provider_label)}</strong>"
        + (f" · {_esc(chairman_model_label)}" if chairman_model_label else "")
    )
    routing_label_html = _render_routing_label_section(outcome)

    head = render_html_head(
        f"Trinity — Council {council_id[:12]}",
        extra_head="",
    )
    footer = render_html_footer()

    # Build chain action shortcut URLs (Continue + Auto-chain). Refine is
    # built per-typed-prompt at click time in the petite-vue handler.
    continue_shortcut = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "council_continue",
            args={"council_id": council_id},
            metadata={"kind": "council_continue"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    auto_chain_shortcut = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "council_auto_chain",
            args={"council_id": council_id, "max_rounds": 3},
            metadata={"kind": "council_auto_chain"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )

    # Round + chain navigation
    round_number = (outcome.metadata or {}).get("round_number") or 1
    parent_council_id = (outcome.metadata or {}).get("parent_council_id")
    chain_root_id = (outcome.metadata or {}).get("chain_root_id") or council_id
    converged = False
    try:
        from .council_runtime import chairman_says_converged as _converged

        converged = _converged(outcome.routing_label)
    except Exception:
        converged = False

    page_data = {
        "councilId": council_id,
        "answers": answers_payload,
        "launchpadUrl": f"file://{(portal_pages_dir() / 'launchpad.html').resolve()}",
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
        "shortcutName": DEFAULT_SHORTCUT_NAME,
        "initialSelection": {
            "provider": selected_provider or "",
            "label": selected_label or "",
        },
        "chain": {
            "continueUrl": continue_shortcut.url,
            "autoChainUrl": auto_chain_shortcut.url,
            "shortcutName": DEFAULT_SHORTCUT_NAME,
            "roundNumber": int(round_number),
            "parentCouncilId": parent_council_id,
            "chainRootId": chain_root_id,
            "converged": converged,
        },
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

    .page-header-bar {{
      display: flex;
      justify-content: flex-start;
      align-items: flex-start;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 10px;
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

    .chain-actions {{
      margin-top: 24px;
    }}

    .chain-button-row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 16px;
    }}

    .chain-refine-row {{
      display: flex;
      gap: 12px;
      margin-top: 16px;
      align-items: stretch;
    }}

    .chain-refine-input {{
      flex: 1;
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font-size: 14px;
      font-family: inherit;
      background: var(--surface);
      color: var(--text-primary);
    }}

    .chain-refine-input:focus {{
      outline: none;
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.12);
    }}

    .chain-loading {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-top: 16px;
      padding: 14px 18px;
      background: var(--surface-muted);
      border-radius: 10px;
    }}

    .chain-loading-link {{
      margin-top: 12px;
      font-size: 13px;
    }}

    .chain-loading .spinner {{
      display: inline-block;
      width: 18px;
      height: 18px;
      border: 2px solid var(--border);
      border-top-color: var(--action);
      border-radius: 50%;
      animation: chain-spin 0.9s linear infinite;
    }}

    @keyframes chain-spin {{
      to {{ transform: rotate(360deg); }}
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

      .page-header-bar {{
        flex-direction: column;
        align-items: flex-start;
      }}
    }}
  </style>

  <main>
    <div id="council-app" v-scope="CouncilApp(pageData)">
      <section class="card mb-lg">
        <div class="page-header-bar">
          <a class="button ghost" :href="pageData.launchpadUrl">Back to Launchpad</a>
        </div>
        <h1>{_esc(page_title)}</h1>
        <p class="lede">Read the analysis below, compare the responses, then pick your preference.</p>
      </section>

      <section class="card synthesis-section mb-lg">
        <h2>Comparative Analysis</h2>
        <p class="meta chairman-attribution">{chairman_attribution}</p>
        <div class="markdown-body">{synthesis_body}</div>
      </section>

      {routing_label_html}

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

      <section class="card chain-actions">
        <div class="eyebrow">Round {{{{ chain.roundNumber }}}}{{{{ chain.converged ? ' · models converged' : '' }}}}</div>
        <h2 v-if="!chainBusy">Continue the conversation</h2>
        <h2 v-if="chainBusy">{{{{ chainStatusHeading }}}}</h2>
        <p class="meta" v-if="!chainBusy">
          Run another round where each model sees the others' answers and refines.
          Or add a new directive to push the conversation in a new direction.
          Click <strong>Pick winner</strong> on a card above to stop here.
        </p>
        <div class="chain-loading" v-if="chainBusy">
          <span class="spinner" aria-hidden="true"></span>
          <span class="meta">{{{{ chainStatusDetail }}}}</span>
        </div>
        <div class="chain-button-row" v-if="!chainBusy">
          <button type="button" class="button primary" @click="startContinue">Continue (one round)</button>
          <button type="button" class="button ghost" @click="startAutoChain">Auto-chain (up to 3 rounds, stop when converged)</button>
        </div>
        <div class="chain-refine-row" v-if="!chainBusy">
          <input
            type="text"
            class="chain-refine-input"
            v-model="refinePrompt"
            placeholder="Or refine with a new directive…"
            @keydown.enter="startRefine"
          />
          <button type="button" class="button" :disabled="!refinePrompt.trim()" @click="startRefine">
            Refine
          </button>
        </div>
        <p class="meta chain-loading-link" v-if="chainBusy">
          Redirecting to the live council page so you can watch it stream in…
        </p>
      </section>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';
    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    {portal_runtime_js()}

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
        chain: pageData.chain || {{}},
        refinePrompt: '',
        chainBusy: false,
        chainStatusHeading: '',
        chainStatusDetail: '',
        get selectedProviderTitle() {{
          return this.selectedProvider ? this.selectedProvider.replace(/_/g, ' ').replace(/\\b\\w/g, (c) => c.toUpperCase()) : '';
        }},
        _liveCouncilBaseUrl() {{
          // Resolve relative to the launchpad's portal_pages -> review_pages.
          const base = (pageData.launchpadUrl || '').replace('launchpad.html', '').replace('portal_pages', 'review_pages');
          return base + 'live_council.html';
        }},
        _newStatusToken() {{
          // Client-generated UUID-ish so the new round writes to a fresh
          // status file we can navigate to immediately.
          return 'chain_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
        }},
        _fireShortcut(shortcutsUrl) {{
          // Hidden anchor click — fires the macOS shortcuts:// URL without
          // navigating the tab, so we can navigate to the live page next.
          const a = document.createElement('a');
          a.href = shortcutsUrl;
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          a.remove();
        }},
        chooseAnswer(label, provider, shortcutUrl) {{
          this.selectedLabel = label;
          this.selectedProvider = provider;
          this.selectedShortcutUrl = shortcutUrl;
          this.savedProvider = this.selectedProvider;
          this.feedbackSaved = true;
          if (shortcutUrl) {{
            this._fireShortcut(shortcutUrl);
          }}
        }},
        _startChainAction(actionName, additionalArgs, heading, detail) {{
          const statusToken = this._newStatusToken();
          const payload = {{
            name: actionName,
            args: Object.assign(
              {{ council_id: pageData.councilId, status_token: statusToken }},
              additionalArgs || {{}},
            ),
            metadata: {{ kind: actionName }},
          }};
          const encoded = encodeURIComponent(JSON.stringify(payload));
          const shortcutName = encodeURIComponent(this.chain.shortcutName || 'Trinity Dispatch');
          const shortcutsUrl = `shortcuts://run-shortcut?name=${{shortcutName}}&input=text&text=${{encoded}}`;

          this.chainBusy = true;
          this.chainStatusHeading = heading;
          this.chainStatusDetail = detail;

          // Fire the shortcut, then poll the new status_token in-place.
          // When the new round completes, navigate to its review page.
          this._fireShortcut(shortcutsUrl);
          this._pollChainStatus(statusToken);
        }},
        _pollChainStatus(statusToken) {{
          if (this._chainPollHandle) clearInterval(this._chainPollHandle);
          const tick = () => {{
            loadStatusScript(statusToken, (status) => {{
              if (!status) return;
              if (status.status === 'running') {{
                // Update the spinner detail with whichever member is active.
                const synthesisStatus = status.synthesis?.status;
                if (synthesisStatus === 'running') {{
                  this.chainStatusDetail = 'Synthesizing the strongest answer…';
                }} else if (status.active_provider) {{
                  this.chainStatusDetail = `${{status.active_provider}} is responding…`;
                }}
                return;
              }}
              if (status.status === 'completed' && status.review_path) {{
                clearInterval(this._chainPollHandle);
                this._chainPollHandle = null;
                navigateToReviewPath(status.review_path);
                return;
              }}
              if (status.status === 'failed' || status.status === 'canceled') {{
                clearInterval(this._chainPollHandle);
                this._chainPollHandle = null;
                this.chainBusy = false;
                this.chainStatusDetail = status.error || 'Chain action stopped.';
              }}
            }});
          }};
          tick();
          this._chainPollHandle = window.setInterval(tick, 1500);
        }},
        startContinue() {{
          if (this.chainBusy) return;
          this._startChainAction(
            'council_continue',
            null,
            'Starting next round…',
            'Each model is reading the others\\' answers and refining.',
          );
        }},
        startAutoChain() {{
          if (this.chainBusy) return;
          this._startChainAction(
            'council_auto_chain',
            {{ max_rounds: 3 }},
            'Auto-chaining…',
            'Models will iterate up to 3 rounds, stopping when the chairman declares convergence.',
          );
        }},
        startRefine() {{
          if (this.chainBusy) return;
          const prompt = (this.refinePrompt || '').trim();
          if (!prompt) return;
          this._startChainAction(
            'council_refine',
            {{ prompt: prompt }},
            'Refining…',
            'Each model is incorporating your new directive into a refined answer.',
          );
        }},
      }};
    }}

    createApp({{ CouncilApp, pageData }}).mount();
  </script>
{footer}"""


def write_unified_council_page(bundle: PromptBundle, outcome: CouncilOutcome) -> Path:
    """Write a tiny redirect file pointing at the unified `live_council.html`
    page, parameterised with this outcome's `?council_id=`. The unified page
    loads the outcome JSONP and renders. This keeps existing links to
    `{council_run_id}.html` working without per-outcome HTML duplication."""
    path = review_pages_dir() / f"{outcome.council_run_id}.html"
    target = f"live_council.html?council_id={outcome.council_run_id}"
    path.write_text(
        f"<!doctype html><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"refresh\" content=\"0; url={target}\">"
        f"<title>Trinity — Council {outcome.council_run_id}</title>"
        f"<script>window.location.replace({json.dumps(target)});</script>"
        f"<a href=\"{target}\">Open council review</a>",
        encoding="utf-8",
    )
    # Make sure the unified page itself exists; idempotent.
    write_live_council_page()
    return path


def render_live_council_page() -> str:
    head = render_html_head("Trinity — Council")
    footer = render_html_footer()
    page_data = {
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
        "outcomeScriptBaseUrl": "file://" + quote(str(council_outcomes_dir().resolve())),
        "loadingMessages": LIVE_COUNCIL_LOADING_MESSAGES,
        "shortcutName": DEFAULT_SHORTCUT_NAME,
        "launchpadUrl": f"file://{(portal_pages_dir() / 'launchpad.html').resolve()}",
        "reviewPagesBaseUrl": "file://" + quote(str(review_pages_dir().resolve())),
    }
    return f"""{head}
  <style>
    .live-shell {{
      display: grid;
      gap: 24px;
    }}

    .task-collapsible {{
      margin: 0 0 12px;
      padding: 14px 16px;
      background: rgba(37, 88, 71, 0.04);
      border-left: 3px solid rgba(37, 88, 71, 0.3);
      border-radius: 0 6px 6px 0;
    }}
    .task-collapsible > summary {{
      cursor: pointer;
      font-size: 17px;
      font-weight: 600;
      color: #1a1a1a;
      list-style: none;
    }}
    .task-collapsible > summary::-webkit-details-marker {{ display: none; }}
    .task-collapsible > summary::before {{
      content: "▸ ";
      color: rgba(37, 88, 71, 0.6);
      margin-right: 4px;
    }}
    .task-collapsible[open] > summary::before {{
      content: "▾ ";
    }}

    .page-header-bar {{
      display: flex;
      justify-content: flex-start;
      align-items: flex-start;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 10px;
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

    .answers-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 24px;
      margin-top: 24px;
    }}

    .answers-grid-three {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
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

    .provider-status-row {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 18px 20px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      font-size: 15px;
      transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }}

    .provider-status-row.clickable {{
      cursor: pointer;
      outline: none;
    }}

    .provider-status-row.clickable:hover {{
      transform: translateY(-2px);
      border-color: var(--action);
      box-shadow: 0 8px 24px rgba(37, 88, 71, 0.12);
    }}

    .provider-status-row.clickable:focus-visible {{
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.14);
    }}

    .provider-status-row.selected {{
      border-color: var(--success);
      background: rgba(45, 106, 79, 0.06);
      box-shadow: 0 0 0 3px rgba(45, 106, 79, 0.1), 0 8px 24px rgba(37, 88, 71, 0.12);
    }}

    .confirmation-box {{
      margin-top: 24px;
      background: rgba(45, 106, 79, 0.06);
      border-color: var(--success);
    }}

    .provider-status-header {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .provider-status-name {{
      font-weight: 600;
      flex: 1;
    }}

    .provider-status-response {{
      color: var(--text-primary);
      line-height: 1.55;
      padding: 10px 12px;
      background: var(--surface-muted);
      border-radius: 8px;
      font-size: 14px;
      white-space: pre-wrap;
      word-wrap: break-word;
    }}

    .provider-status-response.markdown-body {{
      white-space: normal;
      font-family: inherit;
    }}

    .provider-status-response.markdown-body pre {{
      white-space: pre-wrap;
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

    .routing-label-grid {{
      display: grid;
      gap: 14px;
      margin-top: 8px;
    }}

    .routing-label-grid ul {{
      margin: 6px 0 0 0;
      padding-left: 20px;
    }}

    .chain-actions {{
      margin-top: 24px;
    }}

    .chain-button-row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 16px;
    }}

    .chain-refine-row {{
      display: flex;
      gap: 12px;
      margin-top: 16px;
      align-items: stretch;
    }}

    .chain-refine-input {{
      flex: 1;
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font-size: 14px;
      font-family: inherit;
      background: var(--surface);
      color: var(--text-primary);
    }}

    .chain-refine-input:focus {{
      outline: none;
      border-color: var(--action);
      box-shadow: 0 0 0 3px rgba(37, 88, 71, 0.12);
    }}

    .chain-loading {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-top: 16px;
      padding: 14px 18px;
      background: var(--surface-muted);
      border-radius: 10px;
    }}

    .chain-loading .spinner {{
      display: inline-block;
      width: 18px;
      height: 18px;
      border: 2px solid var(--border);
      border-top-color: var(--action);
      border-radius: 50%;
    }}

    @keyframes trinity-spin {{
      to {{
        transform: rotate(360deg);
      }}
    }}

    @media (max-width: 768px) {{
      .page-header-bar {{
        flex-direction: column;
        align-items: flex-start;
      }}
    }}

    .chain-segment-divider {{
      margin: 32px 0 8px;
      padding: 12px 18px;
      background: rgba(37, 88, 71, 0.04);
      border-left: 3px solid rgba(37, 88, 71, 0.3);
      border-radius: 0 8px 8px 0;
    }}

    .refinement-prompt {{
      font-style: italic;
      color: var(--text-primary);
    }}
  </style>
  <main>
    <div id="live-council-app" v-scope="LiveCouncilApp(pageData)" @vue:mounted="init">
      <section class="card mb-lg">
        <div class="page-header-bar">
          <a class="button ghost" :href="pageData.launchpadUrl">Back to Launchpad</a>
          <a class="button ghost" v-if="threadViewUrl" :href="threadViewUrl">View full thread</a>
        </div>
        <h1 v-if="threadTaskText && threadTaskText.length <= 240">{{{{ threadTaskText }}}}</h1>
        <details v-if="threadTaskText && threadTaskText.length > 240" class="task-collapsible" :open="threadTaskText.length <= 600">
          <summary>{{{{ threadTaskText.slice(0, 200) }}}}…</summary>
          <p style="white-space: pre-wrap; margin: 12px 0 0;">{{{{ threadTaskText }}}}</p>
        </details>
        <p class="lede" v-if="anyBusy">Each round fills in below as it completes. You can leave and come back without losing the run.</p>
      </section>

      <div class="chain-segment" v-for="(seg, segIndex) in segments" :key="seg.key" :data-seg-key="seg.key">
        <section class="card chain-segment-divider" v-if="segments.length > 1 || seg.refinementText">
          <div class="eyebrow">Round {{{{ seg.roundNumber }}}}{{{{ seg.converged ? ' · models converged' : '' }}}}</div>
          <p v-if="seg.refinementText" class="meta refinement-prompt" style="margin: 6px 0 0;">↳ {{{{ seg.refinementText }}}}</p>
        </section>

        <section class="card launch-status mb-lg" v-if="seg.busy || seg.failed || seg.canceled">
          <div class="spinner-row" v-if="seg.busy">
            <span class="spinner" aria-hidden="true"></span>
            <strong>Council running</strong>
          </div>
          <strong v-if="seg.failed" class="status-error">Council failed</strong>
          <strong v-if="seg.canceled" class="status-error">Council stopped</strong>
          <p class="status-message" v-if="seg.busy">{{{{ currentStatusMessageFor(seg) }}}}</p>
          <p class="status-error" v-if="seg.errorText">{{{{ seg.errorText }}}}</p>
          <div class="live-actions" v-if="seg.busy && segIndex === segments.length - 1">
            <button type="button" class="button ghost" @click="stopCouncil">Stop council</button>
          </div>
        </section>

        <section class="card synthesis-section mb-lg" v-if="analysisRowFor(seg)">
          <div class="provider-status-header">
            <h2 style="margin: 0;">{{{{ analysisRowFor(seg).label }}}}</h2>
            <div class="provider-status-badge" :class="analysisRowFor(seg).statusClass" v-if="analysisRowFor(seg).statusClass !== 'done'">{{{{ analysisRowFor(seg).statusLabel }}}}</div>
          </div>
          <div class="markdown-body" v-if="analysisRowFor(seg).responseHtml" v-html="analysisRowFor(seg).responseHtml" style="margin-top: 12px;"></div>
          <p class="meta" v-else style="margin-top: 8px;">{{{{ analysisRowFor(seg).detail }}}}</p>
        </section>

        <section class="card mb-lg" v-if="routingLabelFor(seg)">
          <div class="eyebrow">Routing label</div>
          <div class="routing-label-grid">
            <div v-if="routingLabelFor(seg).winner">
              <strong>Winner:</strong> {{{{ formatProviderLabel(routingLabelFor(seg).winner) }}}}<span v-if="routingLabelFor(seg).runner_up"> · runner-up: {{{{ formatProviderLabel(routingLabelFor(seg).runner_up) }}}}</span>
              <span v-if="routingLabelFor(seg).confidence"> · confidence: {{{{ routingLabelFor(seg).confidence }}}}</span>
            </div>
            <div v-if="routingLabelFor(seg).agreed_claims && routingLabelFor(seg).agreed_claims.length">
              <strong>Agreed claims</strong>
              <ul><li v-for="c in routingLabelFor(seg).agreed_claims">{{{{ c }}}}</li></ul>
            </div>
            <div v-if="routingLabelFor(seg).disagreed_claims && routingLabelFor(seg).disagreed_claims.length">
              <strong>Disagreed claims</strong>
              <ul>
                <li v-for="d in routingLabelFor(seg).disagreed_claims">
                  <span>{{{{ d.claim }}}}</span>
                  <span v-if="d.providers_for && d.providers_for.length" class="meta"> — for: {{{{ formatProviders(d.providers_for) }}}}</span>
                  <span v-if="d.providers_against && d.providers_against.length" class="meta"> · against: {{{{ formatProviders(d.providers_against) }}}}</span>
                  <div v-if="d.why_matters" class="meta">{{{{ d.why_matters }}}}</div>
                </li>
              </ul>
            </div>
            <div v-if="routingLabelFor(seg).user_likely_values && routingLabelFor(seg).user_likely_values.length">
              <strong>User-fit signals (from /me):</strong> <span class="meta">{{{{ routingLabelFor(seg).user_likely_values.join(', ') }}}}</span>
            </div>
            <div v-if="routingLabelFor(seg).routing_lesson">
              <strong>Routing lesson:</strong> <span class="meta">{{{{ routingLabelFor(seg).routing_lesson }}}}</span>
            </div>
            <div v-if="routingLabelFor(seg).eval_seed">
              <strong>Eval seed:</strong> <span class="meta">{{{{ routingLabelFor(seg).eval_seed }}}}</span>
            </div>
          </div>
        </section>

        <section class="mb-lg" v-if="memberRowsFor(seg).length">
          <h2>Full Responses</h2>
          <p class="meta" v-if="seg.completed">Click the answer you prefer. Trinity saves that choice for local ratings and future routing.</p>
          <div :class="memberRowsFor(seg).length === 3 ? 'answers-grid answers-grid-three' : 'answers-grid'">
            <article
              class="provider-status-row"
              :class="{{ selected: seg.selectedProvider === row.provider, clickable: seg.completed && row.statusClass === 'done' }}"
              v-for="row in memberRowsFor(seg)"
              :key="row.provider"
              :role="seg.completed && row.statusClass === 'done' ? 'button' : null"
              :tabindex="seg.completed && row.statusClass === 'done' ? 0 : null"
              @click="seg.completed && row.statusClass === 'done' ? chooseMember(seg, row.provider, row.answerLabel) : null"
              @keydown.enter.prevent="seg.completed && row.statusClass === 'done' ? chooseMember(seg, row.provider, row.answerLabel) : null"
              @keydown.space.prevent="seg.completed && row.statusClass === 'done' ? chooseMember(seg, row.provider, row.answerLabel) : null"
            >
              <div class="provider-status-header">
                <div class="provider-status-name">{{{{ row.label }}}}</div>
                <div class="provider-status-badge" :class="row.statusClass" v-if="row.statusClass !== 'done'">{{{{ row.statusLabel }}}}</div>
                <div class="provider-status-badge done" v-if="seg.selectedProvider === row.provider">Preferred</div>
              </div>
              <div class="provider-status-response markdown-body" v-if="row.responseHtml" v-html="row.responseHtml"></div>
              <pre class="provider-status-response" v-else-if="row.responseText">{{{{ row.responseText }}}}</pre>
              <div class="provider-status-detail" v-else :class="{{ empty: !row.detail }}">{{{{ row.detail }}}}</div>
            </article>
          </div>
        </section>

        <section class="card confirmation-box" v-if="seg.selectedProvider">
          <div class="eyebrow">Preference saved</div>
          <h2>{{{{ formatProviderLabel(seg.selectedProvider) }}}} is your preferred answer</h2>
          <p class="meta">Trinity uses this for local ratings and future routing.</p>
        </section>
      </div>

      <section class="card chain-actions" v-if="canChainNext">
        <div class="eyebrow">Continue this thread</div>
        <h2 v-if="!chainBusy">Continue the conversation</h2>
        <h2 v-if="chainBusy">{{{{ chainStatusHeading }}}}</h2>
        <p class="meta" v-if="!chainBusy">
          Run another round where each model sees the others' answers and refines.
          Or add a new directive to push the conversation in a new direction.
        </p>
        <div class="chain-loading" v-if="chainBusy">
          <span class="spinner" aria-hidden="true"></span>
          <span class="meta">{{{{ chainStatusDetail }}}}</span>
        </div>
        <div class="chain-button-row" v-if="!chainBusy">
          <button type="button" class="button primary" @click="startContinue">Continue (one round)</button>
          <button type="button" class="button ghost" @click="startAutoChain">Auto-chain (up to 3 rounds, stop when converged)</button>
        </div>
        <div class="chain-refine-row" v-if="!chainBusy">
          <input
            type="text"
            class="chain-refine-input"
            v-model="refinePrompt"
            placeholder="Or refine with a new directive…"
            @keydown.enter="startRefine"
          />
          <button type="button" class="button" :disabled="!refinePrompt.trim()" @click="startRefine">
            Refine
          </button>
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
        councilId: params.get('council_id') || '',
        threadId: params.get('thread_id') || '',
        taskText: params.get('task') || '',
        fallbackMembers: (params.get('members') || '')
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
      }};
    }}

    window.__TRINITY_COUNCIL_THREAD__ = window.__TRINITY_COUNCIL_THREAD__ || {{}};

    function loadThreadScript(threadId, onComplete) {{
      const base = pageData.outcomeScriptBaseUrl || '';
      if (!base || !threadId) {{ onComplete(null); return; }}
      delete window.__TRINITY_COUNCIL_THREAD__[threadId];
      const script = document.createElement('script');
      const cacheBuster = '?t=' + Date.now();
      script.src = base + '/_thread_' + encodeURIComponent(threadId) + '.js' + cacheBuster;
      script.async = true;
      script.onload = () => {{
        const manifest = window.__TRINITY_COUNCIL_THREAD__?.[threadId] || null;
        onComplete(manifest);
        script.remove();
      }};
      script.onerror = () => {{ onComplete(null); script.remove(); }};
      document.body.appendChild(script);
    }}

    function outcomeToRunState(outcome) {{
      if (!outcome) return null;
      const memberOrder = (outcome.member_results || []).map((m) => m.provider);
      const members = {{}};
      for (const m of (outcome.member_results || [])) {{
        members[m.provider] = {{
          status: 'done',
          model: m.model || '',
          response_text: m.output_text || '',
          response_html: m.output_html || '',
        }};
      }}
      const metadata = Object.assign({{}}, outcome.metadata || {{}});
      metadata.chairman_provider = outcome.primary_provider || metadata.chairman_provider || '';
      metadata.chairman_model = outcome.primary_model || metadata.chairman_model || '';
      metadata.council_id = outcome.council_run_id || metadata.council_id || '';
      // Outcome JSON has no top-level task_text — the writer puts it in
      // metadata.task_text so the post-hoc page can render it without
      // needing a second fetch of the bundle.
      return {{
        status: 'completed',
        statusToken: '',
        taskText: outcome.task_text || metadata.task_text || '',
        memberOrder,
        members,
        synthesis: {{
          status: 'done',
          response_text: outcome.synthesis_output_clean || outcome.synthesis_output || '',
          response_html: outcome.synthesis_html || '',
          routing_label: outcome.routing_label || null,
        }},
        metadata,
        review_path: '',
        error: '',
      }};
    }}

    function normalizeStatus(raw, fallback = null) {{
      if (!raw) {{
        return fallback;
      }}
      const memberMap = raw.members || fallback?.members || {{}};
      const fallbackOrder = fallback?.memberOrder || [];
      const rawOrder = raw.memberOrder || raw.metadata?.members || Object.keys(memberMap);
      return {{
        ...fallback,
        ...raw,
        statusToken: raw.statusToken || raw.status_token || fallback?.statusToken || '',
        taskText: raw.taskText || raw.task_text || fallback?.taskText || '',
        activeProvider: raw.activeProvider || raw.active_provider || fallback?.activeProvider || null,
        activeProviders: raw.activeProviders || raw.active_providers || fallback?.activeProviders || [],
        memberOrder: rawOrder?.length ? rawOrder : fallbackOrder,
        members: memberMap,
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

    function makeSegment({{statusToken='', councilId='', taskText='', refinementText='', members=[]}}) {{
      const status = statusToken ? 'running' : 'pending';
      return {{
        key: 'seg_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8),
        councilId,
        statusToken,
        taskText,
        refinementText,
        runState: normalizeStatus({{
          status,
          statusToken,
          taskText,
          memberOrder: members,
          members: Object.fromEntries(members.map((p) => [p, {{ status: 'pending' }}])),
          synthesis: {{ status: 'pending' }},
        }}, null),
        busy: !!statusToken,
        completed: false,
        failed: false,
        canceled: false,
        errorText: '',
        roundNumber: 1,
        converged: false,
        selectedProvider: '',
        currentStatusIndex: 0,
      }};
    }}

    function LiveCouncilApp(pageData) {{
      const params = getParams();
      return {{
        threadTaskText: params.taskText,
        threadId: params.threadId || '',
        threadViewUrl: '',
        segments: [],
        statusPollHandle: null,
        statusRotateHandle: null,
        chainBusy: false,
        chainStatusHeading: '',
        chainStatusDetail: '',
        refinePrompt: '',
        formatProviderLabel(provider) {{ return formatProviderLabel(provider); }},
        formatProviders(names) {{
          if (!Array.isArray(names)) return '';
          return names.map((n) => formatProviderLabel(n)).join(', ');
        }},
        get anyBusy() {{
          return this.segments.some((s) => s.busy);
        }},
        get canChainNext() {{
          if (this.segments.length === 0) return false;
          const last = this.segments[this.segments.length - 1];
          return !!(last.completed && last.councilId);
        }},
        currentStatusMessageFor(seg) {{
          const message = pageData.loadingMessages[seg.currentStatusIndex % pageData.loadingMessages.length] || 'Working...';
          const synthesisStatus = seg.runState?.synthesis?.status;
          if (synthesisStatus === 'running') {{
            return 'Synthesizing the strongest answer...';
          }}
          const active = seg.runState?.activeProvider;
          if (active) {{
            return `${{formatProviderLabel(active)}}: ${{message}}`;
          }}
          return message;
        }},
        memberRowsFor(seg) {{
          const memberMap = seg.runState?.members || {{}};
          const providers = Object.keys(memberMap).length ? Object.keys(memberMap) : (seg.runState?.memberOrder || []);
          return providers.map((provider, idx) => {{
            const item = memberMap[provider] || {{}};
            const status = item.status || 'pending';
            const baseLabel = formatProviderLabel(provider);
            const model = item.model || '';
            return {{
              provider,
              answerLabel: String.fromCharCode(65 + idx),
              label: model ? `${{baseLabel}} (${{model}})` : baseLabel,
              statusLabel: status === 'done' ? 'Done' : status === 'failed' ? 'Failed' : status === 'running' ? 'Running' : 'Queued',
              statusClass: status === 'done' ? 'done' : status === 'failed' ? 'failed' : status === 'running' ? 'running' : 'pending',
              responseHtml: status === 'done' ? (item.response_html || '') : '',
              responseText: status === 'done' ? (item.response_text || item.reasoning_summary || '') : '',
              detail: status === 'failed'
                ? (item.reasoning_summary || 'Provider failed.')
                : status === 'running'
                  ? (item.reasoning_summary || 'Working...')
                  : 'Queued.',
            }};
          }});
        }},
        routingLabelFor(seg) {{
          return seg.runState?.synthesis?.routing_label || null;
        }},
        analysisRowFor(seg) {{
          const synthesisStatus = seg.runState?.synthesis?.status || 'pending';
          const memberPending = this.memberRowsFor(seg).some((row) => row.statusClass === 'pending' || row.statusClass === 'running');
          const chairmanProvider = seg.runState?.metadata?.chairman_provider || '';
          const chairmanModel = seg.runState?.metadata?.chairman_model || '';
          const chairmanLabel = chairmanProvider
            ? formatProviderLabel(chairmanProvider) + (chairmanModel ? ` (${{chairmanModel}})` : '')
            : '';
          const analysisLabel = chairmanLabel ? `Analysis · ${{chairmanLabel}}` : 'Analysis';
          const synthesisHtml = seg.runState?.synthesis?.response_html || '';
          const synthesisText = seg.runState?.synthesis?.response_text || '';
          return {{
            label: analysisLabel,
            statusLabel: synthesisStatus === 'done' ? 'Done' : synthesisStatus === 'failed' ? 'Failed' : synthesisStatus === 'running' ? 'Running' : 'Queued',
            statusClass: synthesisStatus === 'done' ? 'done' : synthesisStatus === 'failed' ? 'failed' : synthesisStatus === 'running' ? 'running' : 'pending',
            responseHtml: synthesisStatus === 'done' ? synthesisHtml : '',
            responseText: synthesisStatus === 'done' && !synthesisHtml ? synthesisText : '',
            detail: synthesisStatus === 'done'
              ? (synthesisHtml || synthesisText ? '' : 'Final comparison complete.')
              : synthesisStatus === 'failed'
                ? 'Final comparison failed.'
                : synthesisStatus === 'running'
                  ? 'Comparing responses and writing the final recommendation.'
                  : memberPending
                    ? 'Waiting for member responses.'
                    : 'Ready to start final comparison.',
          }};
        }},
        chooseMember(seg, provider, answerLabel) {{
          if (!seg.councilId) return;
          const payload = {{
            name: 'rate_council',
            args: {{
              council_id: seg.councilId,
              provider,
              answer_label: answerLabel,
            }},
            metadata: {{ kind: 'council_feedback', source: 'unified_review' }},
          }};
          this._fireShortcut(buildShortcutUrl(payload));
          this._patchSegment(seg.key, {{ selectedProvider: provider }});
        }},
        init() {{
          if (params.threadId) {{
            this.loadThread(params.threadId);
          }} else if (params.statusToken) {{
            const seg = makeSegment({{
              statusToken: params.statusToken,
              taskText: params.taskText,
              members: params.fallbackMembers,
            }});
            this.segments.push(seg);
            this.startPolling();
          }} else if (params.councilId) {{
            const seg = makeSegment({{ councilId: params.councilId, taskText: params.taskText }});
            this.segments.push(seg);
            this._loadOutcomeIntoSegment(seg, params.councilId);
          }}
        }},
        loadThread(threadId) {{
          loadThreadScript(threadId, (manifest) => {{
            const ids = (manifest?.segments || []).map((s) => s.council_id);
            if (!ids.length) {{
              // Fallback: treat threadId as a council_id
              const seg = makeSegment({{ councilId: threadId }});
              this.segments.push(seg);
              this._loadOutcomeIntoSegment(seg, threadId);
              return;
            }}
            // Load all in parallel; render order matches manifest order.
            const segs = ids.map((cid) => makeSegment({{ councilId: cid }}));
            segs.forEach((s) => this.segments.push(s));
            segs.forEach((s, idx) => this._loadOutcomeIntoSegment(s, ids[idx]));
          }});
        }},
        _loadOutcomeIntoSegment(seg, councilId) {{
          loadOutcomeScript(councilId, (outcome) => {{
            const idx = this.segments.findIndex((s) => s.key === seg.key);
            if (idx === -1) return;
            // Replace the segment object via splice so petite-vue's array
            // proxy fires reactivity. Direct property mutation on the
            // existing object is unreliable when the object was created in
            // a sync push and only nested-property-mutated from async load.
            const current = this.segments[idx];
            if (!outcome) {{
              this.segments.splice(idx, 1, Object.assign({{}}, current, {{
                failed: true,
                errorText: 'Could not load council outcome.',
                busy: false,
              }}));
              return;
            }}
            const rs = outcomeToRunState(outcome);
            if (!rs) return;
            const next = Object.assign({{}}, current, {{
              runState: rs,
              taskText: rs.taskText || current.taskText,
              councilId: rs.metadata?.council_id || councilId,
              busy: false,
              failed: false,
              canceled: false,
              completed: true,
              roundNumber: rs.metadata?.round_number || 1,
              converged: !!rs.metadata?.converged,
            }});
            this.segments.splice(idx, 1, next);
            if (!this.threadTaskText) {{
              this.threadTaskText = rs.taskText || this.threadTaskText;
            }}
            // Track the chain root id so we can show "View full thread"
            // when this single-council page is part of a multi-segment chain.
            const chainRoot = rs.metadata?.chain_root_id || next.councilId;
            if (chainRoot && this.segments.length === 1 && !this.threadId) {{
              this._maybeOfferThreadLink(chainRoot);
            }}
          }});
        }},
        _maybeOfferThreadLink(chainRootId) {{
          // Probe the thread manifest. If it has more than one segment,
          // surface the "View full thread" button.
          loadThreadScript(chainRootId, (manifest) => {{
            const count = (manifest?.segments || []).length;
            if (count > 1) {{
              const url = new URL(window.location.href);
              url.search = '?thread_id=' + encodeURIComponent(chainRootId);
              this.threadViewUrl = url.toString();
            }}
          }});
        }},
        stopCouncil() {{
          const last = this.segments[this.segments.length - 1];
          if (!last?.statusToken) return;
          const payload = {{
            name: 'stop_council',
            args: {{ status_token: last.statusToken }},
            metadata: {{ kind: 'stop_council', source: 'live_review' }},
          }};
          window.location.href = buildShortcutUrl(payload);
        }},
        _newStatusToken() {{
          return 'chain_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
        }},
        _fireShortcut(shortcutsUrl) {{
          const a = document.createElement('a');
          a.href = shortcutsUrl;
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          a.remove();
        }},
        _startChainAction(actionName, additionalArgs, refinementText, heading, detail) {{
          const last = this.segments[this.segments.length - 1];
          if (!last?.councilId) return;
          const newToken = this._newStatusToken();
          const payload = {{
            name: actionName,
            args: Object.assign(
              {{ council_id: last.councilId, status_token: newToken }},
              additionalArgs || {{}},
            ),
            metadata: {{ kind: actionName, source: 'live_council' }},
          }};
          this.chainBusy = true;
          this.chainStatusHeading = heading;
          this.chainStatusDetail = detail;
          this._fireShortcut(buildShortcutUrl(payload));
          this.clearPolling();
          this.refinePrompt = '';
          // Append a NEW segment for the next round; prior rounds stay
          // visible above so the page reads as a scrollable thread.
          const memberOrder = Object.keys(last.runState?.members || {{}});
          const newSeg = makeSegment({{
            statusToken: newToken,
            taskText: this.threadTaskText,
            members: memberOrder,
            refinementText: refinementText || '',
          }});
          this.segments.push(newSeg);
          // Auto-scroll the new segment into view after render.
          requestAnimationFrame(() => {{
            const el = document.querySelector('[data-seg-key="' + newSeg.key + '"]');
            el?.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }});
          this.startPolling();
          setTimeout(() => {{ this.chainBusy = false; }}, 800);
        }},
        startContinue() {{
          if (this.chainBusy) return;
          this._startChainAction('council_continue', null, '', 'Starting next round…',
            "Each model is reading the others' answers and refining.");
        }},
        startAutoChain() {{
          if (this.chainBusy) return;
          this._startChainAction('council_auto_chain', {{ max_rounds: 3 }}, '',
            'Auto-chaining…',
            'Models will iterate up to 3 rounds, stopping when the chairman declares convergence.');
        }},
        startRefine() {{
          if (this.chainBusy) return;
          const prompt = (this.refinePrompt || '').trim();
          if (!prompt) return;
          this._startChainAction('council_refine', {{ prompt }}, prompt, 'Refining…',
            'Each model is incorporating your new directive into a refined answer.');
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
        _patchSegment(key, patch) {{
          const idx = this.segments.findIndex((s) => s.key === key);
          if (idx === -1) return null;
          const next = Object.assign({{}}, this.segments[idx], patch);
          this.segments.splice(idx, 1, next);
          return next;
        }},
        startPolling() {{
          const seg0 = this.segments[this.segments.length - 1];
          if (!seg0?.statusToken) {{
            if (seg0) {{
              this._patchSegment(seg0.key, {{ busy: false, failed: true, errorText: 'Missing council status token.' }});
            }}
            return;
          }}
          const segKey = seg0.key;
          this.statusRotateHandle = window.setInterval(() => {{
            const cur = this.segments.find((s) => s.key === segKey);
            if (!cur) return;
            this._patchSegment(segKey, {{ currentStatusIndex: (cur.currentStatusIndex || 0) + 1 }});
          }}, 2500);
          const check = () => {{
            const cur = this.segments.find((s) => s.key === segKey);
            if (!cur?.statusToken) {{ this.clearPolling(); return; }}
            loadStatusScript(cur.statusToken, (status) => {{
              if (!status) return;
              if (!this.threadTaskText) this.threadTaskText = status.task_text || this.threadTaskText;
              const ref = this.segments.find((s) => s.key === segKey);
              if (!ref) return;
              if (status.status === 'running') {{
                this._patchSegment(segKey, {{
                  busy: true, failed: false, canceled: false, errorText: '',
                  runState: normalizeStatus(status, ref.runState),
                }});
                return;
              }}
              if (status.status === 'completed') {{
                this.clearPolling();
                const next = this._patchSegment(segKey, {{
                  busy: false, failed: false, canceled: false, completed: true,
                  runState: normalizeStatus(status, ref.runState),
                  councilId: status.council_id || ref.councilId,
                  roundNumber: (status.metadata && status.metadata.round_number) || 1,
                  converged: !!(status.metadata && status.metadata.converged),
                }});
                if (next?.councilId) {{
                  this._loadOutcomeIntoSegment(next, next.councilId);
                }}
                return;
              }}
              if (status.status === 'failed') {{
                this.clearPolling();
                this._patchSegment(segKey, {{
                  busy: false, failed: true, canceled: false,
                  errorText: status.error || 'Council failed.',
                }});
                return;
              }}
              if (status.status === 'canceled') {{
                this.clearPolling();
                this._patchSegment(segKey, {{
                  busy: false, failed: false, canceled: true,
                  errorText: status.error || 'Council stopped.',
                }});
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


def write_live_council_page() -> Path:
    path = review_pages_dir() / "live_council.html"
    path.write_text(render_live_council_page(), encoding="utf-8")
    return path
