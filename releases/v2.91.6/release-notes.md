# VideoFlow 2.91.6

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.91.6-linux-x86_64` — SHA-256 `60644134dedadb19bac069492573b55297a602d20c4cefb8ce083d6c46368b10`
- `VideoFlow-2.91.6-x86_64.AppImage` — SHA-256 `a9ba28e9e2de5612714f165f628f3f21330254d3ae6d57547cc176141153528c`
- `VideoFlow-2.91.6-linux-x86_64.tar.zst` — SHA-256 `794f33ca6f27660b4c566aba3867a7240ff9c3dd976d1f9cb9fcab53490847ac`
- `VideoFlow-2.91.6-mcp-servers.tar.zst` — SHA-256 `a717b80286e790cd0c03c390007cedcd18d9ea6459cfc8925660b3dd797f9979`
- `sbom.json` — SHA-256 `ef3fb5a29aebee360c19148b2757694fd48c862f9f74be5968cc8fcf0297e422`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.91.6-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.91.6-linux-x86_64 doctor
./videoflow-2.91.6-linux-x86_64 recipe list
./videoflow-2.91.6-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.91.6-x86_64.AppImage
./VideoFlow-2.91.6-x86_64.AppImage version
./VideoFlow-2.91.6-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
