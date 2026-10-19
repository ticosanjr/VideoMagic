# VideoFlow 0.6.0

Portable, model-free pre-edit pipeline.

## Artifact

- `videoflow-linux-x86_64`
- SHA-256: `2b40cc40694b9d3b0d8b4e775d83a2ba32a750d04ce721d3156007d95f0356df`

## Run

```bash
./videoflow-linux-x86_64 doctor
./videoflow-linux-x86_64 demo -o demo
./videoflow-linux-x86_64 run input.mp4 -o project
./videoflow-linux-x86_64 serve
./videoflow-linux-x86_64 mcp
```

## Windows

The `portable` workflow builds `windows-latest` on a tag when Actions runners and
minutes are available. Otherwise build on Windows and stage the result:

```powershell
uv sync --extra dev
cd ui; npm ci; npm run build; cd ..
uv run python scripts/build_portable.py --fetch-ffmpeg
uv run python scripts/release.py
```

## Notes

See `CHANGELOG.md` for the full list of changes.
