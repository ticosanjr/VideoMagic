# VideoFlow 2.80.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.80.0-linux-x86_64` — SHA-256 `67cb4a434bf371ad15f09798efc77d27cdd6f07a2b4057bf0c61ae94258d9e20`
- `VideoFlow-2.80.0-x86_64.AppImage` — SHA-256 `278340904f490367518072aa1f6f5321181499e0a85a51b74b2665672dda247b`
- `VideoFlow-2.80.0-linux-x86_64.tar.zst` — SHA-256 `99769d04ab873c6d6168dc3b54a7c8f8b763b333b10cb931d169799b730eeb9f`
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
