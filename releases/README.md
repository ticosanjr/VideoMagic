# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.11.0`: five-area navigation, naming pass, HelpTip/FieldHint/EmptyState/
  StatusBadge, searchable settings, units, keyboard tab navigation, and copy
  standards, over the 2.10 MCP/Copilot/integration release.
- `v2.10.0`: 78 MCP tools/5 resources, Copilot, integration area for
  OpenCode/Paperclip/DeepSeek.
- `v2.9.0`: segment-cached render, frame progress/preview, resource-aware
  parallelism, Copilot proposals.

`v2.8.0`, `v2.7.0`, `v2.6.0`, `v2.5.0`, `v2.4.0`, `v2.0.0`, `v1.0.0`, and
`v0.95.0` were pruned by the three-release rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.11.0-x86_64.AppImage
./VideoFlow-2.11.0-x86_64.AppImage version
./VideoFlow-2.11.0-x86_64.AppImage serve --open
```
