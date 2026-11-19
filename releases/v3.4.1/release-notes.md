# VideoFlow 3.4.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Windows GPU kit now ships one `VideoFlowGPU.bat` entry point with a menu for
  install/repair, start, stop, status, doctor, logs, autostart, and uninstall.
- Bootstrap installs the local `worker\` package or bundled wheel explicitly,
  repairs broken venv/dependencies, downloads NVENC FFmpeg when missing,
  restores `worker.env`, validates the shared mount, and supervises restarts.
- Bundled `videoflow_gpu_worker-3.4.1` wheel and Windows scripts inside the
  portable app so kit generation works outside the source tree.

## Artifacts

- `videoflow-3.4.1-linux-x86_64` — SHA-256 `f0aad29c01b2ba947a44b9cbd7951157b06558ec3d12b24cf5d9119de3cae51b`
- `VideoFlow-3.4.1-x86_64.AppImage` — SHA-256 `b4142c802ec54463ac28585e0dffcd89ee7b109e058406aa38705d68b59a7d5f`
- `sbom.json` — SHA-256 `19639030e4d9c9ea3b34ce2fb3f32ed8e9c050f70868ca509fd20fa55f672292`
- `VideoFlow-3.4.1-linux-x86_64.tar.zst` — SHA-256 `70e30335d34c04d248900922bf781a803b5688096d80903b46fb76232d982eed`
- `VideoFlow-3.4.1-mcp-servers.tar.zst` — SHA-256 `d1478a6fc75158fe1321fe04b9bdf0d690203908780ee16ccd1168fb1ae6e1dc`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.4.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.4.1-linux-x86_64 doctor
./videoflow-3.4.1-linux-x86_64 recipe list
./videoflow-3.4.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.4.1-x86_64.AppImage
./VideoFlow-3.4.1-x86_64.AppImage version
./VideoFlow-3.4.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
