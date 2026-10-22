# VideoFlow 0.36.0

This release adds explicit JSON schema gates and output maintenance.

## Schema gates

- `migrate_recipe` fills missing pre-1.0 fields (`schema_version`, `llm`,
  `enabled`, `needs`, `params`) before Pydantic validation.
- `migrate_project_state` validates the state version before loading.
- Future recipe/project schema versions fail with a typed error instead of being
  accepted silently.

## Maintenance

`prune_output` now trims:

- checkpoints beyond `keep_steps`, oldest first;
- B-roll cache files older than `keep_days`;
- run history beyond `keep_runs`.

It never deletes source media or exported NLE/MP4 artifacts.

CLI:

```bash
videoflow recipe cache prune --output /path/to/output \
  --keep-steps 200 --keep-runs 30 --keep-days 14 --dry-run
```

API:

```http
POST /api/v1/maintenance/prune
{
  "output": "/path/to/output",
  "keep_steps": 200,
  "keep_runs": 30,
  "keep_days": 14,
  "dry_run": true
}
```

## Validation

- 434 Python tests passed.
- 14 Vitest tests passed.
- 3 Playwright tests passed.
- AppImage 0.36.0 built.

## Artifacts

- `videoflow-0.36.0-linux-x86_64` — SHA-256 `04126991961f650a90fafbe37628dca2cf37e295863e9b2fa670dfb55da0ac2a`
- `VideoFlow-0.36.0-x86_64.AppImage` — SHA-256 `d9d081e1d780a0d17ef7365699a6fbd3cbf1e458ab4bb25d2d7335fdff55f6aa`
