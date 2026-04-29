from __future__ import annotations

import html
import json
from pathlib import Path

from .council_feedback import latest_feedback_by_council
from .council_runtime import council_outcomes_dir, load_prompt_bundle
from .design_system import render_html_footer, render_html_head
from .dispatch_registry import make_dispatch_action
from .scoreboard import state_dir
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation

PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"


def signal_pages_dir() -> Path:
    path = state_dir() / "signal_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _load_council_raw(council_id: str) -> dict | None:
    path = council_outcomes_dir() / f"{council_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render_signal_page(council_id: str) -> str | None:
    raw = _load_council_raw(council_id)
    if not raw:
        return None

    bundle_id = raw.get("bundle_id")
    prompt_text = "[Council prompt unavailable]"
    if bundle_id:
        try:
            bundle = load_prompt_bundle(bundle_id)
            prompt_text = bundle.task_text.strip() or prompt_text
        except Exception:
            pass

    prior_feedback = latest_feedback_by_council().get(council_id, {})
    selected_provider = prior_feedback.get("provider")

    answers_html = []
    answers_payload = []
    for i, member in enumerate(raw.get("member_results", [])):
        if not isinstance(member, dict):
            continue
        provider = str(member.get("provider") or f"model_{i+1}")
        answer_label = chr(65 + i)
        output = str(member.get("output_text") or "")
        truncated = output[:900] + "…" if len(output) > 900 else output
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
        answers_payload.append(
            {
                "label": answer_label,
                "provider": provider,
                "preview": truncated,
                "shortcut_url": shortcut.url,
            }
        )
        selected_class = " selected" if selected_provider == provider else ""
        answers_html.append(
            f"""
            <article class="card answer-card{selected_class}" :class="{{ selected: selectedAnswer === '{_esc(answer_label)}' }}">
              <div class="eyebrow">{_esc(answer_label)}</div>
              <h3>{_esc(provider.title())}</h3>
              <pre class="answer-preview">{_esc(truncated)}</pre>
              <div class="actions">
                <a class="button primary" href="{_esc(shortcut.url)}" @click="selectedAnswer = '{_esc(answer_label)}'">Choose { _esc(provider.title()) }</a>
              </div>
            </article>
            """
        )

    page_data = {
        "councilId": council_id,
        "prompt": prompt_text,
        "winnerProvider": raw.get("winner_provider"),
        "selectedProvider": selected_provider,
        "answers": answers_payload,
        "reviewPath": str((state_dir() / "review_pages" / f"{council_id}.html").resolve()),
    }

    head = render_html_head(
        f"Trinity — Rate Council {council_id[:12]}",
        extra_head="",
    )
    footer = render_html_footer()
    answers_markup = "".join(answers_html) or '<p class="meta">No answer cards available.</p>'

    return f"""{head}
  <style>
    .answers-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 24px;
    }}

    .answer-card {{
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }}

    .answer-card:hover {{
      transform: translateY(-3px);
      border-color: var(--action);
      box-shadow: 0 12px 30px rgba(37, 88, 71, 0.15);
    }}

    .answer-card.selected {{
      border-color: var(--success);
      box-shadow: 0 0 0 3px rgba(45, 106, 79, 0.1), 0 12px 30px rgba(37, 88, 71, 0.15);
      background: rgba(45, 106, 79, 0.06);
    }}

    .answer-preview {{
      font-size: 13px;
      line-height: 1.45;
      color: var(--text-secondary);
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 240px;
      overflow-y: auto;
    }}

    .back-link {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--action);
      text-decoration: none;
      font-size: 14px;
      margin-bottom: 24px;
    }}

    .confirmation-box {{
      margin-top: 24px;
    }}
  </style>

  <main>
    <div id="signal-app" v-scope="SignalApp(pageData)">
      <a href="file://{_esc(str((state_dir() / 'portal_pages' / 'launchpad.html').resolve()))}" class="back-link">← Back to Launchpad</a>

      <section class="card mb-xl">
        <div class="eyebrow">Rate this Council</div>
        <h1>Which answer do you prefer?</h1>
        <p class="lede">Pick your favorite. Trinity learns. Future rankings, radar charts, and recommendations get smarter from this choice.</p>
      </section>

      <section class="card mb-xl">
        <div class="label mb-sm">You asked</div>
        <p>{_esc(prompt_text)}</p>
        <div class="pillbar">
          <span class="pill">Council { _esc(council_id[:12]) }</span>
          <span class="pill">Synthesized winner: {_esc((raw.get('winner_provider') or 'unknown').title())}</span>
        </div>
      </section>

      <section class="mb-xl">
        <h2>Compare Answers</h2>
        <p class="meta">Each button records your preference locally through Trinity Dispatch.</p>
        <div class="answers-grid" style="margin-top: 24px;">
          {answers_markup}
        </div>
      </section>

      <section class="card confirmation-box" v-if="selectedAnswer">
        <div class="eyebrow">Selection recorded</div>
        <h2>Trinity is learning your taste</h2>
        <p class="meta">Your preference has been sent to Trinity locally. Reopen the Launchpad or review page to continue.</p>
        <div class="actions">
          <a class="button primary" :href="'file://' + reviewPath">Open Review</a>
          <a class="button secondary" href="file://{_esc(str((state_dir() / 'portal_pages' / 'launchpad.html').resolve()))}">Back to Launchpad</a>
        </div>
      </section>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';
    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    function SignalApp(pageData) {{
      const initial = pageData.answers.find((item) => item.provider === pageData.selectedProvider);
      return {{
        selectedAnswer: initial ? initial.label : '',
        reviewPath: pageData.reviewPath,
      }};
    }}

    createApp({{ SignalApp, pageData }}).mount();
  </script>
{footer}"""


def write_signal_page(council_id: str) -> Path | None:
    html = render_signal_page(council_id)
    if not html:
        return None
    path = signal_pages_dir() / f"{council_id}.html"
    path.write_text(html, encoding="utf-8")
    return path
