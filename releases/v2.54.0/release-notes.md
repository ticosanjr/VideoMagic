# VideoFlow 2.54.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.54.0-linux-x86_64` — SHA-256 `219e2cd705e49079cd2b7724a63a8d2cd209bdfb39bae82af268767da56db8d2`
- `VideoFlow-2.54.0-x86_64.AppImage` — SHA-256 `1fa35fd6ae093669af5ca47325e9a3080060fd1ccde12651e7c62111a375a255`
- `sbom.json` — SHA-256 `43dd54a2543953226a89c4e4406a8f1872bc6caed8ddf12ee17741762421ed1d`

## Run

Linux plain binary:

```bash
./videoflow-2.54.0-linux-x86_64 doctor
./videoflow-2.54.0-linux-x86_64 demo -o demo
./videoflow-2.54.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.54.0-x86_64.AppImage
./VideoFlow-2.54.0-x86_64.AppImage version
./VideoFlow-2.54.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
