# VideoFlow 2.64.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Transcription now checkpoints complete segments and resumes from a trimmed WAV tail after a restart.
- Entity extraction resolves single-word script names, quoted events, and known-entity hints.
- Compose, Foley, and mix follow the approved style-guide audio direction.
- Expired asset licenses block audit, review, and export.
- Transcribe logs an estimated runtime by duration, model, and device.

## Artifacts

- `videoflow-2.64.0-linux-x86_64` — SHA-256 `40f27f99d3233b5d6235d154757ffd7dccc61d03f5d0fbd2d814ba484b7812e2`
- `VideoFlow-2.64.0-x86_64.AppImage` — SHA-256 `ea7364884f8ff591aff28be388469c642ebcca9ec3629eb46e4995bf67ef3ee8`
- `sbom.json` — SHA-256 `accec51e0529aa444c30379d5e4ecfac0fb950d8f31a3fddaccb52ffc5614be0`

## Run

Linux plain binary:

```bash
./videoflow-2.64.0-linux-x86_64 doctor
./videoflow-2.64.0-linux-x86_64 recipe list
./videoflow-2.64.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.64.0-x86_64.AppImage
./VideoFlow-2.64.0-x86_64.AppImage version
./VideoFlow-2.64.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
