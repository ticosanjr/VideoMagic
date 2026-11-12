# VideoFlow 2.67.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Eye-contact detection now supports MediaPipe, YOLO face models, and OpenCV, with the manual HITL audit as fallback.
- Independent research agents run concurrently from 2.65.0.
- Partial transcription resume, richer entities, style-guided audio, expired-license blockers, and the Lamera workspace remain included.

## Artifacts

- `videoflow-2.67.0-linux-x86_64` — SHA-256 `4f898d6fea82baa3d8159c3bf490e5d743a3f02ec19634c0bd2d93904e74bcb9`
- `VideoFlow-2.67.0-x86_64.AppImage` — SHA-256 `5fc1b2b2b9b74c32e490e1a40a0f8702312d94ed83ad99671e3229391a337cf5`
- `sbom.json` — SHA-256 `b04744422944beecb3ee5e13be7bdc2ae19650ad0c11bcb4ce443f08feb88aa7`

## Run

Linux plain binary:

```bash
./videoflow-2.67.0-linux-x86_64 doctor
./videoflow-2.67.0-linux-x86_64 recipe list
./videoflow-2.67.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.67.0-x86_64.AppImage
./VideoFlow-2.67.0-x86_64.AppImage version
./VideoFlow-2.67.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
