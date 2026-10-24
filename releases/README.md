# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.9.0`: segment-cached render, frame progress and preview, resource-aware
  parallelism, Copilot recipe/timeline proposals, plus the 2.8 typed job queue.
- `v2.8.0`: typed job rows, retries, frame preview, log rotation, rollback.
- `v2.7.0`: two-track Kdenlive cross-dissolve.

`v2.6.0`, `v2.5.0`, `v2.4.0`, `v2.0.0`, `v1.0.0`, and `v0.95.0` were pruned by
the three-release rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.9.0-x86_64.AppImage
./VideoFlow-2.9.0-x86_64.AppImage version
./VideoFlow-2.9.0-x86_64.AppImage serve --open
```
