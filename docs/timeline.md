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
| Right-click a clip | Context menu: split, duplicate, delete, ripple delete, slide, marker, comments |
| Wheel with `Ctrl/Cmd` | Zoom around the current scale |
| Drag the playhead knob | Scrub |

Edits go to `PATCH /api/v1/jobs/{id}/timeline` or `/timeline/batch`. Every edit
records one undo entry, increments `revision`, and marks the preview outdated.

## Group trim

Group trim is a batch of ordinary `trim` edits computed client-side by
`groupTrimEdits` in `ui/src/lib/timelineView.ts`. Each clip is clamped to
`[0, duration]` and must keep at least 50 ms; clips that would not change are
dropped, so a locked or already-clamped selection produces no request.

## Slide and duplicate

`action: "slide"` moves a clip between two contiguous neighbors: the previous
clip grows, the following clip shrinks, and the clip itself moves. Both source
ranges are adjusted by the same ratio, and the edit is rejected when a source
range leaves the media.

`action: "duplicate"` inserts a copy after the clip, shifts everything that
starts at or after the cut, and gives the copy a fresh clip id for video and
audio.

## Comments

`timeline_meta.json` stores per-clip comments. `GET/POST
/api/v1/jobs/{id}/timeline/comments` and `DELETE .../comments/{id}` back the
Comments panel and the context menu.

## Slip

`action: "slip"` moves `source_in`/`source_out` (frames) and
`source_in_sample`/`source_out_sample` (audio) by `delta_sec` while leaving
`timeline_in`/`timeline_out` untouched. The edit is rejected when the new source
range leaves the media. `timeline=...` stays identical; only the picture and
audio offset change.

## Normal and Recut views

The canonical state keeps active clips in `video_segments`/`audio_segments` and
removed clips in `inactive_segments`. Inactive entries preserve paired source
ranges, transform/transition data, and the reason (`manual`, `silence`,
`retake`).

- **Normal** hides inactive entries and shows the packed active timeline.
- **Recut** draws both sets on the source-time axis: active clips blue,
  inactive clips red. The view choice is stored in the browser.
- `PATCH /timeline` accepts `deactivate` and `activate` actions. They repack the
  active timeline, record history, and bump the revision.
- Render and NLE export consume only active segments.
- `live_eligible`/`live_reason` describe whether the browser can play the active
  source ranges directly. Hard cuts, identity transforms, paired audio (J/L
  offsets play through a separate audio element), no transitions/overlays/
  filters, and no track mute/solo are eligible.
- The live Recut player streams `GET /jobs/{id}/source/file` (Range-capable),
  seeks to each active source range, and jumps over inactive ranges. Complex
  timelines fall back to the rendered preview with the reason shown.

## Waveforms

`GET /api/v1/jobs/{id}/timeline/waveform?start=&end=&buckets=` returns normalised
RMS peaks for a **source-media** range. The UI maps each clip through
`source_in_sec`/`source_out_sec`, so the drawing stays correct after cuts.
Concurrent requests for the same source share one decode.
`src/videoflow/application/waveforms.py`:

1. decodes the source once to 4 kHz mono PCM;
2. computes RMS over 50 ms buckets;
3. normalises by the loudest bucket;
4. caches the result under `<home>/waveforms/<digest>.json`, keyed by path, size,
   and mtime;
5. slices the requested range and resamples it to `buckets` using the maximum,
   preserving transients.

The canvas requests roughly 60 bars per second, capped at 720 per clip, and
falls back to a deterministic synthetic shape when the peaks are unavailable.
`GET /frame?time=` takes a **timeline** moment, prefers the current preview file,
and otherwise maps the moment to the clip's source frame.

## Virtualization

The canvas draws only clips, captions, and waveform bars that intersect the
visible time window plus a three-second margin. The window comes from
`visibleRange(scrollLeft, viewportWidth, zoom)` and is covered by Vitest. A
scroll schedules one animation-frame redraw, so the number of Konva nodes stays
proportional to what the operator can see rather than to the document length.

## Incremental render

`shorts.render` writes `shorts/render-manifest.json` with a digest of the pieces,
style, captions, B-roll, SFX, music, cards, crop, and split-screen settings.
An unchanged Short is reused instead of re-encoded. The MP4 render queue does
the same for the whole timeline through `render/manifest.json`.

## Assets on the timeline

The timeline rail lists image and video assets from the local library. Drag one
onto the canvas and the panel posts:

```json
{
  "asset_id": "…",
  "path": "/media/logo.png",
  "start_sec": 4.2,
  "duration_sec": 3,
  "position_x": 0.5,
  "position_y": 0.5,
  "width_ratio": 0.25,
  "opacity": 1.0,
  "kind": "image"
}
```

`POST /api/v1/jobs/{id}/timeline/overlays` stores an `OverlayClip` in
`ProjectState.overlays` with frame-based timing and records one undo entry;
`DELETE .../overlays/{id}` removes it. The MP4 exporter adds each overlay as an
extra FFmpeg input and composites it with `overlay=...:enable='between(t,…)'`.
Images loop for the window; videos are stream-looped and trimmed. Missing files
are skipped. Overlays are not yet mapped into the NLE documents, which keep the
existing B-roll lane.

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
