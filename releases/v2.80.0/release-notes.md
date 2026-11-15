# VideoFlow 2.80.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.80.0-linux-x86_64` — SHA-256 `7e0263e0213bdefd827df295e78a2fc25a7f6a5121f48045074b97efc09cc6e9`
- `VideoFlow-2.80.0-x86_64.AppImage` — SHA-256 `510df367df39d6fca0a64090ed0436b9d308c92848c18dc25eff66f491a098ff`
- `VideoFlow-2.80.0-linux-x86_64.tar.zst` — SHA-256 `4c758094a1c67e19e874a0222d125708104a4fc37ffb2af662c3b199c6eae9c7`
- `sbom.json` — SHA-256 `765d0b196839c50d9e1e7c4e55fc3a31641c8d73071c184696449d34eaf61840`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.80.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.80.0-linux-x86_64 doctor
./videoflow-2.80.0-linux-x86_64 recipe list
./videoflow-2.80.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.80.0-x86_64.AppImage
./VideoFlow-2.80.0-x86_64.AppImage version
./VideoFlow-2.80.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
