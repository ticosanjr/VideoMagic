# VideoFlow 2.91.9

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.9-linux-x86_64` — SHA-256 `81b9b227dd81aa0b7671f3246bfa0150153ae205d469552e548d854f6beb0c36`
- `VideoFlow-2.91.9-x86_64.AppImage` — SHA-256 `29bcf11f3355f040879afa0f82dd028cfb08dcb7cfca0c2a75de150dbf35a50a`
- `VideoFlow-2.91.9-linux-x86_64.tar.zst` — SHA-256 `76f216c124d461596c0ea323ce561357c1f94574bf756045bb9d0674aede3957`
- `VideoFlow-2.91.9-mcp-servers.tar.zst` — SHA-256 `e3a39a1dfdd47dc811c2e5ec9ae9ee5d5f98c0b252049448b8e456b2c1d8b0b2`
- `sbom.json` — SHA-256 `7423c2566bfa6d62df325818a5c60f10aedd6976cb72ca27ec74f5b5870104ad`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.9-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.9-linux-x86_64 doctor
./videoflow-2.91.9-linux-x86_64 recipe list
./videoflow-2.91.9-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.9-x86_64.AppImage
./VideoFlow-2.91.9-x86_64.AppImage version
./VideoFlow-2.91.9-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
