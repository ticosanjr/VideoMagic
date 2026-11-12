# VideoFlow 2.70.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Synthetic Code Studio: 43-node script-first pipeline with narration, timed storyboard, HTML/CSS/Three.js scenes, headless render, procedural audio, captions, and QA.
- Footage Intelligence Edit: 54-node real-footage pipeline with decoupage, OCR, masks, tracking, anchored callouts, licensed media, mix, QA, and MP4/NLE/EDL delivery.
- Multimodal QA, empty-frame and clipping checks, voice-clone repair, and the local tray icon.
- Both new recipes ship as built-in favorites.

## Artifacts

- `videoflow-2.70.0-linux-x86_64` — SHA-256 `41a2f49d4638ae4693520176e38c51fc73303753fa99356be8c19ff4d56b30a0`
- `VideoFlow-2.70.0-x86_64.AppImage` — SHA-256 `7921e2fb81d07b5a80d20e0190b26465fcefea6eff8c8a8bd8b9e526446feca5`
- `sbom.json` — SHA-256 `42d1007b6cc2ac60e5ebfa5a4abebe34d78c99dc93af6d34fa373203ac560c12`

## Run

Linux plain binary:

```bash
./videoflow-2.70.0-linux-x86_64 doctor
./videoflow-2.70.0-linux-x86_64 recipe list
./videoflow-2.70.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.70.0-x86_64.AppImage
./VideoFlow-2.70.0-x86_64.AppImage version
./VideoFlow-2.70.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
