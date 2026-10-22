# VideoFlow 0.26.0

This release adds the two remaining execution-layer pieces: direct MP4 render
for the main timeline and folder batches.

## Direct MP4 render

`export.nle` now accepts `mp4` as a target. The exporter builds one FFmpeg
filter graph from the validated timeline:

- video `trim` + `setpts` + optional static scale/crop, then `concat`;
- audio `atrim` + `asetpts` + fades, then `concat`;
- H.264/AAC output with `+faststart`.

The legacy Export card and recipe export step expose the target. This is a
review/social deliverable, not a replacement for the NLE master.

## Folder batches

```bash
videoflow recipe batch recipes/viral_shorts_batch.json /media/inbox -o /media/out --recursive
```

- `POST /api/v1/batches`, `GET /api/v1/batches`,
  `GET /api/v1/batches/{id}`, `POST /api/v1/batches/{id}/cancel`.
- MCP: `videoflow_run_batch`, `videoflow_get_batch`,
  `videoflow_cancel_batch`.
- The Recipes tab has a **Batch** modal with folder pickers, recursive mode,
  extension filter, item-level progress, and cancellation.
- Files are processed one at a time. Each item is a normal job with its own
  output folder, logs, cancellation, and recipe checkpoints.

## Validation

- 405 Python tests passed; 14 UI tests passed.
- Real FFmpeg media rendered through the timeline filter graph and probed back
  at the source dimensions.
- A two-file batch completed both items into separate output folders, each with
  a direct `timeline.mp4`.
- The 0.26.0 AppImage started without a terminal and served the batch API.
- Opening the AppImage again reused the running service.
- Playwright opened and closed the Batch modal.

## Artifacts

- `videoflow-0.26.0-linux-x86_64` — SHA-256 `50565cdd9183362740759f16b84f5fb466264a5382f4f5f98564ecba8a801f46`
- `VideoFlow-0.26.0-x86_64.AppImage` — SHA-256 `837588ac78d79495ee6185997785260728208a35363178adf5e4f596d5ac6b18`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
