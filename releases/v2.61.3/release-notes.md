# VideoFlow 2.61.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Provider connection tests now show inline validation and connection errors.
- 401/403, 404, 429, 5xx, and network failures have human messages and hints, with the raw response in details.
- A pasted API key can be tested without saving it; the result shows the key source.
- Base URL, secret env name, and chat model are validated before the request.

## Artifacts

- `videoflow-2.61.3-linux-x86_64` — SHA-256 `69010eb632083ed9da58f7fabb6c3d0a17adfc428ff9ed246460acb2c1bd8054`
- `VideoFlow-2.61.3-x86_64.AppImage` — SHA-256 `861a37b7e5aab546231df9feb66f826c9a6dfffcb129a9d6e11a5b37e3a3d3cb`
- `sbom.json` — SHA-256 `8b76224e78c4a6a5301810801bdf744deb8a23de5b3fa4f66118563e961c56a6`

## Run

Linux plain binary:

```bash
./videoflow-2.61.3-linux-x86_64 doctor
./videoflow-2.61.3-linux-x86_64 recipe list
./videoflow-2.61.3-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.61.3-x86_64.AppImage
./VideoFlow-2.61.3-x86_64.AppImage version
./VideoFlow-2.61.3-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
