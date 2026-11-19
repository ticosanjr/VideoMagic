# VideoFlow 3.3.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.3.0-linux-x86_64` — SHA-256 `13422ad3d83d1c30e2a52965484beda7c1a1ddedea0190c335aa9319f59b5bc7`
- `VideoFlow-3.3.0-x86_64.AppImage` — SHA-256 `6c5656b935c1de4e1bc2816c8dd198ae65ca0d96206921563c5e6cd86aa7dc6c`
- `sbom.json` — SHA-256 `8909a72f3916cbcf9c0f455894bf033f86a72155af383d2b546b85c5bf54799c`
- `VideoFlow-3.3.0-linux-x86_64.tar.zst` — SHA-256 `ceeb4f221a8a662ec51286a8f424f4e3b825db72572d1695e420a37903d00d4a`
- `VideoFlow-3.3.0-mcp-servers.tar.zst` — SHA-256 `82956b08295b5c3b6e27af6583db93e0b484a29ddb5856a0188a215747930b2a`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.3.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.3.0-linux-x86_64 doctor
./videoflow-3.3.0-linux-x86_64 recipe list
./videoflow-3.3.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.3.0-x86_64.AppImage
./VideoFlow-3.3.0-x86_64.AppImage version
./VideoFlow-3.3.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
