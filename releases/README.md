# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v1.0.0`: local-first stable release with recipe variables, variants,
  map/reduce, human gates, Shorts scoring, assets, delivery, SQLite index,
  plugins, diagnostics, and backup/restore.
- `v0.95.0`: local-first release candidate.
- `v0.86.0`: Settings Hub, expanded models, managed services, library,
  diagnostics, and support bundle.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-1.0.0-x86_64.AppImage
./VideoFlow-1.0.0-x86_64.AppImage version
./VideoFlow-1.0.0-x86_64.AppImage serve --open
```
