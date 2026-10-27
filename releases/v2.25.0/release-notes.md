# VideoFlow 2.25.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.25.0-linux-x86_64` — SHA-256 `dc3574fc7b64f5104a1e9a9a84b5e625821cc9974d3d5506b9b640d06c4c3238`
- `VideoFlow-2.25.0-x86_64.AppImage` — SHA-256 `e8a6d12388eb2907bc4562575364ce7de92bbecdf39d5331f572bb980076ba89`
- `sbom.json` — SHA-256 `82bb13dc7673f2a6fe00044956a10ec97c6203c274ea0c8160617cce457d880e`

## Run

Linux plain binary:

```bash
./videoflow-2.25.0-linux-x86_64 doctor
./videoflow-2.25.0-linux-x86_64 demo -o demo
./videoflow-2.25.0-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.25.0-x86_64.AppImage
./VideoFlow-2.25.0-x86_64.AppImage version
./VideoFlow-2.25.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
