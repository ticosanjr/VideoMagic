# VideoFlow 0.7.0

Portable, model-free pre-edit pipeline.

## Artifact

- `videoflow-0.7.0-linux-x86_64`
- SHA-256: `c2df1959bc50806c77e14056d3a451dcaf41278a5a56c10d3a016a3429dfa473`

## Run

```bash
./videoflow-0.7.0-linux-x86_64 doctor
./videoflow-0.7.0-linux-x86_64 demo -o demo
./videoflow-0.7.0-linux-x86_64 run input.mp4 -o project
./videoflow-0.7.0-linux-x86_64 serve
./videoflow-0.7.0-linux-x86_64 mcp
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
