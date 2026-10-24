# Hardening

## Fault injection

The suite exercises the failure paths that used to be untested:

| Failure | Test | Expected |
| --- | --- | --- |
| Corrupt SQLite file | `test_corrupt_database_reads_as_empty` | reads return empty, no crash |
| Corrupt JSON during migration | `test_migration_survives_a_corrupt_json_file` | import skips the file |
| Output not writable | `test_job_fails_cleanly_when_the_output_is_not_writable` | job ends `failed` with an error |
| Corrupt project state | `test_api_timeline_rejects_a_corrupt_state` | 4xx/5xx, never a fake timeline |
| Provider offline | `test_sandbox_*`, provider fallback tests | typed error or fallback |
| Missing model | `test_missing_whisper_model_is_a_typed_error` | typed error |
| `kill -9` on a running job | `test_sigkill_requeues_the_running_job` | job requeued and completed |
| Disk full (ENOSPC) | `test_disk_full_fails_an_export_without_a_success_marker` | failed, no success marker |
| Provider offline | `test_offline_provider_falls_back_to_the_next` | fallback provider answers |

A failed operation never writes a success result: the job error is set before
the status changes, and partial render/preview files are removed on cancel.

## Log rotation

`application/services.py:rotate_log` keeps `server.log` under 4 MB and retains
`server.log.1` and `server.log.2`. `append_server_log` rotates before writing.

## Scheduled backups

`application/backups.py` writes `backups/videoflow-YYYYMMDD-HHMMSS.zip` through
`database.backup`, then prunes everything beyond `keep` (default 7). Enable it
at startup with:

```bash
VIDEOWFLOW_BACKUP_ON_START=1 videoflow-api
```

On demand:

```http
POST /api/v1/maintenance/backup
```

The backup is a consistent SQLite snapshot plus the settings files.

## Accessibility

- `:focus-visible` outlines every interactive element with sky-400.
- Command palette, notification center, activity drawer, and shortcut reference
  trap Tab focus (`ui/src/lib/a11y.ts`) and restore focus when the palette
  closes.
- `prefers-reduced-motion` disables animations and transitions.
- Playwright runs keyboard-only flows: `Ctrl/Cmd+K`, Tab inside the palette,
  `g`-prefixed jumps, the shortcut reference, and Escape.
- `aria-live` regions carry notification and activity updates; dialogs declare
  `aria-modal` and a label.

The AA target is covered by keyboard operation, visible focus, live regions,
reduced motion, and labelled controls. Screen-reader passes and 200% zoom remain
manual checklist items.

## Crash reports and cost

Unhandled API errors write `<home>/crash-reports/crash-*.json` with the exception,
a bounded traceback, and only version/python/platform/machine. No environment
variables or secrets are copied. `GET /api/v1/metrics/cost` returns call and
token totals per model; no price table is guessed.

## Large timelines

`tests/unit/test_performance.py` builds 1,000 clips and exports FCPXML, XMEML,
and Kdenlive; each writer must finish under ten seconds (they finish in well
under one second on the development host). A Playwright scroll test with 200
clips and 1,000 captions measures **17 ms/frame on an idle host** and ~25 ms at
load average 10, after thumbnail caching, one caption shape, visible-only audio
bars, and banded redraws. The canvas draws only the visible window plus one
viewport of margin when the clip count exceeds 300; smaller timelines are drawn
once and rely on native scrolling.

## Schema freeze

`tests/contract/test_schemas.py` regenerates every committed schema and fails on
drift. `tests/unit/test_operational_store.py:test_schema_1x_home_migrates_to_2x`
opens a `schema_version=1` database, migrates it, and checks that rows and
defaults survive.
