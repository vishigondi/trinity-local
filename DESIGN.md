# Trinity Design System

## Overview

Trinity is a local intelligence layer, not a SaaS dashboard. The UI should feel calm, trustworthy, and slightly editorial: more like a well-designed field notebook or control desk than an analytics product. Favor legibility, hierarchy, and restraint over visual novelty.

The primary surfaces are static HTML pages opened locally in the browser:
- Launchpad
- Council review pages
- Weekly digest pages

These surfaces should share one visual language so the product feels cohesive even though the pages are generated independently.

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

## Digest Guidance

- Treat digest pages like editorial summaries.
- Use stronger sectioning and narrative sequencing than the launchpad.
- Emphasize trends, switches, and meaningful deltas over raw counts.

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
