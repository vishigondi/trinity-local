# Trinity Design System

## Overview

Trinity is a local intelligence layer, not a SaaS dashboard. The UI should feel calm, trustworthy, and slightly editorial: more like a well-designed field notebook or control desk than an analytics product. Favor legibility, hierarchy, and restraint over visual novelty.

The primary surfaces are static HTML pages opened locally in the browser:
- **Launchpad** (autofill suggestions; personal routing table card with provider scores per `task_type`; **pair-wise `/me` lenses card with copy-to-socials buttons** — title + why-it-matters per principle, no verbatim prompts; recent councils)
- **Unified council page** — single page handling both in-flight (`?status_token=...`) and post-hoc (`?council_id=...`) views. Member responses stream as each finishes; chairman synthesis status; structured Routing label section; per-member rating buttons (the rating interaction lives inside this page, not a separate Signal/Rating page)
- Future surfaces: weekly Elo report (deferred); local leaderboard view over `compute_personal_routing_table()` (currently rendered as the launchpad card)

These surfaces share one visual language so the product feels cohesive even though the pages are generated independently. The `/me` lens cards are the **shareable social artifact** — pair-wise model/user context stays local for the chairman; only the principle (title + why-it-matters) ships to clipboard.

## Frontend Stack Contract

Trinity’s frontend stack is:

- **static HTML** for structure and artifact durability
- **`petite-vue`** for interactive islands
- **`Chart.js`** for radar, Elo, and report visuals

Design choices should assume:

- pages open from disk
- pages may be bookmarked and reopened later
- interaction is page-local, not SPA-global
- visuals may need to be screenshotable and shareable

## Visual Theme

- Tone: grounded, intelligent, high-trust, local-first
- Density: medium to airy
- Layout feel: document-first, not dashboard-first
- Motion: minimal; prefer static clarity over animated ornament
- Atmosphere: warm paper background, dark ink text, subtle depth

## Color Palette

### Core roles

- Background base: `#f5efe3`
- Background wash: `#ece4d6`
- Surface: `#fbf8f2`
- Surface muted: `#f1eadf`
- Border: `#d7ccb9`
- Text primary: `#1f1a17`
- Text secondary: `#5f554d`
- Text muted: `#86796d`
- Primary action: `#255847`
- Primary action hover: `#1d4638`
- Primary action text: `#f7f3ea`
- Accent warm: `#b57438`
- Success: `#2d6a4f`
- Warning: `#b26a1f`
- Danger: `#a33c2f`
- Info: `#315c85`

### Usage rules

- Use the green family only for primary actions and active confirmation states.
- Use the warm accent sparingly for emphasis, highlights, or section markers.
- Avoid introducing additional saturated colors unless they encode status.
- Prefer contrast through ink, paper, and border relationships before using color.

## Typography

### Font stacks

- Display serif: `"Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif`
- UI sans: `"SF Pro Text", "Segoe UI", system-ui, sans-serif`
- Monospace: `"SF Mono", "JetBrains Mono", "Cascadia Code", monospace`

### Hierarchy

- Eyebrow / label:
  - Font: UI sans
  - Size: 12px
  - Weight: 700
  - Case: uppercase
  - Letter spacing: 0.14em
- Page title:
  - Font: display serif
  - Size: 56px desktop / 38px mobile
  - Weight: 700
  - Line height: 0.95 to 1.0
- Section title:
  - Font: display serif
  - Size: 24px desktop / 20px mobile
  - Weight: 700
  - Line height: 1.1
- Body:
  - Font: UI sans
  - Size: 18px desktop / 16px mobile
  - Weight: 400
  - Line height: 1.55
- Secondary body:
  - Font: UI sans
  - Size: 15px
  - Weight: 400
  - Line height: 1.5
- Code / paths / commands:
  - Font: monospace
  - Size: 14px

### Typography rules

- Use the serif only for page titles and section titles.
- Use sans for all explanatory copy, metadata, buttons, and labels.
- Do not mix more than two font families on a page.

## Spacing and Layout

### Spacing scale

- 4px
- 8px
- 12px
- 16px
- 24px
- 32px
- 48px
- 64px

### Layout principles

- Center a single primary column with generous outer padding.
- Prefer stacked sections over multi-panel dashboard grids.
- Use width to create calm, not to cram more controls on screen.
- Keep action groups close to the content they affect.

