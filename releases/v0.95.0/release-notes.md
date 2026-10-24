# VideoFlow 0.95.0 release candidate

Local-first release candidate built locally on Linux. GitHub Actions is not
used.

## Recipes

- Typed variables, expressions, profiles, and dry-run.
- Recipe variants into named output folders.
- Map, reduce, subflows, and per-item error policies.
- Human approval gates with `waiting_approval` and resume.
- 34 built-in recipes covering rough cut, captions, NLE export, clean audio,
  chapters, Shorts selection/render, best moments, trailer, review, variants,
  podcast/interview/webinar/lecture/product/testimonial/livestream, B-roll,
  music, SFX, metadata, thumbnails, publishing, analytics, localization, and
  finishing.

## Shorts quality

- Multifactor scoring: completeness, payoff, hook, CTA, speaker balance, and
  duration fit.
- Diversity filter and optional LLM re-rank.
- Scoring profiles: default, hook, education, podcast.

## Assets and delivery

- Shot detection and thumbnails.
- Semantic B-roll matching.
- Beat grid and SFX planning.
- Metadata pack, thumbnail pack, publish queue, analytics review, experiment
  evaluation, chapters, and NLE QA.

## Platform

- SQLite WAL index for jobs, assets, and batches.
- Backup bundle and metrics endpoints.
- Plugin SDK v1 for custom steps.
- Settings wiring for models/speech/quality/translation/proxy/runtime.
- Library and EN/PT-BR navigation strings.
- Diagnostics 2.0 with FFmpeg capabilities, CUDA/ONNX, SQLite integrity,
  providers, services, models, metrics, and support bundle.

## Validation

- 477 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.
- Linux binary and AppImage verified locally.

## Notes

- Distribution, signing, macOS, Windows local builds, and collaboration remain
  out of scope.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA is still
  required.
- Per-clip waveform rendering remains future work.
