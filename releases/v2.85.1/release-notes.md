# VideoFlow 2.85.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.85.1-linux-x86_64` — SHA-256 `0d0f9fb0553d51cd3c572d69c52a69b216757ba9b3a86c6a0254798a9916312a`
- `VideoFlow-2.85.1-x86_64.AppImage` — SHA-256 `425deacd7dec5b2e63d7a5f682f304cb807b3ff361e39f18b55f980492386a65`
- `VideoFlow-2.85.1-linux-x86_64.tar.zst` — SHA-256 `861fca77b91f8a2f6facf790fd203efc4e1ff8615cd90b4f7110c0c851f7718d`
- `sbom.json` — SHA-256 `2fb60cce511c4f5b50caab09b845581510d48099ec56b84a705d631c6cb22504`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.85.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.85.1-linux-x86_64 doctor
./videoflow-2.85.1-linux-x86_64 recipe list
./videoflow-2.85.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.85.1-x86_64.AppImage
./VideoFlow-2.85.1-x86_64.AppImage version
./VideoFlow-2.85.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
