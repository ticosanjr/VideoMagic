# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.60.0`: durable HILT approvals/questions/files with local, e-mail, Slack,
  and Signal channels; the 53-step Full AI Editor; research/script, vision,
  licensed assets, motion, procedural audio, fact-check, and voice repair.
- `v2.59.4`: legacy job API and portable execution removed; recipe-only jobs,
  domain-split API routes, hardened MCP registry, and concurrent history fixes.
- `v2.59.3`: premium studio shell and branding, PWA metadata, mobile
  navigation and builder fixes, branded empty states, and the shared
  `shorts_project`/`worker_state`/text primitives.

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
