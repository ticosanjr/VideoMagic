# VideoFlow 2.71.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- New favorites-first Produce overview, searchable recipe library, and two-step run composer.
- Global HITL inbox plus a generic `#run/<job_id>` workspace with gate, artifacts, logs, and history.
- Recipe-specific panels for Synthetic Code Studio, Footage Intelligence Edit, Lamera, Full AI Editor, and DeepSeek.
- Shared design tokens, rail/sidebar shell, readable type floor, setup health checklist, and mobile step-list fallback.
- HITL gates now carry summary, checklist, severity, next step, and group metadata.

## Artifacts

- `videoflow-2.71.0-linux-x86_64` — SHA-256 `efe5bc3d33e33cebf4eb465f0ab586723619fd43b35b5f59855b8ac465b2ec08`
- `VideoFlow-2.71.0-x86_64.AppImage` — SHA-256 `00b3747faccf794a10203e93feff47c821efb882be1148d1a7c0c3ee1f71e886`
- `sbom.json` — SHA-256 `63e6ee962325c1626d5df5401a21f3868237794f099ec859638134ec4ff61edf`

## Run

Linux plain binary:

```bash
./videoflow-2.71.0-linux-x86_64 doctor
./videoflow-2.71.0-linux-x86_64 recipe list
./videoflow-2.71.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.71.0-x86_64.AppImage
./VideoFlow-2.71.0-x86_64.AppImage version
./VideoFlow-2.71.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
