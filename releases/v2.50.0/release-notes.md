# VideoFlow 2.50.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.50.0-linux-x86_64` — SHA-256 `6ac568149e7995b013fe9334d02582e00f42ea18a45beefc4fe2941b09426590`
- `VideoFlow-2.50.0-x86_64.AppImage` — SHA-256 `2bd61807c561ef5b11833e4684ed05a2a245fe0bcbd38f9715a59b3e93f5a85b`
- `sbom.json` — SHA-256 `f03bc8d69e9e1b3a0add88926a81b9806560133746d3831ce9a41b8b27dba5dd`

## Run

Linux plain binary:

```bash
./videoflow-2.50.0-linux-x86_64 doctor
./videoflow-2.50.0-linux-x86_64 demo -o demo
./videoflow-2.50.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.50.0-x86_64.AppImage
./VideoFlow-2.50.0-x86_64.AppImage version
./VideoFlow-2.50.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
