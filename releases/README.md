# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.7.0`: two-track Kdenlive cross-dissolve plus the 2.6 professional
  features (NLE overlays, semantic B-roll option, dubbing alignment/review,
  hook/duration A/B, video mute, parallel map, asset pagination, plugin write
  policy, job DAG, embedded panels, cost estimates, expanded golden set).
- `v2.6.0`: professional edition with overlays, content quality, and hardening.
- `v2.5.0`: professional foundation with shell, jobs, timeline, NLE finishing.

`v2.4.0`, `v2.0.0`, `v1.0.0`, and `v0.95.0` were pruned by the three-release rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.7.0-x86_64.AppImage
./VideoFlow-2.7.0-x86_64.AppImage version
./VideoFlow-2.7.0-x86_64.AppImage serve --open
```
