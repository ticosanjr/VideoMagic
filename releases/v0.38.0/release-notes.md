# VideoFlow 0.38.0

This is the final release in the 0.35–0.38 sequence.

## Two-source split-screen

- `shorts.render` accepts `second_source_path`.
- With split-screen enabled, the left panel comes from the primary source and
  the right panel from the second source.
- Without a second source, the same-source two-panel layout remains.
- The Recipes inspector has a second-source field and file picker.
- Verified with two generated clips: the rendered Short is 1080x1920 and
  contains both panels.

## UI and testing

- Schema-derived inspector fields for primitive step parameters.
- NLE validation modal backed by `POST /api/v1/exports/validate`.
- B-roll plan viewer with provider, license, and path.
- Persistent batch JSON, restart recovery, and interrupted-batch marking.
- Playwright now covers:
  - recipe graph and transition controls;
  - add-step palette;
  - second split-screen source;
  - schema-derived fields;
  - NLE validation;
  - persisted failed/succeeded run history.
- CI installs Chromium and runs Playwright E2E.
- Vitest excludes `e2e/**`, so the two suites no longer collide.

## JSON policy

Project data, schemas, fixtures, recipes, batch records, history, checkpoints,
and test data are JSON. The repository policy test allows YAML only under
`.github/workflows`, where GitHub requires it.

## Validation

- 439 Python tests passed.
- 14 Vitest tests passed.
- 6 Playwright tests passed.
- CI run `39863803104` succeeded, including Playwright E2E.
- Windows workflow run `39863806505` succeeded; artifact is PE32+ x86-64.
- 0.38.0 AppImage ran the two-source split-screen recipe successfully.

## Artifacts

- `videoflow-0.38.0-linux-x86_64` — SHA-256 `34c70c87cd91f57bdcd653c0cecb47f00c0812de862bb45d6d040a382b9e881f`
- `VideoFlow-0.38.0-x86_64.AppImage` — SHA-256 `ec54f9d1579e07afb7927c062742b6b770d728419a9b8d30b64c4eb5e4f10c08`
- `videoflow-0.38.0-windows-x86_64.exe` — SHA-256 `d4336627a79ecb6838c381aa797e25592fa33faf495b06f4b26d62971fd4112f`

## Remaining limitations

- Kdenlive transitions are affine opacity/volume fades, not an exact validated
  cross-dissolve.
- Manual import QA in Resolve, Premiere, and Kdenlive is still pending.
- pyannote and Pexels are optional and were tested with fakes/mocks, not real
  model/API credentials.
- The Windows binary is unsigned and was not executed on this Linux host.
