# VideoFlow 3.0.4

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.0.4-linux-x86_64` — SHA-256 `a92721d58363166b63de537a20227689c28481e6e7ca16f30d69f8c249cb3d6c`
- `VideoFlow-3.0.4-x86_64.AppImage` — SHA-256 `49f3539b11ab95d84f6749d9b786423eedf85c59dcbf116f17b39ce21d665296`
- `VideoFlow-3.0.4-linux-x86_64.tar.zst` — SHA-256 `cee96c3874a9e3f86dfb7632f8b2746e27d49f130e8bb1642c33e35b2874963f`
- `VideoFlow-3.0.4-mcp-servers.tar.zst` — SHA-256 `4e89ee2af3b4ca8354f1809156289c690c4d70daebd15efb57c0a23c51dbd006`
- `sbom.json` — SHA-256 `d2c4e5360e01a2eb88950beeb612343ec91437f6c8dc46cd89a5131317ea64f5`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.0.4-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.0.4-linux-x86_64 doctor
./videoflow-3.0.4-linux-x86_64 recipe list
./videoflow-3.0.4-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.0.4-x86_64.AppImage
./VideoFlow-3.0.4-x86_64.AppImage version
./VideoFlow-3.0.4-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
