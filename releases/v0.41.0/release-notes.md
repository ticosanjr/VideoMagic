# VideoFlow 0.41.0

This release adds preview without leaving the Recipes tab.

## Inline preview

- MP4 artifacts in a successful job render in the result panel.
- Rendered Shorts render in a preview grid.
- Preview files are served through the job API and are constrained to the job
  output directory.

## API

```http
GET /api/v1/jobs/{job_id}/artifacts/{artifact_name}
GET /api/v1/jobs/{job_id}/shorts/{index}/file
```

## Validation

- 443 Python tests passed.
- 7 media tests passed.
- 14 Vitest tests passed.
- 6 Playwright tests passed.
- Artifact and Short file routes have API tests.

## Notes

- Previews use the actual rendered file; a low-res proxy is still future work.
- Exact Kdenlive cross-dissolve and manual NLE QA remain pending.
