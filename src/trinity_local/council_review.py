from __future__ import annotations

import html
from pathlib import Path

from .council_schema import CouncilOutcome, PromptBundle
from .design_system import render_html_footer, render_html_head
from .scoreboard import state_dir


def review_pages_dir() -> Path:
    path = state_dir() / "review_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _member_card(provider: str, model: str | None, output_text: str) -> str:
    body = _esc(output_text.strip() or "(no output)")
    return f"""
    <section class="card member">
      <div class="meta">{_esc(provider)} · {_esc(model or "unknown")}</div>
      <pre>{body}</pre>
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
          <pre>{_esc(outcome.synthesis_output or "(pending)")}</pre>
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
          <pre>{_esc(outcome.synthesis_prompt or "(not generated)")}</pre>
        </section>
        """
        peer_reviews = _peer_review_card(outcome)

    head = render_html_head("Trinity — Council Review")
    footer = render_html_footer()

    return f"""{head}
  <style>
    .grid.two {{
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
  <main>
    <section class="card">
      <div class="eyebrow">Trinity</div>
      <h1>Council Review</h1>
      <p class="meta">Bundle: {_esc(bundle.bundle_id)} · Task cluster: {_esc(bundle.task_cluster_id)}</p>
      <div class="pillbar">
        <span class="pill">Origin: {_esc(bundle.origin_provider or "unknown")}</span>
        <span class="pill">Session: {_esc(bundle.origin_session_id or "unknown")}</span>
        <span class="pill">{_esc(bundle.created_at)}</span>
      </div>
    </section>

    <section class="card mb-lg">
      <h2>Task</h2>
      <pre>{_esc(bundle.task_text)}</pre>
    </section>

    <section class="grid two">
      <section class="card">
        <h2>Goal</h2>
        <pre>{_esc(bundle.goal or "(none)")}</pre>
      </section>
      <section class="card">
        <h2>Comparison Instructions</h2>
        <pre>{_esc(bundle.comparison_instructions or "(none)")}</pre>
      </section>
    </section>

    <section class="card mb-lg">
      <h2>Context Bundle</h2>
      <pre>{_esc(bundle.context_excerpt or "(none)")}</pre>
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
