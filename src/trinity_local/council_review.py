from __future__ import annotations

import html
from pathlib import Path

from .council_schema import CouncilOutcome, PromptBundle
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
    <section class="card" style="margin-top:16px;">
      <h2>Peer Reviews</h2>
      {aggregate}
      <div class="grid members">
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

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>trinity-local Council Review</title>
  <style>
    :root {{
      --bg: #f2efe8;
      --ink: #111111;
      --muted: #5b5b52;
      --card: #fffdf7;
      --line: #d7d1c2;
      --accent: #1f5eff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #f7f3ea 0%, var(--bg) 100%);
      color: var(--ink);
      font: 16px/1.5 Georgia, "Iowan Old Style", serif;
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 80px;
    }}
    h1, h2 {{ margin: 0 0 12px; }}
    h1 {{ font-size: 2rem; }}
    h2 {{ font-size: 1.1rem; }}
    p.meta {{
      color: var(--muted);
      margin: 8px 0 0;
    }}
    .grid {{
      display: grid;
      gap: 16px;
      margin-top: 16px;
    }}
    .grid.two {{
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}
    .grid.members {{
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.04);
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .member .meta {{
      color: var(--accent);
      font: 600 12px/1.2 ui-sans-serif, system-ui, sans-serif;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .pillbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 12px 0 0;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: white;
      font: 12px/1.2 ui-sans-serif, system-ui, sans-serif;
      color: var(--muted);
    }}
    ul {{ margin: 0; padding-left: 18px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 16px;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
    }}
    details summary {{
      cursor: pointer;
      color: var(--accent);
      margin: 10px 0;
      font: 600 12px/1.2 ui-sans-serif, system-ui, sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
  </style>
</head>
<body>
  <main>
    <header class="card">
      <h1>Council Review</h1>
      <p class="meta">Bundle: {_esc(bundle.bundle_id)} · Task cluster: {_esc(bundle.task_cluster_id)}</p>
      <div class="pillbar">
        <span class="pill">Origin provider: {_esc(bundle.origin_provider or "unknown")}</span>
        <span class="pill">Origin session: {_esc(bundle.origin_session_id or "unknown")}</span>
        <span class="pill">Created: {_esc(bundle.created_at)}</span>
      </div>
    </header>

    <section class="card" style="margin-top:16px;">
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

    <section class="card" style="margin-top:16px;">
      <h2>Context Bundle</h2>
      <pre>{_esc(bundle.context_excerpt or "(none)")}</pre>
    </section>

    {summary}
    {peer_reviews}

    <section class="card" style="margin-top:16px;">
      <h2>Member Outputs</h2>
      <div class="grid members">
        {member_cards or '<p class="meta">No council member results recorded yet.</p>'}
      </div>
    </section>
  </main>
</body>
</html>
"""


def write_review_html(bundle: PromptBundle, outcome: CouncilOutcome | None = None) -> Path:
    suffix = outcome.council_run_id if outcome is not None else bundle.bundle_id
    path = review_pages_dir() / f"{suffix}.html"
    path.write_text(render_review_html(bundle, outcome), encoding="utf-8")
    return path
