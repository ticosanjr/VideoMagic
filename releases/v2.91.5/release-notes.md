# VideoFlow 2.91.5

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.5-linux-x86_64` — SHA-256 `1ad92655bcd274c4972cd9375811114dc928ccc05daaa50d63f5327fd44f3e24`
- `VideoFlow-2.91.5-x86_64.AppImage` — SHA-256 `3212afd65d3fda446ce6a28e06da083712e309c681573b7bb234723e85916a60`
- `VideoFlow-2.91.5-linux-x86_64.tar.zst` — SHA-256 `deda8dba4c62364f78e095d65c4a7c28c4db741121af31fac1795fa7f7022433`
- `VideoFlow-2.91.5-mcp-servers.tar.zst` — SHA-256 `acea6bc5db3fd12665b4899276b9dd61fe637f056ab99584509e215d579a3cc1`
- `sbom.json` — SHA-256 `bc8f0d4c134ec9f010b8fab5907638c6f9dcaae00c0c5ad3bb6a41d049d55f1c`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.5-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.5-linux-x86_64 doctor
./videoflow-2.91.5-linux-x86_64 recipe list
./videoflow-2.91.5-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.5-x86_64.AppImage
./VideoFlow-2.91.5-x86_64.AppImage version
./VideoFlow-2.91.5-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
