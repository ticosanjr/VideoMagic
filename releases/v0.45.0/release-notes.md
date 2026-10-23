# VideoFlow 0.45.0

This release closes the 0.43–0.45 sequence.

## Preview proxy

```http
POST /api/v1/jobs/{id}/preview
GET  /api/v1/jobs/{id}/preview/file
```

The proxy is a 540p H.264/AAC MP4 generated on demand from the first MP4
artifact or rendered Short. The original render is untouched.

## Global cache pruning

- `prune_cache` removes analysis entries by age and total size.
- CLI: `videoflow recipe cache prune --global-cache --cache-days 30 --cache-max-mb 512`.
- API: `POST /api/v1/maintenance/prune` with `include_global_cache: true`.
- Output-local pruning remains available in the same command.

## Engine cleanup

- Removed the unimplemented `PipelineRunner.execute` scaffold.
- `PipelineRunner` is planning-only; the recipe engine owns execution.

## Validation

- 448 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 8 Playwright tests passed.
- Preview proxy and global cache pruning have automated tests.

## Notes

- Manual NLE import QA and exact Kdenlive cross-dissolve remain pending.
- pyannote/Pexels still need real model/API credentials for final validation.
- Distribution, signing, SBOM expansion, and macOS remain out of scope.
