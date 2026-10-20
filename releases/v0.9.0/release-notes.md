# VideoFlow 0.9.0

Portable, model-free pre-edit pipeline.

## Artifacts

- `videoflow-0.9.0-linux-x86_64` — SHA-256 `dc81d5d745b8ab5cdbea707cc1372d341ed9dbfac066a76ada48ad7a23375afc`
- `VideoFlow-0.9.0-x86_64.AppImage` — SHA-256 `628617c06d7f00d3fe82c710a7ab7115390d3f7096d1015c40c37df960171ddd`
- `videoflow-0.9.0-windows-x86_64.exe` — SHA-256 `e05b43c464c1d7a844cc90f997d9d03e3865030e0c69bd37040a55991edfa05b`

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
