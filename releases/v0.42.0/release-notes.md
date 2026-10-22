# VideoFlow 0.42.0

This is the final release in the 0.39–0.42 hardening sequence.

## MLT/Kdenlive render smoke

- `scripts/melt_check.py` renders a Kdenlive/MLT project through `melt` and
  returns a JSON verdict with return code, stdout, and stderr.
- A media test generates a real two-cut source, exports Kdenlive, and runs the
  same render smoke.
- CI installs `melt` and runs the media suite.
- The local extracted MLT 7.22 render succeeded; optional plugins (`movit`,
  `qtblend`, `affine`) produced warnings in that minimal extraction.

## Final delivery

- Tag-driven release workflow publishes Linux, AppImage, Windows, SBOM, and
  checksums.
- Windows executable is smoke-tested with `version`, `doctor`, and `demo`.
- Inline MP4 and Short previews are served by the job API.

## Validation

- 443 Python tests passed.
- 8 media tests (including the melt render check).
- 14 Vitest tests passed.
- 6 Playwright tests passed.
- CI and the tag release workflow cover Linux, Windows, Playwright, media, and
  SBOM generation.

## Remaining limitations

- Kdenlive uses affine opacity/volume fades, not an exact validated
  cross-dissolve.
- Manual import QA in Resolve, Premiere, and Kdenlive remains pending.
- pyannote/Pexels are optional and mock-tested.
- The Windows executable is unsigned.
