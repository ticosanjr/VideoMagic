# Accessibility QA checklist

Automated coverage: Playwright keyboard, focus trap, narrow viewport, PT-BR
locale, reduced motion, axe WCAG A/AA, mobile builder, mobile timeline, HITL
inbox, and both workspace overviews. A human still signs the manual pass before
3.0.

Latest automated run (2026-11-13): 113 Playwright passed, 1 skipped; 99 Vitest
passed; svelte-check 0 errors; visual baselines for shell desktop/mobile,
mobile builder, mobile timeline, HITL inbox, and Synthetic/Footage workspaces.
The machine has Orca 46.1 on `DISPLAY=:20`. Evidence bundle:
`docs/qa-evidence/qa-20261113T113812Z.{json,md}`.

## Environment

- OS: Linux
- Display: `:20`
- Screen reader: Orca (`/usr/bin/orca`)
- Browser zoom: 100%, 200%
- Theme: dark and light, comfortable and compact density

## Checklist

| # | Check | Evidence | Signed |
| --- | --- | --- | --- |
| 1 | Area and sub-tab tablists move with arrows, Home, and End | Playwright + manual | pending |
| 2 | Command palette traps focus and restores it on close | Playwright + manual | pending |
| 3 | Shortcuts modal traps focus and closes with Escape | Playwright + manual | pending |
| 4 | Every destructive action is reachable without a mouse | manual | pending |
| 5 | Status, progress, and errors are announced by Orca | manual | pending |
| 6 | Timeline clips, track headers, and context menu are operable by keyboard | manual | pending |
| 7 | 200% zoom keeps Produce/Edit/Runs/Library/Setup usable | manual | pending |
| 8 | 480px viewport keeps navigation and primary actions visible | Playwright + manual | pending |
| 9 | Light theme contrast passes on text, borders, and badges | manual | pending |
| 10 | `prefers-reduced-motion` disables non-essential animation | automated + manual | pending |
| 11 | Assistant plan, diff, and approval are understandable without colour | manual | pending |
| 12 | Focus is visible on inputs, buttons, tabs, and canvas controls | manual | pending |

## Sign-off

- Reviewer:
- Date:
- Build: `releases/v2.72.0/videoflow-2.72.0-linux-x86_64`
- Result: pending

A signed copy is required before 3.0. Fixes for P0/P1 block the release.
