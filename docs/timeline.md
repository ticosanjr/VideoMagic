# Timeline

The timeline edits the canonical `project_state.json` through validated integer
edits. Seconds are only the wire format; frames and samples are authoritative.

## Canvas interaction

| Gesture | Effect |
| --- | --- |
| Click a clip | Select it; `Shift`+click adds to the selection |
| Drag a clip | Move it, with snapping to playhead and neighboring edges |
| Drag an edge handle | Trim the selected clip |
| Drag an edge with several clips selected | Group trim: the same edge delta is applied to every selected clip |
| `Shift` + drag an edge | Ripple trim: following clips move by the same delta |
| `Alt` + drag a clip | Slip: shift the source in/out without moving the clip |
| Wheel with `Ctrl/Cmd` | Zoom around the current scale |
| Drag the playhead knob | Scrub |

Edits go to `PATCH /api/v1/jobs/{id}/timeline` or `/timeline/batch`. Every edit
records one undo entry, increments `revision`, and marks the preview outdated.

## Group trim

Group trim is a batch of ordinary `trim` edits computed client-side by
`groupTrimEdits` in `ui/src/lib/timelineView.ts`. Each clip is clamped to
`[0, duration]` and must keep at least 50 ms; clips that would not change are
dropped, so a locked or already-clamped selection produces no request.

## Slip

`action: "slip"` moves `source_in`/`source_out` (frames) and
`source_in_sample`/`source_out_sample` (audio) by `delta_sec` while leaving
`timeline_in`/`timeline_out` untouched. The edit is rejected when the new source
range leaves the media. `timeline=...` stays identical; only the picture and
audio offset change.

## Waveforms

`GET /api/v1/jobs/{id}/timeline/waveform?start=&end=&buckets=` returns normalised
RMS peaks. `src/videoflow/application/waveforms.py`:

1. decodes the source once to 4 kHz mono PCM;
2. computes RMS over 50 ms buckets;
3. normalises by the loudest bucket;
4. caches the result under `<home>/waveforms/<digest>.json`, keyed by path, size,
   and mtime;
5. slices the requested range and resamples it to `buckets` using the maximum,
   preserving transients.

The canvas requests roughly 60 bars per second, capped at 720 per clip, and
falls back to a deterministic synthetic shape when the peaks are unavailable.

## Virtualization

The canvas draws only clips, captions, and waveform bars that intersect the
visible time window plus a three-second margin. The window comes from
`visibleRange(scrollLeft, viewportWidth, zoom)` and is covered by Vitest. A
scroll schedules one animation-frame redraw, so the number of Konva nodes stays
proportional to what the operator can see rather than to the document length.

## Preview scheduler

After a successful edit, undo, or redo, the panel sets `previewDirty` and shows
`preview outdated`. When `Auto preview` is enabled and a preview already exists,
a 1.2 s debounce starts a new background preview through
`POST /api/v1/jobs/{id}/preview`. Rendering from the current `project_state.json`
is what makes the preview reflect the edit rather than the last MP4 artifact.

## Tracks

`timeline_meta.json` stores `muted`, `solo`, and `locked` per track.

- `locked` — the API rejects clip edits with `409 state_not_ready`; the canvas
  disables clip drag and hides trim handles.
- `muted` — render and preview append `volume=0` to the audio filter chain.
- `solo` — overrides mute for the audio track.

Markers are stored in the same file and reject negative times or unknown tracks.

## Tests

- `tests/unit/test_waveforms.py` — peak extraction, silence, slicing, cache.
- `tests/unit/test_new_features.py` — slip moves the source only.
- `tests/contract/test_api_waveform.py` — endpoint payload, DTO ranges, missing
  state.
- `tests/contract/test_api_timeline.py` — locked-track rejection and unlock.
- `tests/unit/test_render_cancel.py` — mute and solo in the render filters.
- `ui/src/lib/timelineView.test.ts` — window and group-trim math.
- `ui/e2e/timeline.spec.ts` — waveform requests, auto-preview control, and the
  outdated marker.
