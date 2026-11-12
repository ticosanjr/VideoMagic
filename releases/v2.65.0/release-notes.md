# VideoFlow 2.65.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Independent scoped research agents now run concurrently and merge their dossiers, hashes, ports, and warnings.
- The four Lamera research scopes keep their own checkpoints and aggregate manifest.
- Transcription still resumes from a partial segment checkpoint after a restart.
- Entity extraction, style-guided audio, and expired-license blockers from 2.64.0 remain included.

## Artifacts

- `videoflow-2.65.0-linux-x86_64` — SHA-256 `570dda899088a56faa3af1b0aa177b1a6b8f5b4981c39954f5e0deecbac58607`
- `VideoFlow-2.65.0-x86_64.AppImage` — SHA-256 `b2fd51c9f4aa8a020c4c62bc41fb1826ba0810473313d41f64e3824a0a6b95b9`
- `sbom.json` — SHA-256 `d559a7baab5899a56414ad61cc672b1b0ce545ee75e57dde0360bf8a85f88c56`

## Run

Linux plain binary:

```bash
./videoflow-2.65.0-linux-x86_64 doctor
./videoflow-2.65.0-linux-x86_64 recipe list
./videoflow-2.65.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.65.0-x86_64.AppImage
./VideoFlow-2.65.0-x86_64.AppImage version
./VideoFlow-2.65.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
