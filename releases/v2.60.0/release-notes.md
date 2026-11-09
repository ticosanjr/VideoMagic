# VideoFlow 2.60.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Durable human-in-the-loop approvals, questions, and file handoffs, with local,
  e-mail, Slack, and Signal channels.
- The 53-step Full AI Editor: research, dual script, decoupage audit, entity
  corrections, licensed assets, motion, procedural audio, fact-check, voice
  repair, and final approval.
- Explicit asset license ledger; the final NLE export blocks unknown or
  unapproved fair-use/CC assets.
- MCP surface at 74 tools, including interaction list/get/respond.

## Artifacts

- `videoflow-2.60.0-linux-x86_64` — SHA-256 `351088a0004775153e93ed5028bb342c56877aff483d75557d4c9985ea9c288d`
- `VideoFlow-2.60.0-x86_64.AppImage` — SHA-256 `ea3900cfa43d9bd56e6ca42cc27bc96af37920ab78e93d7c5bb8e073dda712cb`
- `sbom.json` — SHA-256 `3f3f2bf43409b0ad80f41fbcf94dacb74083d542bc5dc09ed752f91c6bcaa103`

## Run

Linux plain binary:

```bash
./videoflow-2.60.0-linux-x86_64 doctor
./videoflow-2.60.0-linux-x86_64 recipe list
./videoflow-2.60.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.60.0-x86_64.AppImage
./VideoFlow-2.60.0-x86_64.AppImage version
./VideoFlow-2.60.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
