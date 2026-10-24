# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.5.0`: professional edition with real cancellation, SQLite-first
  operations, command center and job dashboard, calendar of timeline tools,
  calibrated Short selection, semantic B-roll, SFX/dubbing/hook A/B, native NLE
  finishing, plugin SDK with sandbox, theming, accessibility, hardening, and
  asset overlays.
- `v2.4.0`: professional foundation and finishing edition.
- `v2.0.0`: local-only feature-complete edition.

`v1.0.0` and `v0.95.0` were pruned by the three-release retention rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.5.0-x86_64.AppImage
./VideoFlow-2.5.0-x86_64.AppImage version
./VideoFlow-2.5.0-x86_64.AppImage serve --open
```
