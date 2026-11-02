# VideoFlow 2.35.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.35.0-linux-x86_64` — SHA-256 `5367637d984224255796b49e41546da748f92aac141120389408537bdd4cdd9f`
- `VideoFlow-2.35.0-x86_64.AppImage` — SHA-256 `0efe6a0a309894c7ffab2950109dfe2b1b4b3ec36898ae75bb0b456eb660179d`
- `sbom.json` — SHA-256 `6ba541291062fc38891c9948f29f653a3fba28d538b14d0f7b81b96e3606fab6`

## Run

Linux plain binary:

```bash
./videoflow-2.35.0-linux-x86_64 doctor
./videoflow-2.35.0-linux-x86_64 demo -o demo
./videoflow-2.35.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.35.0-x86_64.AppImage
./VideoFlow-2.35.0-x86_64.AppImage version
./VideoFlow-2.35.0-x86_64.AppImage demo -o demo
```

## Notes

See `CHANGELOG.md`.
