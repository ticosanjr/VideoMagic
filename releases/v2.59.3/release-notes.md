# VideoFlow 2.59.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.59.3-linux-x86_64` — SHA-256 `85db370bd829b0c3369f6cda2849d680e30c4a68e2194eefe34438bd3afd2e66`
- `VideoFlow-2.59.3-x86_64.AppImage` — SHA-256 `fc18d5a79f757368eb535d9c39e607db6c43ccee9e0a23fedab242a7f014d5bc`
- `sbom.json` — SHA-256 `3fc04816037c717df58e2119c43be16d7938536830da8210f02d51342d3fc87b`

## Run

Linux plain binary:

```bash
./videoflow-2.59.3-linux-x86_64 doctor
./videoflow-2.59.3-linux-x86_64 demo -o demo
./videoflow-2.59.3-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.59.3-x86_64.AppImage
./VideoFlow-2.59.3-x86_64.AppImage version
./VideoFlow-2.59.3-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
