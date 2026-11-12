# PRODUCT.md

## Product

VideoFlow is a local-first video pre-edit studio. It turns source footage and
script-first pipelines into reviewed cuts, NLE timelines, MP4 masters, and
approval-ready artifacts. Nothing leaves the machine unless the operator
explicitly enables an external provider.

## People

Primary: a solo technical creator or editor who runs repeatable video
workflows on their own machine and wants control over every automated cut,
asset, voice, and render.

Secondary: a small production team reviewing the same run from different
machines on the local network.

## Jobs to be done

1. Start a favorite recipe without opening the graph builder.
2. Know what the run needs and whether the setup is ready before it starts.
3. Review a human gate (approve, answer, upload, or fix) without hunting.
4. Inspect the output: cut, storyboard, voice, scenes, callouts, QA, export.
5. Configure providers, models, services, and paths without guessing.

## Success

- A first-time operator can start a favorite recipe in under one minute.
- A pending gate is visible from every screen.
- The next action is always explicit: start, review, fix, export, or configure.
- A review of one gate takes under two minutes.
- No screen depends on 9–10px text to fit.
- Desktop and mobile both support gate review and artifact inspection.

## Constraints

- Local only by default; external services are opt-in per run.
- Preserve project state, recipe graphs, API contracts, hash routes, test ids,
  keyboard shortcuts, and existing automation.
- Portuguese (pt-BR) and English UI.
- WCAG A/AA, reduced motion, high-contrast theme, keyboard-first workflows.
- The timeline and recipe canvas remain desktop-first; mobile gets a usable
  list/inspection fallback.

## Non-goals

- Cloud collaboration, accounts, or a hosted render farm.
- Replacing a full NLE for frame-level finishing.
- A marketing site or social network.
- Hiding the technical truth of the pipeline behind a consumer wizard.
