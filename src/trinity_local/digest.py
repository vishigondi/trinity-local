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
from .drift import DriftAlert, check_drift
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
    path = trinity_home() / "digest_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_digest_html(digest: WeeklyDigest) -> Path:
    """Render the digest as a static HTML page."""
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>Trinity Local — Weekly Digest</title>")
    parts.append("<style>")
    parts.append("""
        :root { --bg: #0d1117; --card: #161b22; --text: #c9d1d9; --accent: #58a6ff;
                --green: #3fb950; --red: #f85149; --border: #30363d; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
               background: var(--bg); color: var(--text); padding: 2rem; max-width: 800px; margin: 0 auto; }
        h1 { color: var(--accent); margin-bottom: 0.5rem; }
        .meta { color: #8b949e; margin-bottom: 2rem; }
        .card { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
                padding: 1rem; margin-bottom: 1rem; }
        .card h3 { color: var(--accent); margin-bottom: 0.5rem; }
        .stat { display: inline-block; margin-right: 1.5rem; }
        .stat-value { font-size: 1.5rem; font-weight: 600; }
        .stat-label { color: #8b949e; font-size: 0.85rem; }
        .alert { background: #f8514922; border-left: 3px solid var(--red); padding: 0.75rem 1rem; margin-bottom: 0.5rem; border-radius: 0 6px 6px 0; }
        .best-kind { display: inline-block; background: #3fb95022; color: var(--green); padding: 2px 8px;
                     border-radius: 12px; font-size: 0.8rem; margin: 2px; }
        .summary { display: flex; gap: 2rem; margin-bottom: 2rem; flex-wrap: wrap; }
    """)
    parts.append("</style></head><body>")
    parts.append("<h1>📊 Weekly Digest</h1>")
    parts.append(f'<p class="meta">Generated {digest.generated_at} · Past {digest.period_days} days</p>')

    # Summary cards
    parts.append('<div class="summary">')
    parts.append(f'<div class="stat"><div class="stat-value">{digest.total_sessions}</div><div class="stat-label">Total Sessions</div></div>')
    parts.append(f'<div class="stat"><div class="stat-value">${digest.total_cost_usd:.2f}</div><div class="stat-label">Estimated Cost</div></div>')
    parts.append(f'<div class="stat"><div class="stat-value">{len(digest.drift_alerts)}</div><div class="stat-label">Drift Alerts</div></div>')
    parts.append('</div>')

    # Per-provider cards
    for entry in digest.entries:
        parts.append('<div class="card">')
        parts.append(f"<h3>{entry.provider}</h3>")
        parts.append(f'<span class="stat"><span class="stat-value">{entry.sessions}</span> <span class="stat-label">sessions</span></span>')
        parts.append(f'<span class="stat"><span class="stat-value">${entry.total_cost_usd:.2f}</span> <span class="stat-label">cost</span></span>')
        if entry.best_task_kinds:
            parts.append("<div style='margin-top:0.5rem'>Best for: ")
            for kind in entry.best_task_kinds:
                parts.append(f'<span class="best-kind">{kind}</span>')
            parts.append("</div>")
        parts.append("</div>")

    # Drift alerts
    if digest.drift_alerts:
        parts.append("<h2 style='margin:1.5rem 0 0.75rem;color:var(--red)'>⚠️ Drift Alerts</h2>")
        for alert in digest.drift_alerts:
            parts.append(f'<div class="alert">{alert.message}</div>')

    parts.append("</body></html>")

    html = "\n".join(parts)
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
