# VideoFlow 2.11.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.11.0-linux-x86_64` — SHA-256 `9555e620bac439ba7b1f491fc57ef021dc222b88d17c531e000593e632b3db26`
- `VideoFlow-2.11.0-x86_64.AppImage` — SHA-256 `27b1de724350c61f79b5887e9f1d7a934928233ba509ee2ce550db23f5fafdfe`
- `sbom.json` — SHA-256 `d30dae339ec82c572db997c9ab38746898eafce7395576347f31441cb48e7304`

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
