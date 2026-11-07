# VideoFlow 2.59.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.59.1-linux-x86_64` — SHA-256 `d6887b5d2664d28446d0cdc6e8451c05daa2f92ba88a5d1c24e3a33ee8f69b3f`
- `VideoFlow-2.59.1-x86_64.AppImage` — SHA-256 `dd6b70a15941c1459e554d80c9abee00634a136f68b15142ed5edbdd6750ee8b`
- `sbom.json` — SHA-256 `99d87f7a847b957564d7ce2fbd9f26f3cf5a7124c0bfac3fe5f00c4e6a6ecea0`

## Run

Linux plain binary:

```bash
./videoflow-2.59.1-linux-x86_64 doctor
./videoflow-2.59.1-linux-x86_64 demo -o demo
./videoflow-2.59.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.59.1-x86_64.AppImage
./VideoFlow-2.59.1-x86_64.AppImage version
./VideoFlow-2.59.1-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
