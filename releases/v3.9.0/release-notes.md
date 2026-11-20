# VideoFlow 3.9.0

Worker dashboard, active discovery, complete style CRUD, format presets, and
searchable documentation.

## Artifacts

- `videoflow-3.9.0-linux-x86_64` — onefile Linux binary.
- `VideoFlow-3.9.0-x86_64.AppImage` — AppImage.
- `VideoFlow-3.9.0-linux-x86_64.tar.zst` — portable onedir bundle.
- `sbom.json`, `SHA256SUMS`, `manifest.json`.

## Highlights

- Embedded Windows worker dashboard at `http://127.0.0.1:8766/`: connection
  URLs, auth mode, firewall/discovery state, GPU/driver/VRAM, NVENC error,
  current job, recent jobs, logs, copy URL, and open logs.
- Worker menu option 12 opens the dashboard; status prints auth, encoder, LAN
  URLs, and dashboard URL.
- Active discovery combines UDP beacons with a TCP subnet scan; Linux GPU panel
  shows discovery diagnostics and live worker activity.
- `vf_format` and JSON format presets with 9:16, 4:5, 1:1, and 16:9 seeds,
  safe zones, caption presets, platforms, export targets, and full CRUD.
- Styles UI supports create, edit, duplicate, restore seed, and delete;
  `vf_style` adds `create`, `duplicate`, and `restore`.
- Formats UI has visual safe-zone preview and full CRUD.
- Searchable help center covering workspace, worker, styles, formats, scenes,
  Shorts, export, MCP, and troubleshooting, plus tooltips.
- MCP surface: 35 tools, 16 resources.

## Verification

- MCP: 423 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,835 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0 errors, production build OK.
- AppImage and onefile report `videoflow 3.9.0 (linux-x86_64)`.

## Windows worker

Download the 3.9.0 kit, run “Instalar / reparar tudo”, then “Iniciar worker”.
The kit installs `videoflow_gpu_worker-3.9.0`, enables discovery and LAN-open
for private networks, and updates firewall rules for all profiles.

## Known limitations

- Physical RTX 3060 NVENC certification remains pending; the dashboard shows
  the real FFmpeg error and remote rendering still works with libx264.
- Resolve import remains manual; run `scripts/fcpxml_smoke.py` first.
- The scene benchmark corpus is synthetic.
