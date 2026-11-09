# Release artifacts

Releases are built locally and staged here. Binaries are ignored by git; only
the manifest, checksums, and notes are tracked. GitHub Actions is not used.

## Current

- `v2.59.4`: legacy job API and portable execution removed; recipe-only jobs,
  domain-split API routes, hardened MCP registry, and concurrent history fixes.
- `v2.59.3`: premium studio shell and branding, PWA metadata, mobile
  navigation and builder fixes, branded empty states, and the shared
  `shorts_project`/`worker_state`/text primitives.
- `v2.59.2`: unified job lifecycle, shared text/file/span primitives, and the
  recipe catalog split into a package.

Older folders are pruned by the three-release rule.

## Verification

Each release ships `SHA256SUMS`. Verify from the release folder:

```bash
sha256sum -c SHA256SUMS
```

The Linux AppImage can be checked without installing:

```bash
chmod +x VideoFlow-2.59.4-x86_64.AppImage
./VideoFlow-2.59.4-x86_64.AppImage version
./VideoFlow-2.59.4-x86_64.AppImage serve --open
```
