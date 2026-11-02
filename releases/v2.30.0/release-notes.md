# VideoFlow 2.30.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.30.0-linux-x86_64` — SHA-256 `1e6667039c64707aeca5764bb13b8dca4f933447c377b83f90121a9576f1daf9`
- `VideoFlow-2.30.0-x86_64.AppImage` — SHA-256 `d692a1aed6c6a54c9237404f628f8356a2c95bf5343d9b9b822536ee91799cc1`
- `sbom.json` — SHA-256 `ab5f5e60fcc799868e3e7035e129c2cc1131767dd8fb50dd27c81c7a89b81b74`

## Run

Linux plain binary:

```bash
./videoflow-2.30.0-linux-x86_64 doctor
./videoflow-2.30.0-linux-x86_64 demo -o demo
./videoflow-2.30.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.30.0-x86_64.AppImage
./VideoFlow-2.30.0-x86_64.AppImage version
./VideoFlow-2.30.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
