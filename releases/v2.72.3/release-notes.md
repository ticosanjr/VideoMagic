# VideoFlow 2.72.3

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `VideoFlow-2.72.3-linux-x86_64.tar.zst` — SHA-256 `915326def23fc92555a96dc8ddeab6476c8107a3b9e84d2e45a44ffc5e37c578`
- `sbom.json` — SHA-256 `cb3368dd69e78160692fc01f7972dfd17f4943d4dc2ae3afd83f576e9624cc40`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.72.3-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

## Notes

See `CHANGELOG.md`.
