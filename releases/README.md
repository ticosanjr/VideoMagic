# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.4.0`: professional foundation and finishing edition. Cancellable FFmpeg,
  SQLite-first operations, command center and job dashboard, real waveforms,
  slip/group trim/ripple trim, preview scheduler, calibrated Short selection,
  shot-aware B-roll, SFX library, delivery package, and native NLE titles,
  markers, colour, B-roll, and audio master.
- `v2.0.0`: local-only feature-complete edition with gates, queue, variants,
  analytics-weighted scoring, dubbing, TF-IDF B-roll, library CRUD, SQLite
  migration, backup/restore, and plugins.
- `v1.0.0`: local-first stable release.

`v0.95.0` was pruned by the three-release retention rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.4.0-x86_64.AppImage
./VideoFlow-2.4.0-x86_64.AppImage version
./VideoFlow-2.4.0-x86_64.AppImage serve --open
```
