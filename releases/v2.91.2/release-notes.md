# VideoFlow 2.91.2

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.2-linux-x86_64` — SHA-256 `02b94940b526fbb50cbbe536eb109de19bb32fe22171f000c5f47c93823351aa`
- `VideoFlow-2.91.2-x86_64.AppImage` — SHA-256 `3f63164c34ec25bcd79ab7ac61ea99c3c805374a14868d446522cd94d8aed9f7`
- `VideoFlow-2.91.2-linux-x86_64.tar.zst` — SHA-256 `dc475eee193bf5ad08cb21577a3688b3897686d7efb222609f2d0048e644148c`
- `VideoFlow-2.91.2-mcp-servers.tar.zst` — SHA-256 `30b921d192ed06c9cb24bc0c537c11221c558826bc583c6ae6273a6fd1e0d85b`
- `sbom.json` — SHA-256 `f663024f255acc78d005f25f1e322f9330f5d638250adf7a2773796bf9560636`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.2-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.2-linux-x86_64 doctor
./videoflow-2.91.2-linux-x86_64 recipe list
./videoflow-2.91.2-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.2-x86_64.AppImage
./VideoFlow-2.91.2-x86_64.AppImage version
./VideoFlow-2.91.2-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
