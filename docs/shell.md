# Professional shell

The 2.1.0 shell keeps every critical action reachable from the keyboard and
makes job state visible without leaving the current tab. Everything is local:
the shortcuts drive the same REST endpoints the panels use.

## Command palette

Open with `Ctrl/Cmd+K`. Type to filter; `Up`/`Down` move the selection and
`Enter` runs it. Commands include:

- open any workspace tab;
- open the notification center or the activity drawer;
- show the shortcut reference;
- refresh the jobs snapshot;
- download the support bundle;
- cancel a running or queued job;
- retry a failed or cancelled job.

Matching is ranked: title prefix first, then title substring, then keywords and
hints. The ranking lives in `ui/src/lib/commandPalette.ts` and is covered by
Vitest.

## Shortcuts

| Keys | Action |
| --- | --- |
| `Ctrl/Cmd+K` | Command palette |
| `?` | Shortcut reference |
| `Esc` | Close the palette, drawer, modal, or notification center |
| `g` then `r` | Produce · Recipes |
| `g` then `d` | Produce · Lamera |
| `g` then `c` | Produce · Assistant |
| `g` then `t` | Edit · Timeline |
| `g` then `j` | Runs · Jobs |
| `g` then `u` | Runs · Schedules |
| `g` then `a` | Library · Media |
| `g` then `l` | Library · Brand |
| `g` then `m` | Setup · AI models |
| `g` then `v` | Setup · Local services |
| `g` then `p` | Setup · AI providers |
| `g` then `e` | Setup · Extensions |
| `g` then `i` | Setup · Connect |
| `g` then `s` | Setup · Settings |
| `n` | Notification center |
| `u` | Activity drawer |

Global shortcuts are ignored while an input, textarea, select, or contenteditable
element has focus, so typing a query never switches tabs.

## Notification center

Notices carry a kind (`info`, `success`, `warning`, `error`), a title and
message, an optional error code, and an optional action. Errors and warnings are
persistent by default. The sort order is severity first, then newest first, so
an error never hides behind a success. The pure rules live in
`ui/src/lib/notifications.ts`; the reactive store lives in
`ui/src/lib/notifications.svelte.ts`.

The shell banner still surfaces service-level failures. Notices add history and
actions on top of it.

## Activity drawer

The drawer shows four buckets from the current jobs snapshot:

1. needs attention (approval pending or failed);
2. running;
3. queued;
4. recently finished.

Each entry shows the source name, the current message, the next action, and the
creation time. The footer jumps to the job dashboard.

## Areas

The shell has five primary areas: **Produce** (Recipes, Lamera, Assistant), **Edit**
(Timeline), **Runs** (Jobs, Schedules), **Library** (Media, Brand library), and
**Setup** (AI models, AI providers, Local services, Extensions, Connect,
Settings). Flat hashes (`#recipes`, `#timeline`, …) are canonical; legacy
hashes redirect. The breadcrumb shows the area and the current tab.

## Runs dashboard

The Runs · Jobs tab polls `GET /api/v1/jobs` every four seconds while mounted. It shows:

- bucket counts and a text search over id, status, stage, message, source, and
  recipe;
- status badge, progress, stage message, elapsed time, and inline error;
- the next action for that job;
- guarded cancel for queued or running jobs (`Cancel` then `Confirm cancel`);
- retry for failed or cancelled jobs;
- a link to the timeline for succeeded jobs with artifacts.

Filtering and next-action copy live in `ui/src/lib/jobsView.ts` and are covered
by Vitest.

## Idempotency

`POST /api/v1/recipes/run` accepts `idempotency_key`.
While the matching job is `queued`, `running`, or `waiting_approval`, the
request returns that job. Terminal jobs release the key. The check is in-memory
inside the single local process and the key is persisted with the job, so a
restart re-queues the same job instead of spawning a duplicate.

## Retry contract

`POST /api/v1/jobs/{job_id}/retry`

- accepts `failed` and `cancelled` jobs only;
- re-enqueues with the original source, output, and options plus `resume: true`;
- returns `202` with the new job;
- returns `409 state_not_ready` for any other status;
- returns `404` for an unknown job.

## Cancellation contract

`FFmpegAdapter` starts FFmpeg with `Popen(..., start_new_session=True)`, polls
`communicate(timeout=0.2)`, and sends `SIGTERM` to the process group followed by
`SIGKILL` after one second. The render and preview managers pass a
`threading.Event`, so `cancel()` stops the current FFmpeg process instead of
waiting for the next stage, and the partial file is removed.

## Testing

- Vitest: command ranking, job filtering/counts/next action, notice creation,
  ordering, and counts.
- Playwright: palette open/navigate/close, shortcut reference, `g`-prefixed
  jumps, activity drawer, notification center, job filtering, and guarded
  cancel.
- Python: FFmpeg timeout/cancel via `Popen`, render and preview cancellation
  cleanup, SQLite-first loading, requeue after restart, stale JSON, migration,
  and the retry endpoints.
