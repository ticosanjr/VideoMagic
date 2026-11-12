# VideoFlow 2.69.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Eye-contact analyzers moved into `application/eye_contact.py`; the step is now orchestration only.
- Parallel research groups reuse the parent's source stamp and Intelligence instance.
- Lamera workspace polling is adaptive, pauses in hidden tabs, and never overlaps requests.
- Includes the optional ElevenLabs voice clone and `voice.clone` repair step from 2.68.0.

## Artifacts

- `videoflow-2.69.0-linux-x86_64` — SHA-256 `b0fd21376506fdf03897748504c137ac0a036ef04e99662cf1595f607fb7c328`
- `VideoFlow-2.69.0-x86_64.AppImage` — SHA-256 `9648fff6c7b571bab65a5b442adc6d238ee706b77149729c38282b2a3b949d93`
- `sbom.json` — SHA-256 `d9290056216af8b29e58bce1bdd633445e17584572c14a441401ae42b2016682`

## Run

Linux plain binary:

```bash
./videoflow-2.69.0-linux-x86_64 doctor
./videoflow-2.69.0-linux-x86_64 recipe list
./videoflow-2.69.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.69.0-x86_64.AppImage
./VideoFlow-2.69.0-x86_64.AppImage version
./VideoFlow-2.69.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
