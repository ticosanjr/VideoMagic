# VideoFlow 2.72.0

## Highlights

- Tray execution controller: live job counts, open Runs, and pause/resume/cancel all.
- Structured recipe preflight with blocking errors and actionable warnings.
- Deeper HITL: expiry, drafts, artifact review, upload progress, and bulk approval.
- Mobile timeline list fallback plus scene/callout plan editors.
- Full-tree coverage above 95% and expanded Playwright visual baselines.

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.72.0-linux-x86_64` — SHA-256 `c4361f3c0a8a9215aabfadba211327d9458b0fc0718027e98799a0046282798a`
- `VideoFlow-2.72.0-x86_64.AppImage` — SHA-256 `f4466d67473009e6745e63facf95e711fd89125703a460a81cc7e0b310837bfc`
- `sbom.json` — SHA-256 `1b1d9fea8ea456f48f26463014436a3c7600ed896fe6d28554c03e495485ffe4`

## Run

Linux plain binary:

```bash
./videoflow-2.72.0-linux-x86_64 doctor
./videoflow-2.72.0-linux-x86_64 recipe list
./videoflow-2.72.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.72.0-x86_64.AppImage
./VideoFlow-2.72.0-x86_64.AppImage version
./VideoFlow-2.72.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
