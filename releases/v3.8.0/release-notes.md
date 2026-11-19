# VideoFlow 3.8.0

Zero-config Windows GPU worker and restored setup panels.

## Artifacts

- `videoflow-3.8.0-linux-x86_64` — onefile Linux binary.
- `VideoFlow-3.8.0-x86_64.AppImage` — AppImage.
- `VideoFlow-3.8.0-linux-x86_64.tar.zst` — portable onedir bundle.
- `sbom.json`, `SHA256SUMS`, `manifest.json`.

## Highlights

- LAN-open mode for loopback and private RFC1918 clients; public clients still
  require the token.
- Automatic LAN discovery, reconnect, and periodic retry in the UI.
- Windows firewall rules for TCP 8766 and UDP 8767 cover Public, Private, and
  Domain profiles.
- Worker health/beacon expose `auth_mode`, `nvenc`, and `encoder`; remote Short
  render uses NVENC only when available, otherwise libx264 on the worker.
- Installer logs the real NVENC failure instead of only warning.
- Setup → Workspace: folder picker, allowed-root registration, style/workflow
  sync, and one-click OpenCode MCP installation.
- Setup → Styles, Formats, and Help: style editing, format/safe-zone review,
  and MCP workflow/troubleshooting instructions.

## Verification

- MCP: 411 passed, 34 tools, 16 resources, 85% coverage.
- Python non-media: 2,828 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0 errors, production build OK.
- AppImage and onefile report `videoflow 3.8.0 (linux-x86_64)`.

## Security

LAN-open accepts only private/loopback addresses. Set
`VF_GPU_ALLOW_LAN_OPEN=0` to require the token again. Public clients never
bypass authentication.

## Known limitations

- Physical RTX 3060 NVENC certification remains pending; diagnostics now show
  the FFmpeg error.
- Resolve import remains manual; `scripts/fcpxml_smoke.py` validates first.
- The scene benchmark corpus is synthetic.
