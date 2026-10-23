# Release artifacts

This directory mirrors the artifacts attached to GitHub Releases. Binaries are
ignored by git; only the notes and checksums are tracked.

## Current

- `v0.67.0`: canvas timeline, top-of-panel errors, persistent providers,
  B-roll approval, model downloads, executable flow nodes, legacy removal.
- `v0.62.0`: timeline edit foundation and settings/content consolidation.
- `v0.57.0`: recipe history, template gallery, and final 0.57 polish.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-0.67.0-x86_64.AppImage
./VideoFlow-0.67.0-x86_64.AppImage version
./VideoFlow-0.67.0-x86_64.AppImage serve --open
```
