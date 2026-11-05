# VideoFlow 2.58.5

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.58.5-linux-x86_64` — SHA-256 `6799e5d1af4c9c1a9492d31530463e0085dd1695b873483bce0f33844b4793da`
- `VideoFlow-2.58.5-x86_64.AppImage` — SHA-256 `ba42eca30941ac7e195da4adda283269c77437bfdc02a389915b31077fbe77de`
- `sbom.json` — SHA-256 `21cf8925ff912ec267c98a3bf90738450af218925adebf4e268a05fd4b618a47`

## Run

Linux plain binary:

```bash
./videoflow-2.58.5-linux-x86_64 doctor
./videoflow-2.58.5-linux-x86_64 demo -o demo
./videoflow-2.58.5-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.58.5-x86_64.AppImage
./VideoFlow-2.58.5-x86_64.AppImage version
./VideoFlow-2.58.5-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
