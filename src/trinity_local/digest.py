"""Weekly digest generation.

Aggregates the past 7 days of activity: sessions per provider, costs,
best provider per task kind, drift alerts, and workflow suggestions.
Outputs as static HTML and/or macOS notification.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import trinity_home
from .cost_tracker import CostSummary, load_cost_log, summarize_costs
from .design_system import render_html_footer, render_html_head
from .drift import DriftAlert, check_drift
from .state_paths import digest_pages_dir
from .utils import now_iso


@dataclass
class DigestEntry:
    """One provider's summary for the digest."""
    provider: str
    sessions: int = 0
    total_cost_usd: float = 0.0
    best_task_kinds: list[str] = field(default_factory=list)


@dataclass
class WeeklyDigest:
    """Complete weekly digest data."""
    generated_at: str = ""
    period_days: int = 7
    entries: list[DigestEntry] = field(default_factory=list)
    drift_alerts: list[DriftAlert] = field(default_factory=list)
    total_sessions: int = 0
    total_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "period_days": self.period_days,
            "total_sessions": self.total_sessions,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "entries": [asdict(e) for e in self.entries],
            "drift_alerts": [a.to_dict() for a in self.drift_alerts],
        }


def generate_digest(*, period_days: int = 7) -> WeeklyDigest:
    """Generate a weekly digest from cost log and drift detection."""
    costs = load_cost_log(since_days=period_days)
    summaries = summarize_costs(costs)
    drift_alerts = check_drift(current_window_days=period_days)

    # Determine best provider per task kind
    task_kind_best: dict[str, tuple[str, float]] = {}
    for provider, summary in summaries.items():
        for task_kind, cost in summary.by_task_kind.items():
            # "Best" = most sessions at lowest cost (simplistic — will improve in Phase 4)
            if task_kind not in task_kind_best:
                task_kind_best[task_kind] = (provider, summary.sessions)

    entries: list[DigestEntry] = []
    for provider, summary in sorted(summaries.items()):
        best_kinds = [
            tk for tk, (p, _) in task_kind_best.items() if p == provider
        ]
        entries.append(DigestEntry(
            provider=provider,
            sessions=summary.sessions,
            total_cost_usd=summary.total_cost_usd,
            best_task_kinds=best_kinds,
        ))

    return WeeklyDigest(
        generated_at=now_iso(),
        period_days=period_days,
        entries=entries,
        drift_alerts=drift_alerts,
        total_sessions=sum(e.sessions for e in entries),
        total_cost_usd=round(sum(e.total_cost_usd for e in entries), 4),
    )


def _digest_pages_dir() -> Path:
    """Deprecated — use state_paths.digest_pages_dir() instead."""
    return digest_pages_dir()


def render_digest_html(digest: WeeklyDigest) -> Path:
    """Render the digest as a static HTML page."""
    head = render_html_head("Trinity — Weekly Digest")
    footer = render_html_footer()

    # Per-provider cards
    provider_cards = []
    for entry in digest.entries:
        best_kinds = ""
        if entry.best_task_kinds:
            badges = "\n".join(f'<span class="badge">{kind}</span>' for kind in entry.best_task_kinds)
            best_kinds = f'<div class="mb-md"><strong>Best for:</strong><div class="actions gap-sm" style="margin-top:8px;">{badges}</div></div>'
        provider_cards.append(f"""
            <section class="card">
              <h3>{entry.provider}</h3>
              <div class="meta">
                <strong>{entry.sessions}</strong> sessions ·
                <strong>${entry.total_cost_usd:.2f}</strong> estimated cost
              </div>
              {best_kinds}
            </section>
            """)

    # Drift alerts
    drift_section = ""
    if digest.drift_alerts:
        alerts = "\n".join(
            f'<div class="alert-box danger">{alert.message}</div>'
            for alert in digest.drift_alerts
        )
        drift_section = f"""
        <section class="card mb-lg">
          <h2>Drift Alerts</h2>
          {alerts}
        </section>
        """

    html = f"""{head}
  <main>
    <section class="card">
      <div class="eyebrow">Trinity</div>
      <h1>Weekly Digest</h1>
      <p class="lede">Generated {digest.generated_at} · Past {digest.period_days} days</p>
    </section>

    <section class="grid grid-cards">
      <div class="summary-stat">
        <div class="summary-stat-value">{digest.total_sessions}</div>
        <div class="summary-stat-label">Total Sessions</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-value">${digest.total_cost_usd:.2f}</div>
        <div class="summary-stat-label">Estimated Cost</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-value">{len(digest.drift_alerts)}</div>
        <div class="summary-stat-label">Drift Alerts</div>
      </div>
    </section>

    <section class="card mb-lg">
      <h2>Provider Summary</h2>
      <div class="grid grid-cards">
        {''.join(provider_cards)}
      </div>
    </section>

    {drift_section}
  </main>
{footer}
"""

    out_path = _digest_pages_dir() / "digest.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def render_digest_notification(digest: WeeklyDigest) -> str:
    """Render a compact notification string from the digest."""
    lines: list[str] = []
    lines.append(f"Trinity Weekly: {digest.total_sessions} sessions, ~${digest.total_cost_usd:.2f}")
    for entry in digest.entries:
        best = f" (best: {', '.join(entry.best_task_kinds)})" if entry.best_task_kinds else ""
        lines.append(f"  {entry.provider}: {entry.sessions} sessions, ${entry.total_cost_usd:.2f}{best}")
    if digest.drift_alerts:
        lines.append(f"  ⚠ {len(digest.drift_alerts)} drift alert(s)")
        for alert in digest.drift_alerts[:2]:
            lines.append(f"    {alert.message}")
    return "\n".join(lines)
