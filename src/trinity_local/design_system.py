"""Shared design system CSS from DESIGN.md.

Colors, typography, spacing, and component styles used across all
Trinity HTML pages (portal, council, digest).
"""

COLORS = {
    "bg_base": "#f5efe3",
    "bg_wash": "#ece4d6",
    "surface": "#fbf8f2",
    "surface_muted": "#f1eadf",
    "border": "#d7ccb9",
    "text_primary": "#1f1a17",
    "text_secondary": "#5f554d",
    "text_muted": "#86796d",
    "action_primary": "#255847",
    "action_primary_hover": "#1d4638",
    "action_text": "#f7f3ea",
    "success": "#2d6a4f",
    "warning": "#b26a1f",
    "danger": "#a33c2f",
    "info": "#315c85",
}

SHARED_CSS = """
:root {
  --bg-base: """ + COLORS["bg_base"] + """;
  --bg-wash: """ + COLORS["bg_wash"] + """;
  --surface: """ + COLORS["surface"] + """;
  --surface-muted: """ + COLORS["surface_muted"] + """;
  --border: """ + COLORS["border"] + """;
  --text-primary: """ + COLORS["text_primary"] + """;
  --text-secondary: """ + COLORS["text_secondary"] + """;
  --text-muted: """ + COLORS["text_muted"] + """;
  --action: """ + COLORS["action_primary"] + """;
  --action-hover: """ + COLORS["action_primary_hover"] + """;
  --action-text: """ + COLORS["action_text"] + """;
  --success: """ + COLORS["success"] + """;
  --warning: """ + COLORS["warning"] + """;
  --danger: """ + COLORS["danger"] + """;
  --info: """ + COLORS["info"] + """;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  line-height: 1.55;
  font-size: 16px;
}

main {
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px;
}

@media (max-width: 768px) {
  main {
    padding: 18px;
  }
}

/* Typography */
h1 {
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
  font-size: clamp(38px, 8vw, 56px);
  font-weight: 700;
  line-height: 0.95;
  margin: 0 0 24px 0;
  color: var(--text-primary);
}

h2 {
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
  margin: 0 0 16px 0;
  color: var(--text-primary);
}

@media (max-width: 768px) {
  h2 {
    font-size: 20px;
  }
}

h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: var(--text-primary);
}

p {
  margin: 0 0 12px 0;
  color: var(--text-secondary);
}

.lede {
  font-size: 18px;
}

.eyebrow {
  font-family: "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--action);
  margin: 0 0 8px 0;
}

code, pre {
  font-family: "SF Mono", "JetBrains Mono", "Cascadia Code", monospace;
  font-size: 14px;
  background: var(--surface-muted);
  padding: 2px 6px;
  border-radius: 4px;
}

pre {
  padding: 12px;
  overflow-x: auto;
  margin: 12px 0;
}

/* Layout */
.grid {
  display: grid;
  gap: 24px;
}

.grid-2 {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.grid-cards {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.grid-members {
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.hero {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  align-items: center;
}

@media (max-width: 768px) {
  .hero {
    grid-template-columns: 1fr;
  }
}

/* Shared topbar — sub-pages all use this shape.
   Launchpad is the root and uses the hero pattern instead (no topbar). */
.trinity-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 28px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.trinity-topbar .topbar-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  transition: background 0.12s, border-color 0.12s;
}
.trinity-topbar .topbar-back:hover {
  background: var(--surface-muted);
  border-color: var(--text-muted);
}
.trinity-topbar .topbar-title {
  font-family: "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--text-primary);
  margin: 0;
}
.trinity-topbar .topbar-spacer { flex: 1; }
.trinity-topbar .topbar-action {
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
}
.trinity-topbar .topbar-action:hover {
  background: var(--surface-muted);
  color: var(--text-primary);
}
@media (max-width: 768px) {
  .trinity-topbar { padding: 12px 16px; gap: 10px; }
  .trinity-topbar .topbar-title { font-size: 14px; }
}

/* Cards and surfaces */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 24px;
  box-shadow: 0 10px 30px rgba(57, 44, 26, 0.08);
}

.card-muted {
  background: var(--surface-muted);
}

.member pre {
  font-size: 13px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Buttons */
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px 20px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-primary);
  text-decoration: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s ease;
}

.button:hover {
  border-color: var(--text-secondary);
}

.button.primary {
  background: var(--action);
  color: var(--action-text);
  border-color: var(--action);
}

.button.primary:hover {
  background: var(--action-hover);
  border-color: var(--action-hover);
}

.button.secondary {
  background: var(--surface);
  border-color: var(--border);
}

.button.secondary:hover {
  background: var(--surface-muted);
}

.button.ghost {
  background: transparent;
  border-color: transparent;
  color: var(--action);
}

.button.ghost:hover {
  background: var(--bg-wash);
}

.button.danger {
  background: var(--danger);
  color: white;
  border-color: var(--danger);
}

/* Metadata and secondary info */
.meta {
  font-size: 15px;
  color: var(--text-muted);
  font-family: "SF Pro Text", "Segoe UI", system-ui, sans-serif;
}

.label {
  font-family: "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

/* Status badges */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  background: var(--bg-wash);
  color: var(--text-secondary);
}

.badge.success {
  background: rgba(45, 106, 79, 0.12);
  color: var(--success);
}

.badge.warning {
  background: rgba(178, 106, 31, 0.12);
  color: var(--warning);
}

.badge.danger {
  background: rgba(163, 60, 47, 0.12);
  color: var(--danger);
}

.badge.info {
  background: rgba(49, 92, 133, 0.12);
  color: var(--info);
}

/* Action groups */
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.pillbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 12px 0 0;
}

.pill {
  display: inline-block;
  padding: 4px 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-muted);
}

/* Spacing utilities */
.gap-xs { gap: 4px; }
.gap-sm { gap: 8px; }
.gap-md { gap: 12px; }
.gap-lg { gap: 24px; }
.gap-xl { gap: 32px; }

.mb-xs { margin-bottom: 4px; }
.mb-sm { margin-bottom: 8px; }
.mb-md { margin-bottom: 12px; }
.mb-lg { margin-bottom: 24px; }
.mb-xl { margin-bottom: 32px; }

/* Responsive video/iframe */
.video-container {
  position: relative;
  width: 100%;
  padding-bottom: 56.25%;
  margin: 24px 0;
}

.video-container iframe,
.video-container video {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 14px;
  border: 1px solid var(--border);
}

.video-shell {
  position: relative;
  width: 100%;
  padding-bottom: 56.25%;
}

.video-shell video,
.video-shell iframe {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 14px;
  border: 1px solid var(--border);
}

/* Details/summary */
details {
  margin: 12px 0;
  padding: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
  border-radius: 14px;
}

summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--action);
  user-select: none;
}

details[open] {
  background: var(--surface);
}

/* Utilities */
.text-muted {
  color: var(--text-muted);
}

.text-secondary {
  color: var(--text-secondary);
}

.align-center {
  text-align: center;
}

.align-right {
  text-align: right;
}

.hidden {
  display: none !important;
}

.summary-stat {
  text-align: center;
  padding: 16px;
}

.summary-stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--action);
}

.summary-stat-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-top: 4px;
}

.alert-box {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 0 4px 4px 0;
  color: var(--text-primary);
}

.alert-box.danger {
  background: rgba(163,60,47,0.12);
  border-left: 3px solid var(--danger);
}

.alert-box.success {
  background: rgba(45,106,79,0.12);
  border-left: 3px solid var(--success);
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

th, td {
  text-align: left;
  border-bottom: 1px solid var(--border);
  padding: 8px;
  font-size: 14px;
}

th {
  background: var(--surface-muted);
  font-weight: 600;
}
"""

def render_html_head(title: str = "Trinity", *, extra_head: str = "") -> str:
    """Render <head> with shared CSS and optional extra markup."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
{SHARED_CSS}
  </style>
{extra_head}
</head>
<body>
"""

def render_html_footer() -> str:
    """Render closing tags."""
    return """</body>
</html>
"""
