# VideoFlow 0.34.0

This release closes the operational gaps: NLE export validation, the legacy
module rerun, green CI, and a Windows PE attached to the release.

## NLE validation

- `scripts/validate_nle.py <exports-dir>` checks FCPXML, XMEML, and Kdenlive
  structure.
- `POST /api/v1/exports/validate` exposes the same validation.
- The report includes clips, transitions, keyframes, effects, affine filters,
  and tractors, with explicit errors and warnings.
- `docs/nle-qa.md` adds the manual import checklist for Resolve, Premiere, and
  Kdenlive.
- Validated report for the two-cut crossfade + progressive zoom fixture:
  - FCPXML: 2 clips, 1 transition, 2 keyframes.
  - XMEML: 2 clips, 1 transition, 1 motion effect.
  - Kdenlive: 2 clips, 2 affine filters, 4 tractors.

## Legacy module rerun

`POST /api/v1/projects/{id}/modules/{module}/run` no longer returns `501`.

- It plans the rack graph with the target and enabled upstream modules.
- A cached target returns `202` with `{"mode": "cached", "job": null}`.
- Otherwise it starts the full project pipeline and returns
  `{"mode": "full_pipeline", "planned": [...]}`.
- Recipe runs remain the checkpointed path; the legacy route does not execute a
  module in isolation.

## CI and Windows

- GitHub Actions CI passes on Linux for Python lint/tests and UI check/test/build.
- The Windows workflow builds a PE32+ x86-64 executable successfully.
- This release attaches that Windows artifact:

```powershell
.\videoflow-0.34.0-windows-x86_64.exe version
```

The Windows binary is unsigned, so SmartScreen may warn. It was built on
`windows-latest`; this Linux host has no Wine, so it was not executed locally.

## Validation

- 426 Python tests passed; 14 UI tests passed.
- CI run `39849714371` succeeded.
- Windows workflow run `39849718043` succeeded; artifact is PE32+ x86-64.
- The 0.34.0 AppImage returned `videoflow 0.34.0 (linux-x86_64)`.
- The 0.34.0 AppImage ran the split-screen + local B-roll + diarization recipe to
  success.

## Artifacts

- `videoflow-0.34.0-linux-x86_64` — SHA-256 `3f25b71470bf7ca1ed17afd0c80c1b617270062aaa87499e9893a9a1cf7701b8`
- `VideoFlow-0.34.0-x86_64.AppImage` — SHA-256 `448ac1f907d3d7d39e66e746c1e48ceff3f7fd7a3a894a2739dabcf80b875c57`
- `videoflow-0.34.0-windows-x86_64.exe` — SHA-256 `8128e312746e35cc5b47583f487fd5e579cce1f7dcb29108fc3a5350f73f01a5`

## Notes

Manual import into Resolve, Premiere, and Kdenlive is still pending because those
applications are not installed here. Automated XML validation passes.
