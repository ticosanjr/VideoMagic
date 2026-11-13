# VideoFlow 2.72.1

## Highlights

- AppImage and desktop entry now start the tray instead of a terminal-only serve process.
- Frozen tray forces the XEmbed backend and bundles Xlib/six/pystray backends.
- Tray controls: live counts, open Runs, pause/resume/cancel all.
- Added a tray smoke test that verifies the icon and the job-control endpoints.

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.72.1-linux-x86_64` — SHA-256 `0db6bf5482cd2555ebb1fd804aa8742e7cde35635a4b95eca02f007f45f16a4b`
- `VideoFlow-2.72.1-x86_64.AppImage` — SHA-256 `79fc58b0ca1b030557edca08b926c21d0409659707af03ca1fd3d304f377d9ee`
- `sbom.json` — SHA-256 `09a8a170c2063afddbb7d931be7762a0142e17b387fc590567468f74bb6a825e`

## Run

Linux plain binary:

```bash
./videoflow-2.72.1-linux-x86_64 doctor
./videoflow-2.72.1-linux-x86_64 recipe list
./videoflow-2.72.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.72.1-x86_64.AppImage
./VideoFlow-2.72.1-x86_64.AppImage version
./VideoFlow-2.72.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
