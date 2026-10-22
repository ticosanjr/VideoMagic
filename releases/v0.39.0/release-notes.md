# VideoFlow 0.39.0

This release hardens delivery.

## Automatic release

Pushing a `v*` tag now runs a release workflow that builds:

- the Linux portable binary;
- the Linux AppImage;
- the Windows PE32+ executable;
- a JSON SBOM.

It stages SHA-256 checksums and publishes the GitHub release with the artifacts.
The same workflow smoke-tests the Windows executable with `version`, `doctor`,
and `demo`.

## CI

- Python media tests run in CI with real FFmpeg fixtures.
- Playwright E2E runs in CI with Chromium.
- SBOM generation is part of the release build.

## Retention

Successful recipe runs now prune old checkpoints and run history using the
existing maintenance service. The defaults are 200 checkpoints and 30 runs.
Set `VIDEOFLOW_PRUNE_AFTER_RUN=0` to disable it.

## Validation

- 439 Python tests passed.
- 7 media tests passed.
- 14 Vitest tests passed.
- 6 Playwright tests passed.
- AppImage and Windows smoke are validated by the release workflow.

## Notes

- Exact Kdenlive cross-dissolve and manual NLE import QA remain pending.
- pyannote/Pexels remain optional and mock-tested.
- The Windows binary is unsigned.
