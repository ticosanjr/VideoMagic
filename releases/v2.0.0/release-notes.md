# VideoFlow 2.0.0 (local edition)

Local-only, loopback-only automation studio. Distribution, publishing, and
multiuser use are out of scope.

## Highlights

- Human gate UI with approve/reject and checkpoint resume.
- Persistent priority job queue with restart requeue.
- Scheduler job reconciliation.
- Variant comparison and analytics-weighted Short scoring.
- Real audio onset/beat detection and music/SFX mixing in Shorts.
- Dubbing step for localized Shorts with TTS.
- TF-IDF B-roll matching over assets and transcript.
- Real thumbnail variants and winner selection.
- Library CRUD for music, images, and fonts.
- SQLite migration for jobs/assets/batches with WAL, backup, and restore.
- Plugin step loader.
- Settings Hub, provider fallbacks, secrets, model manager, managed services,
  diagnostics, and support bundle.
- 34 built-in recipes.
- 485 Python tests, 8 media tests, 13 Vitest tests, 19 Playwright tests.

## Scope

Out of scope by request: distribution, publishing, multiuser/collaboration,
Windows local build, macOS, signing, and auto-update.

## Known limitations

- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA still
  required.
- Plugin SDK v1 covers steps, not providers/exporters/UI panels.
- SQLite is an operational index; JSON remains canonical for jobs/assets.
- Full UI i18n and per-clip waveforms remain future work.
- Render cancellation stops between stages, not mid-process.
