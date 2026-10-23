# Recipe studio and timeline UI specification

Stack: SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript, Konva, and
wavesurfer.js. English strings only.

0.80.0 removes the legacy rack. The product is a recipe studio with a
professional canvas timeline, automation schedules, and provider settings.
Errors are persistent, sticky banners at the top of the page or panel; inline
field validation remains next to the field.

## 1. Layout

```
┌──────────────────────────────────────────────────────────────┐
│ VideoFlow  recipe studio       server/ui versions   restart  │
├──────────────────────────────────────────────────────────────┤
│ Recipes  Assets  Timeline  Models  Services  Providers       │
├──────────────────────────────────────────────────────────────┤
│ [sticky error banner when the last action fails]             │
│                                                              │
│ Active workspace                                             │
└──────────────────────────────────────────────────────────────┘
```

There is no project creation wizard, no module rack, and no global run form.
Recipes own execution; the timeline owns editing. The filesystem picker is a
modal utility.

## 2. Error contract

- One `ErrorBanner` component renders `role="alert"` and
  `aria-live="assertive"`.
- The banner is sticky at the top of the active panel and includes a copy
  diagnostics action and a dismiss action.
- Errors are never rendered below the content they belong to.
- Toasts are reserved for transient success or failure notifications.
- The timeline panel surfaces API errors through `testId="timeline-error"`.

## 3. Recipes

- Svelte Flow DAG editor with inline node fields and a JSON escape hatch.
- Per-step progress, cached/executed/skipped status, logs, and NLE validation.
- Undo/redo for structural edits, saved layout, node width cycling, and pinning.
- Recipe template gallery, save-as, version history, and restore.
- Batch tab with persisted history and resume.
- Flow nodes execute real work:
  - `flow.conditional` evaluates `always`, `has_shorts`, `has_transcript`,
    `artifact:<name>`, `metadata:<key>`, and `file:<path>`.
  - `flow.loop` repeats inline steps over selected Shorts or matching files.
  - `flow.subflow` runs an inline group or another recipe's steps.

## 4. Timeline

The canvas is Konva; the audio waveform is wavesurfer.js.

- Tracks: V1 video, A1 dialogue, S1 captions, B1 B-roll.
- Ruler with second ticks, hover time, and click/drag scrubbing.
- Playhead line and draggable knob.
- Zoom slider, fit, and Ctrl/Cmd+wheel zoom.
- Clips drag horizontally with snapping to the playhead, other clip edges,
  captions, and zero.
- Selected clips expose left/right trim handles; dragging shows a live ghost.
- Toolbar: play/pause, timecode, undo, redo, split, delete, ripple delete,
  snap toggle, fit, and zoom.
- Shift-click multi-select; group move and bulk delete/ripple use atomic batch
  edits.
- Keyboard: Space plays, `S` splits, Delete deletes, Shift+Delete ripples,
  Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z redoes.
- Editable playhead timecode input.
- Clip inspector: timeline in/out, trim, move delta, transition type/length,
  scale, position, audio fade in/out, and keyframe count.
- Markers with labels and jump-to-time; per-track mute/solo/lock.
- Real clip thumbnails loaded from the job source.
- Background MP4 render queue with progress, cancel, and download.
- Incremental rendering: scene layer vs. overlay playhead/guides.
- Caption list with in-place editing.
- Preview: MP4 player plus waveform, both synced to the playhead. Background
  540p proxy rendering with progress and cancellation; titles, color/LUT, and
  audio-master filters are applied to the preview render.
- Shorts cards open the Short editor (reframe, captions, metadata, thumbnail,
  voice-over, dubbing, analysis, publish).
- B-roll approval: approve/reject and reorder per Short, persisted to
  `broll_approval.json`; the renderer consumes only approved entries.

## 5. Automation

- Persistent schedules: once, interval, and watch folder.
- SQLite storage with a one-time JSON migration.
- Retry/backoff, bounded run history, per-file size/mtime signatures, and a
  local 20-second scheduler.
- Run-now, status, last-run, and errors.

## 6. Deliverables

- Review checklist from `review.json` with approve/reject, reviewer, comments,
  and a comment thread.
- Thumbnail variants from `thumbnails/*.png`; the selected variant is stored in
  `thumbnail_choice.json`, with impressions/clicks/CTR metrics.
- NLE sidecars package titles, LUT/eq, audio master filters, B-roll, and markers.
- Audio QA reports EBU R128 loudness and true peak.

## 7. Assets

Scan folders into the local index, search, filter by kind, edit tags and
license, download, and remove. Assets are served by the local API.

## 8. Models

Models are grouped by capability. Downloads run in the background with
progress, cancellation, checksum verification, installed path, disk usage, and
"used by" provenance. The default model per capability is stored in the model
settings; provider configuration is separate.

## 9. Services

Health polling, service discovery, current-service restart/shutdown, stop other
VideoFlow processes, doctor output, server log download, and support bundle.

## 10. Providers

Providers are persisted in `$VIDEOWFLOW_HOME/providers.json`. Secrets use the
environment, OS keyring, or a 0600 local fallback; only presence is exposed.

- Capabilities: LLM, ASR, TTS, vision, stock, translation, diarization,
  publishing.
- Fields: id, name, base URL, secret env name, model, enabled, default,
  fallback IDs, notes.
- The connection test reports HTTP status and secret presence without showing
  the secret.
- `GET /api/v1/providers/resolve?capability=...` returns the default followed by
  its fallback chain.

## 11. Persistence and invalidation

- `project_state.json` is the single source of truth for the timeline.
- Every timeline edit increments `revision` and writes one undo entry in
  `timeline_history.json`.
- Edits do not claim rendered artifacts are fresh; the API returns a warning
  that export/render must run again.
- B-roll approvals, provider configuration, model downloads, and publish queue
  state are JSON files under the VideoFlow home or job output.

## 12. Accessibility and responsiveness

- Navigation uses `role="tab"` buttons with `aria-selected`.
- Error banners use `role="alert"`.
- Timeline shortcuts ignore focused inputs, textareas, and selects.
- Panels are usable from 360 px upward; the timeline scrolls horizontally
  instead of shrinking clips below legibility.