### Container rules

- Max content width: `1080px`
- Default page padding: `32px`
- Mobile page padding: `18px`
- Section gap: `24px` to `36px`

## Shapes and Elevation

- Large card radius: `24px`
- Medium control radius: `14px`
- Small radius: `10px`

### Elevation

- Cards should use soft, low-contrast shadows:
  - `0 10px 30px rgba(57, 44, 26, 0.08)`
- Borders should remain visible even when shadows are present.
- Avoid harsh dark shadows or glassmorphism effects.

## Components

### Page shell

- Warm gradient or paper-like wash background is allowed, but subtle.
- Content should sit on light surfaces with strong readable contrast.
- Top-of-page identity should be clear and stable across all generated pages.

### Primary button

- Filled with primary action green
- Light text
- Rounded pill or soft capsule
- Strong enough to anchor the page visually

### Secondary button

- Surface-colored fill or near-white fill
- Border visible
- Text in primary ink
- Must read as secondary, not disabled

### Action cards

- This is the most important Trinity component.
- Each card should show:
  - action title
  - brief rationale
  - source/provider or task metadata
  - one clear primary CTA
- Use stronger visual emphasis for the primary action card than for supporting content.

### Status cards

- Used for “No pending actions”, health summaries, or passive information.
- Quieter than action cards.
- Should never visually compete with a real action.

### Metadata rows

- Use compact sans text
- Muted color
- Prefer one-line summaries over verbose labels

## Launchpad Guidance

- The launchpad is a local action surface, not an app homepage.
- Keep the page short and scannable.
- Put pending actions ahead of explanatory prose.
- If there are no actions, make the empty state calm and concise.
- Avoid long onboarding text once the core setup is complete.

## Council Review Guidance

- Lead with:
  - task
  - recommendation / winner
  - agreement
  - differences
- Raw model outputs should be expandable or visually subordinate.
- The primary decision should be obvious without scrolling far.

## Council Rating Interaction

The rating UI lives **inside the unified council review page**, not a separate Signal page. Inline guidance:

- Answer cards are equally weighted until the user selects a winner.
- Confirmation state should feel rewarding but not gamified.
- Selecting a winner fires `record_outcome` (via the launchpad shortcut dispatch) which updates `CouncilOutcome.metadata.user_verdict` and propagates to the originating `PromptNode`.
- Disagreed-claims block reads as a passage, not a table — the structured Routing JSON is the substrate, the prose is the experience.

## Chart Guidance

- Charts only when they add immediate comprehension.
- Favor:
  - compact bar charts (provider scores per task_type on the personal routing table card)
  - simple line charts (Elo trajectory)
- Avoid chart junk, legends that dominate the page, or analyst-dashboard density.
- Charts inherit the paper-and-ink visual language:
  - muted gridlines
  - dark labels
  - restrained accent palette

## Social Artifact Guidance

The shipped social artifact is the **`/me` lens card** — title + why-it-matters per principle, copyable to socials with one click.

- Per-card Copy emits one principle as a short, paste-ready block.
- Section-level "Copy all" emits every principle in one bundle, headed with "The principles I encode by what I redirect away from:".
- Verbatim model/user prompt content is **never** in the share text — it stays local for the chairman.
- Cards should read clearly in a crop; supporting copy is short.

(Future surfaces — radar/battle/taste-profile pages — are deferred. The /me lens cards subsume the "shareable taste artifact" use case for now.)

## Responsive Behavior

- Collapse to a single-column layout on narrow screens.
- Maintain strong title presence on mobile, but reduce size and spacing.
- Buttons should remain finger-friendly.
- Do not rely on hover-only affordances.

## Do

- Use strong hierarchy and quiet surfaces.
- Make actions obvious.
- Keep the overall tone warm and local, not corporate SaaS.
- Let whitespace create clarity.
- Favor summary-first layouts.

## Do Not

- Do not use generic Tailwind-blue product styling.
- Do not turn pages into dashboard widget grids by default.
- Do not overload the page with explanatory copy.
- Do not introduce purple or neon accents.
- Do not use heavy gradients, frosted glass, or loud AI-brand visuals.
- Do not make everything look interactive; reserve emphasis for true actions.
