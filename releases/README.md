# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v3.7.0`: decupage acoustic phase, Scene Intelligence, Dynamic Shorts
  compositor, `vf_scenes`, 34 MCP tools, FCPXML V1/V2/A1/A2, and phase 7
  benchmark evidence.
- `v3.6.0`: distribution and GPU-worker hardening.
- `v3.5.0`: MCP-first surface and stateful step chains.

Older folders are pruned by the three-release rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.60.0-x86_64.AppImage
./VideoFlow-2.60.0-x86_64.AppImage version
./VideoFlow-2.60.0-x86_64.AppImage serve --open
```
