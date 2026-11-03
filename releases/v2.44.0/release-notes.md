# VideoFlow 2.44.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.44.0-linux-x86_64` — SHA-256 `73c495084147426f337e77c1da445c2800efcc1038b14a44f90d88a8007bdda7`
- `VideoFlow-2.44.0-x86_64.AppImage` — SHA-256 `6b43b24a7390cb79dd77745441c3551a5663619af2e6315ad87d339b73fe21fd`
- `sbom.json` — SHA-256 `caa7812ae047e5a4bd0514aea2c65b776d365f9b79e31ce4b2714b79061075f5`

## Run

Linux plain binary:

```bash
./videoflow-2.44.0-linux-x86_64 doctor
./videoflow-2.44.0-linux-x86_64 demo -o demo
./videoflow-2.44.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.44.0-x86_64.AppImage
./VideoFlow-2.44.0-x86_64.AppImage version
./VideoFlow-2.44.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
