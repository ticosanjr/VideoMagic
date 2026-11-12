# DESIGN.md

## Identity

VideoFlow is a local control room: calm, precise, technical, and made for
people who care about the cut. It should feel like a professional tool that
stays out of the way, not a generic SaaS dashboard.

References: editing suites, broadcast control surfaces, terminal tools, and
technical documentation. Avoid decorative AI-dashboard tropes.

## Principles

1. **The next action is obvious.** One primary action per screen, always in the
   same place.
2. **Favorites first.** The most-used recipes are visible, not hidden in a modal.
3. **Review is work.** HITL is a first-class screen with artifacts, context, and
   a clear decision bar.
4. **Density with air.** Keep the information, remove the noise. Never use tiny
   type to make a layout fit.
5. **Local truth.** Show what is local, what needs a provider, and what is
   blocked before the run starts.

## Type

Use the system sans stack. Minimum readable size is 12px for metadata; body is
13–14px.

| Token | Size | Use |
|---|---:|---|
| `--vf-text-2xs` | 11px | timestamps, dense badges only |
| `--vf-text-xs` | 12px | metadata, helper text, table labels |
| `--vf-text-sm` | 13px | controls, secondary body |
| `--vf-text-base` | 14px | body |
| `--vf-text-lg` | 16px | section titles |
| `--vf-text-xl` | 20px | page titles |
| `--vf-text-2xl` | 26px | workspace hero |

Line heights: 1.35 for dense metadata, 1.5 for body, 1.1 for display.

## Color

One primary accent (sky/cyan) and semantic colors only. Phase colors are
reserved for recipe phase identity, never for general decoration.

- Background: `--vf-bg`
- Surface: `--vf-surface`, `--vf-surface-2`
- Border: `--vf-border`, `--vf-border-strong`
- Text: `--vf-text`, `--vf-muted`
- Accent: `--vf-accent`, `--vf-accent-soft`
- Semantic: success, warning, danger, info

Contrast must meet AA at the rendered size. Do not use color alone for status.

## Layout

- Desktop: 64–76px area rail + 232–260px contextual sidebar + fluid workspace.
- Header: context and search at left; review queue, activity, theme, and service
  status at right.
- Active-run bar: one compact row under the header.
- Mobile: area rail becomes a horizontal scroll row; contextual tabs become a
  second row or select; content is single column.
- Maximum content width: 1680px for builder/timeline, 1440px for forms.

## Surfaces and shape

Three levels only: page background, panel, and raised control. Borders are 1px.
Radii: 8px controls, 12px panels, 16px dialogs. Shadows only for overlays and
sticky bars.

## Components

- Buttons: 32px desktop, 40px mobile; primary filled accent; secondary outlined.
- Inputs: 36–40px; label above; helper below; error replaces helper.
- Cards: title, one-line description, status, one primary action. No nested
  card stacks.
- Empty states: what this is, why it matters, one action.
- Tables: sticky header, row hover, card fallback below 768px.
- Tabs: active state uses text + underline/left bar, not color alone.

## Motion

120–180ms for state changes; 220ms for overlays. No looping decorative motion.
Respect `prefers-reduced-motion`.

## Bans

- Decorative grid or line-field backgrounds outside a real canvas.
- 8–10px body text.
- Nested cards and card grids used as the default layout.
- Gradient text, glowing borders, or rainbow accents for decoration.
- More than one primary button in a view.
- Hiding a primary workflow behind a modal.

## Implementation

Tokens live in `ui/src/design/tokens.css` and are imported by `app.css`. Shared
components in `ui/src/lib/ui` consume tokens only; panels migrate incrementally
without changing their test ids or routes.
