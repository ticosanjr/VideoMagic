# VideoFlow 2.59.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.59.4-linux-x86_64` — SHA-256 `8770fedf59508a0fcee2dfb5100b43f8e4d9bc80f30341944ed39fdea4e27dd9`
- `VideoFlow-2.59.4-x86_64.AppImage` — SHA-256 `bb4875eafd71f19b055a94f2717525c9fdea1bd24b9a3daa75681b477c274465`
- `sbom.json` — SHA-256 `456fe310f127a1552dd9ed02d8036ccc4c6ac4821689a7259c65ab16bad463c1`

## Run

Linux plain binary:

```bash
./videoflow-2.59.4-linux-x86_64 doctor
./videoflow-2.59.4-linux-x86_64 demo -o demo
./videoflow-2.59.4-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.59.4-x86_64.AppImage
./VideoFlow-2.59.4-x86_64.AppImage version
./VideoFlow-2.59.4-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
