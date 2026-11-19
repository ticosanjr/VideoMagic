# VideoFlow 3.8.0

Zero-config Windows GPU worker discovery and the restored setup panels.

## Highlights

- LAN-open worker mode for loopback and private RFC1918 clients. Public clients
  still require the token.
- Automatic discovery and reconnect in the UI; host/token fields moved under
  Advanced pairing.
- Windows firewall rules now cover Public, Private, and Domain profiles; TCP
  8766 and UDP 8767.
- Worker health/beacon expose `auth_mode`, `nvenc`, and `encoder`; remote Short
  render chooses NVENC only when it is actually available, otherwise libx264.
- Installer logs the real NVENC failure and keeps remote rendering available.
- Setup → Workspace: folder picker, allowed-root registration, style/workflow
  sync, and one-click OpenCode MCP installation.
- Setup → Styles, Formats, and Help: catalog editing, aspect ratios/safe zones,
  and MCP workflow/troubleshooting instructions.

## Artifacts

- `videoflow-3.8.0-linux-x86_64` — onefile Linux binary.
- `VideoFlow-3.8.0-x86_64.AppImage` — AppImage.
- `VideoFlow-3.8.0-linux-x86_64.tar.zst` — portable onedir bundle.
- `sbom.json`, `SHA256SUMS`, `manifest.json`.

Windows GPU worker wheel:
`src/videoflow/templates/wheels/videoflow_gpu_worker-3.8.0-py3-none-any.whl`.

## Verification

- MCP: 411 passed, 34 tools, 16 resources, 85% coverage.
- Python non-media: 2,828 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0 errors, production build OK.
- AppImage and onefile both report `videoflow 3.8.0 (linux-x86_64)`.

## Security

LAN-open accepts only private/loopback addresses. Set
`VF_GPU_ALLOW_LAN_OPEN=0` on the worker to require the token again. Public
clients never bypass authentication.

## Known limitations

- Physical Windows RTX 3060 NVENC certification remains pending; the installer
  now reports the exact failure when NVENC is unavailable.
- Resolve import remains a manual smoke; `scripts/fcpxml_smoke.py` verifies XML,
  lanes, and media first.
- The scene benchmark corpus is synthetic.
