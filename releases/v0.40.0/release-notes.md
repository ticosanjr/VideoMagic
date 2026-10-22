# VideoFlow 0.40.0

This release consolidates persistence and recovery.

## Jobs survive restart

- Each job is written as JSON under the VideoFlow home.
- Completed jobs are reloaded by the API after a restart.
- Queued/running jobs are marked failed with `job_interrupted`, avoiding phantom
  active work.

## Batches resume

- `POST /api/v1/batches/{id}/resume`.
- The batch modal has a Resume action for failed/cancelled batches.
- Completed items are skipped; only failed/pending items run again.
- Persisted batch JSON includes the recipe.

## Validation

- 442 Python tests passed.
- 7 media tests passed.
- 14 Vitest tests passed.
- 6 Playwright tests passed.
- The 0.39 automatic release workflow already proved tag-driven Linux, AppImage,
  Windows, SBOM, checksums, and GitHub publishing.

## Notes

- `PipelineRunner.execute` remains an xfail; the recipe engine is the execution
  path.
- Exact Kdenlive cross-dissolve and manual NLE import QA remain pending.
