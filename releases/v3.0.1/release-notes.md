# VideoFlow 3.0.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-3.0.1-linux-x86_64` — SHA-256 `efb020bf195977a4d8871021681a15af99567d4ee85066615d2fadd8a78f47b4`
- `VideoFlow-3.0.1-x86_64.AppImage` — SHA-256 `f5d5fa247ef9471f67f73902cea03cd00af1288b250d24439c0c79a58c289605`
- `VideoFlow-3.0.1-linux-x86_64.tar.zst` — SHA-256 `991ea549402842977c3802667a798cbcb4bddf1bfd8a032d62b787c2091ab7bc`
- `VideoFlow-3.0.1-mcp-servers.tar.zst` — SHA-256 `45eb92f13855c6156cb264701393f136e9e6b87ba94b0aec99e9691813fda102`
- `sbom.json` — SHA-256 `b29264bca89bbc7ffc63e59b29dd4343a27cc9fe0e17eb84f446452f6670b3d7`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.0.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.0.1-linux-x86_64 doctor
./videoflow-3.0.1-linux-x86_64 recipe list
./videoflow-3.0.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.0.1-x86_64.AppImage
./VideoFlow-3.0.1-x86_64.AppImage version
./VideoFlow-3.0.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
