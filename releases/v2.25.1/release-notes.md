# VideoFlow 2.25.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.25.1-linux-x86_64` — SHA-256 `8ec6b589a0a0e579e881abc207b6feb681eb94b85d1fb10630eb82bd34bd1439`
- `VideoFlow-2.25.1-x86_64.AppImage` — SHA-256 `de54651f832e4d45bdfb94eb13d542659355dc6ac1f01eba3337ce9d84266430`
- `sbom.json` — SHA-256 `6f525cd9961e46d061145dd105e88e5fe35e7cbf2673de633e3bbf69dd589bd7`

## Run

Linux plain binary:

```bash
./videoflow-2.25.1-linux-x86_64 doctor
./videoflow-2.25.1-linux-x86_64 demo -o demo
./videoflow-2.25.1-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.25.1-x86_64.AppImage
./VideoFlow-2.25.1-x86_64.AppImage version
./VideoFlow-2.25.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
