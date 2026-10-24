# VideoFlow 2.5.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.5.0-linux-x86_64` — SHA-256 `d1ffeaf232e29314ff8f21f3e0c8d7dee948436b939a78d68d517c2af24cd02e`
- `VideoFlow-2.5.0-x86_64.AppImage` — SHA-256 `049deb28c5bbd95ebfe2833625a544a4858fcb4ce3c08e17d2c19fd31c0239c1`
- `sbom.json` — SHA-256 `229a2aed3a5781e6b69b617456c96ed59df8ba20ec2bd1d649294fc3a651254e`

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
