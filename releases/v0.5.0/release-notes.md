# VideoFlow 0.5.0

Portable, model-free pre-edit pipeline.

## Artifact

- `videoflow-0.5.0-linux-x86_64`
- SHA-256: `0568d58fdd90ed51e0e6067be28a4107561117116b1eac1bfeb21df55830c008`

## Run

```bash
./videoflow-0.5.0-linux-x86_64 doctor
./videoflow-0.5.0-linux-x86_64 demo -o demo
./videoflow-0.5.0-linux-x86_64 run input.mp4 -o project
./videoflow-0.5.0-linux-x86_64 serve
./videoflow-0.5.0-linux-x86_64 mcp
```

## Windows

The `portable` workflow builds `windows-latest` on a tag, but GitHub Actions on
this private repository currently stops both jobs before the first step (no
runner assigned). Until billing/visibility is sorted out, build the Windows
artifact on a Windows machine:

```powershell
uv sync --extra dev
cd ui; npm ci; npm run build; cd ..
uv run python scripts/build_portable.py --fetch-ffmpeg
```

Then stage and upload it with `scripts/release.py`.

## Notes

See `CHANGELOG.md` for the full list of changes.
