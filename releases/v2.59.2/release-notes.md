# VideoFlow 2.59.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.59.2-linux-x86_64` — SHA-256 `4c62b271be3deb8a2a7740f7d73c182db2b6b532626a7abaee3c69db9d4210a1`
- `VideoFlow-2.59.2-x86_64.AppImage` — SHA-256 `af63e2078a3bd952190843d0e6604e9b899133ce0e3a9c1a7a50a781169147ff`
- `sbom.json` — SHA-256 `7947cb71355081d765eaab599db3b780947809acc8b1d88074948cc17b299316`

## Run

Linux plain binary:

```bash
./videoflow-2.59.2-linux-x86_64 doctor
./videoflow-2.59.2-linux-x86_64 demo -o demo
./videoflow-2.59.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.59.2-x86_64.AppImage
./VideoFlow-2.59.2-x86_64.AppImage version
./VideoFlow-2.59.2-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
