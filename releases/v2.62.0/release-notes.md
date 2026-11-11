# VideoFlow 2.62.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- New favorite **Lamera Video Edit** recipe: 65 nodes in six colored phases.
- Four scoped research agents, presenter profile, and split narration/edition approvals.
- New `transcript.blocks`, `entities.extract`, and `storyboard.preview` steps.
- Colored recipe canvas groups with labels and descriptions.
- HITL checkpoints for research, decoupage, entities, units, assets, intro, samples, fact-check, voice, and final approval.

## Artifacts

- `videoflow-2.62.0-linux-x86_64` — SHA-256 `3ee27faae8cd7f27e578d2f23b298c7b28003177c0ed08fe5d1046082132c359`
- `VideoFlow-2.62.0-x86_64.AppImage` — SHA-256 `d4c1dfd7e3236aceb46664fe0a63bff22a71d7afb282e32ec92cee5d94f8aaa8`
- `sbom.json` — SHA-256 `32c5f3bac1a3d10f39104faefe93282c2f12a66ddbf498f20b5538134af26a8e`

## Run

Linux plain binary:

```bash
./videoflow-2.62.0-linux-x86_64 doctor
./videoflow-2.62.0-linux-x86_64 recipe list
./videoflow-2.62.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.62.0-x86_64.AppImage
./VideoFlow-2.62.0-x86_64.AppImage version
./VideoFlow-2.62.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
