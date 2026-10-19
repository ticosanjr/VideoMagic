# Releases

Every release gets a versioned folder:

```
releases/v0.4.0/
  videoflow-linux-x86_64    # local artifact, ignored by git
  SHA256SUMS                # tracked
  manifest.json             # tracked
  release-notes.md          # tracked
```

## Policy

1. Stage the artifact with `uv run python scripts/release.py --version X.Y.Z`.
2. Verify `doctor`, `demo`, and the three exports on the staged binary.
3. Commit the notes, checksums, and manifest. The binary is ignored because
   GitHub rejects files over 100 MB in normal git history.
4. Upload the binary as a GitHub Release asset:

```bash
gh release create vX.Y.Z releases/vX.Y.Z/<asset> \
  --title "VideoFlow X.Y.Z" \
  --notes-file releases/vX.Y.Z/release-notes.md
```

Windows artifacts are built by the `portable` CI workflow and attached to the
same release. A release is not complete until Linux and Windows assets exist and
their checksums are recorded here.

## Current

- `v0.6.0`: Linux x86_64, static FFmpeg. SRT retakes and LLM guard.
- `v0.5.0`: Linux x86_64, static FFmpeg. UI drives real jobs. Windows pending CI.
- `v0.4.0`: Linux x86_64, static FFmpeg, 168 MB. Windows pending CI.
