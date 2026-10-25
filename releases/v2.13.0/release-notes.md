# VideoFlow 2.13.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.13.0-linux-x86_64` — SHA-256 `fe7fa49e97c0ef3907ccb8ba128a899d145ce0894d901130b6a8f19964f39856`
- `VideoFlow-2.13.0-x86_64.AppImage` — SHA-256 `6e1ea80881938ded67caab4aabe349cf833697549542676d741af399bbaaf09c`
- `sbom.json` — SHA-256 `92fea7bb5266f66144e6cce896f2e9e70d22917ad8c58ada509c8a1679cb502c`

## Run

Linux plain binary:

```bash
./videoflow-linux-x86_64 doctor
./videoflow-linux-x86_64 demo -o demo
./videoflow-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-x86_64.AppImage
./VideoFlow-x86_64.AppImage version
./VideoFlow-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-windows-x86_64.exe version
.\videoflow-windows-x86_64.exe doctor
.\videoflow-windows-x86_64.exe demo -o demo
```

## Notes

See `CHANGELOG.md`. Windows artifacts are PE32+ x86-64 and were built and
smoke-tested under Wine in this release.
