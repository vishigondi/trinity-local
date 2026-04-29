from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .council_feedback import latest_feedback_by_council
from .council_schema import CouncilOutcome, PromptBundle
from .design_system import render_html_footer, render_html_head
from .dispatch_registry import make_dispatch_action
from .markdown_utils import render_markdown
from .scoreboard import state_dir
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation


def review_pages_dir() -> Path:
    path = state_dir() / "review_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def render_review_html(bundle: PromptBundle, outcome: CouncilOutcome | None = None) -> str:
    member_cards = ""
    if outcome is not None:
        member_cards = "\n".join(
            _member_card(member.provider, member.model, member.output_text)
            for member in outcome.member_results
        )

    differences = ""
    if outcome and outcome.differences:
        differences = "".join(f"<li>{_esc(item)}</li>" for item in outcome.differences)

    summary = ""
    peer_reviews = ""
    if outcome:
        summary = f"""
        <section class="card">
          <h2>Primary Synthesis</h2>
          <div class="markdown-body">{render_markdown(outcome.synthesis_output or "(pending)")}</div>
        </section>
        <section class="grid two">
          <section class="card">
            <h2>Winner</h2>
            <p>{_esc(outcome.winner_provider or "unknown")} · {_esc(outcome.winner_model or "unknown")}</p>
            <p>Agreement score: {_esc(str(outcome.agreement_score) if outcome.agreement_score is not None else "n/a")}</p>
            <p>Follow-up needed: {_esc(str(outcome.needs_followup) if outcome.needs_followup is not None else "n/a")}</p>
          </section>
          <section class="card">
            <h2>Differences</h2>
            <ul>{differences or "<li>None recorded.</li>"}</ul>
          </section>
        </section>
        <section class="card">
          <h2>Synthesis Prompt Sent To Primary Model</h2>
          <div class="markdown-body">{render_markdown(outcome.synthesis_prompt or "(not generated)")}</div>
        </section>
        """
        peer_reviews = _peer_review_card(outcome)

    head = render_html_head("Trinity — Council Review")
    footer = render_html_footer()
    origin_label = bundle.origin_provider or bundle.metadata.get("launch_source") or "Direct Council"
    session_label = bundle.origin_session_id
    created_label = _pretty_timestamp(bundle.created_at) or bundle.created_at
    pills = [f'<span class="pill">Origin: {_esc(_pretty_label(origin_label))}</span>']
    if session_label:
        pills.append(f'<span class="pill">Run: {_esc(session_label)}</span>')
    if created_label:
        pills.append(f'<span class="pill">{_esc(created_label)}</span>')

    return f"""{head}
  <style>
    .grid.two {{
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .markdown-body {{
      line-height: 1.65;
      color: var(--text-primary);
    }}
    .markdown-body > :first-child {{
      margin-top: 0;
    }}
    .markdown-body > :last-child {{
      margin-bottom: 0;
    }}
    .markdown-body p,
    .markdown-body ul,
    .markdown-body ol,
    .markdown-body pre {{
      margin: 0 0 14px 0;
    }}
    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3,
    .markdown-body h4,
    .markdown-body h5,
    .markdown-body h6 {{
      margin: 0 0 12px 0;
      line-height: 1.2;
    }}
    .markdown-body ul,
    .markdown-body ol {{
      padding-left: 20px;
    }}
    .markdown-body code {{
      font-family: "SFMono-Regular", Menlo, monospace;
      background: rgba(37, 88, 71, 0.08);
      padding: 2px 6px;
      border-radius: 6px;
      font-size: 0.95em;
    }}
    .markdown-body pre.md-code-block {{
      background: var(--surface-muted);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      overflow-x: auto;
    }}
    .markdown-body pre.md-code-block code {{
      background: transparent;
      padding: 0;
      border-radius: 0;
    }}
    .markdown-body a {{
      color: var(--action);
      text-decoration: none;
    }}
    .markdown-body a:hover {{
      text-decoration: underline;
    }}
    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
    }}
    .markdown-body th, .markdown-body td {{
      text-align: left;
      border-bottom: 1px solid var(--border);
      padding: 8px;
      font-size: 14px;
    }}
    .markdown-body th {{
      background: var(--surface-muted);
      font-weight: 600;
    }}
  </style>
  <main>
    <section class="card">
      <div class="eyebrow">Trinity</div>
      <h1>Council Review</h1>
      <p class="meta">Bundle: {_esc(bundle.bundle_id)}</p>
      <div class="pillbar">
        {"".join(pills)}
      </div>
    </section>

    <section class="card mb-lg">
      <h2>Task</h2>
      <div class="markdown-body">{render_markdown(bundle.task_text)}</div>
    </section>

    <section class="grid two">
      <section class="card">
        <h2>Goal</h2>
        <div class="markdown-body">{render_markdown(bundle.goal or "(none)")}</div>
      </section>
      <section class="card">
        <h2>Comparison Instructions</h2>
        <div class="markdown-body">{render_markdown(bundle.comparison_instructions or "(none)")}</div>
      </section>
    </section>

    <section class="card mb-lg">
      <h2>Context Bundle</h2>
      <div class="markdown-body">{render_markdown(bundle.context_excerpt or "(none)")}</div>
    </section>

    {summary}
    {peer_reviews}

    <section class="card mb-lg">
      <h2>Member Outputs</h2>
      <div class="grid grid-members">
        {member_cards or '<p class="meta">No council member results recorded yet.</p>'}
      </div>
    </section>
  </main>
{footer}
"""


