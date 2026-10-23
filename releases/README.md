# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v0.86.0`: local-first beta with Settings Hub, expanded models, managed
  services, library, diagnostics, and support bundle.
- `v0.80.0`: multi-select timeline, render queue, markers, SQLite schedules,
  secrets, failover, translation, and delivery metrics.
- `v0.70.0`: incremental timeline, background preview, burned titles, color
  grading, automation schedules, review/thumbnail delivery, resumable models.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-0.86.0-x86_64.AppImage
./VideoFlow-0.86.0-x86_64.AppImage version
./VideoFlow-0.86.0-x86_64.AppImage serve --open
```
