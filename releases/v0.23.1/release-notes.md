# VideoFlow 0.23.1

This is the hardening release for the recipe engine introduced in 0.23.0.

## Fixed

- **Recipe paths now use the allowlist jail.** `srt_path` in `transcribe` and
  `overlay_path`, `music_path`, `intro_path`, and `outro_path` in
  `shorts.render` are resolved with `resolve_allowed` before a REST or MCP job
  starts. A recipe cannot read `/etc/passwd` or any path outside the configured
  roots.
- **Shorts no longer race retakes.** The built-in `viral_shorts_batch` and
  `full_podcast_curation` recipes now make `shorts.select` depend on
  `retakes.cull`, so selection uses the same cull decisions as the main
  timeline.
- **Operator recipes override built-ins.** A recipe saved under
  `<videoflow-home>/recipes/<id>.json` is loaded before the built-in with the
  same id. Recipe ids are validated before any filesystem lookup.

## Recipe engine

The Recipes tab is the first workspace tab. It edits a versioned JSON DAG with
Svelte Flow, validates it, saves/downloads it, and runs it with live progress.
The same contract is available from:

```bash
videoflow recipe list
videoflow recipe validate recipes/viral_shorts_batch.json
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out
```

REST and MCP expose the same steps, recipes, validation, and run operations.
See `docs/recipes.md`.

## Validation

- 392 Python tests passed; 14 UI tests passed; enforced coverage 98.72%.
- The 0.23.1 AppImage was started from a detached, no-terminal session.
- The recipe endpoint rejected an SRT path outside the allowlist with
  `403 path_not_allowed`.
- A real recipe then ran to `succeeded` on FFmpeg-generated media.
- Opening the AppImage a second time reused the running service.

## Artifacts

- `videoflow-0.23.1-linux-x86_64` — SHA-256 `d9f8f2c97e19ce7bfadc24e9cdfd25e4954a56f0b38d82eec8f1d7d39a5e7b90`
- `VideoFlow-0.23.1-x86_64.AppImage` — SHA-256 `1cfa05d061f03f3552636a80ae183388fa9138c08de77a3236f791752e986d34`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