def write_review_html(bundle: PromptBundle, outcome: CouncilOutcome | None = None) -> Path:
    suffix = outcome.council_run_id if outcome is not None else bundle.bundle_id
    path = review_pages_dir() / f"{suffix}.html"
    path.write_text(render_review_html(bundle, outcome), encoding="utf-8")
    return path


PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"


def render_unified_council_page(bundle: PromptBundle, outcome: CouncilOutcome) -> str:
    """Unified page combining synthesis analysis + response cards + voting."""
    council_id = outcome.council_run_id
    prior_feedback = latest_feedback_by_council().get(council_id, {})
    selected_provider = prior_feedback.get("provider")

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

        selected_class = " selected" if selected_provider == provider else ""
        body = render_markdown(output)
        answers_html.append(f"""
    <article class="card answer-card{selected_class}" :class="{{selected: selectedAnswer === '{_esc(answer_label)}'}}">
      <div class="eyebrow">{_esc(answer_label)}</div>
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
    }

    # Use task text as title
    page_title = bundle.task_text or "Council Review"

    return f"""{head}
  <style>
    .answers-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
      gap: 24px;
      margin-top: 24px;
    }}

    .answer-card {{
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      cursor: pointer;
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

    .synthesis-section {{
      margin-bottom: 32px;
    }}

    .confirmation-box {{
      margin-top: 24px;
      background: rgba(45, 106, 79, 0.06);
      border-color: var(--success);
    }}

    .floating-actions {{
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      gap: 12px;
      z-index: 100;
      background: var(--surface);
      padding: 12px 24px;
      border-radius: 24px;
      border: 1px solid var(--border);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    }}

    .floating-actions button {{
      padding: 8px 16px;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }}

    .floating-actions button.primary {{
      background: var(--action);
      color: var(--action-text);
    }}

    .floating-actions button.primary:hover {{
      background: var(--action-hover);
    }}

    .floating-actions button.secondary {{
      background: var(--surface-muted);
      color: var(--text-primary);
      border: 1px solid var(--border);
    }}

    .floating-actions button.secondary:hover {{
      background: var(--border);
    }}

    .floating-actions.hidden {{
      display: none;
    }}

    @media (max-width: 768px) {{
      .floating-actions {{
        bottom: 16px;
        left: 16px;
        right: 16px;
        transform: none;
        gap: 8px;
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
        <p class="meta">Click a "Prefer" button to record your choice. This trains Trinity's Elo scores.</p>
        <div class="answers-grid">
          {"".join(answers_html)}
        </div>
      </section>

      <section class="card confirmation-box" v-if="selectedAnswer">
        <div class="eyebrow">✓ Recorded</div>
        <h2>Your preference is saved</h2>
        <p class="meta">Trinity is learning your taste. This improves future council decisions and Elo rankings.</p>
      </section>
    </div>

    <div class="floating-actions" :class="{{hidden: !selectedAnswer}}" v-if="selectedAnswer">
      <button class="primary" @click="backToLaunchpad">Back to Launchpad</button>
    </div>
  </main>

  <script type="application/json" id="page-data">{json.dumps(page_data, separators=(",", ":"), ensure_ascii=True)}</script>
  <script type="module">
    import {{ createApp }} from '{PETITE_VUE_MODULE}';
    const pageData = JSON.parse(document.getElementById('page-data').textContent);

    function CouncilApp(pageData) {{
      return {{
        selectedAnswer: '',
        backToLaunchpad() {{
          setTimeout(() => {{
            window.location.href = 'launchpad.html';
          }}, 500);
        }}
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
