# VideoFlow 1.0.0 (local stable)

Local-first, loopback-only video automation studio. Built locally on Linux;
GitHub Actions is not used.

## Highlights

- Recipe variables, expressions, profiles, dry-run, variants, map/reduce,
  subflows, error policies, and human approval gates.
- 34 built-in recipes for rough cuts, captions, NLE export, clean audio,
  chapters, Shorts selection/render, best moments, trailer, review, variants,
  podcast/interview/webinar/lecture/product/testimonial/livestream, B-roll,
  music, SFX, metadata, thumbnails, publishing, analytics, localization, and
  finishing.
- Multifactor Short scoring with analytics weights, diversity filtering,
  selection reports, and optional LLM re-rank.
- Real audio onset/beat detection, music/SFX mixing in Shorts, audio QA, and
  thumbnail A/B winner selection.
- Persistent priority job queue with restart requeue and scheduler job
  reconciliation.
- Canvas timeline with multi-select, batch edits, markers, track mute/solo/lock,
  clip thumbnails, preview/render queues, transitions, fades, and undo/redo.
- Settings Hub, provider fallbacks, secrets, model manager, managed services,
  library, and diagnostics 2.0.
- SQLite WAL indices, backup/restore, metrics, plugin steps, and support bundle.
- 484 Python tests, 8 media tests, 13 Vitest tests, 19 Playwright tests.

## Scope

Out of scope: distribution, signing, macOS, Windows local builds, and
collaboration.

## Known limitations

- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA still
  required.
- Plugin SDK v1 covers steps only.
- SQLite is an operational index; JSON remains canonical for jobs/assets.
- Full UI i18n and per-clip waveforms remain future work.
