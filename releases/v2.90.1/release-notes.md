# VideoFlow 2.90.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Artifacts

- `videoflow-2.90.1-linux-x86_64` — SHA-256 `99bd23d8e00414a736c5dbe128b5cbab0bfde26e77e6ddca16b70f3f7796f834`
- `VideoFlow-2.90.1-x86_64.AppImage` — SHA-256 `32f6f7deb68dd00b1e1e2f463c641cb6df715922f13f93ce3bd9f592f4259272`
- `VideoFlow-2.90.1-linux-x86_64.tar.zst` — SHA-256 `3eca3c6679e66f1be1605820194f7b51cc4c1c2d33d4116b5067a4cb81a78138`
- `VideoFlow-2.90.1-mcp-servers.tar.zst` — SHA-256 `679fb3c841109efc3788bf85b27d2283fb98ae578218db80dbb8843d714416dc`
- `sbom.json` — SHA-256 `c8deee8240a12adb77c84dee34e2758e08fe88cd0de1d627ad69f2b0634ae08d`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-2.90.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-2.90.1-linux-x86_64 doctor
./videoflow-2.90.1-linux-x86_64 recipe list
./videoflow-2.90.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-2.90.1-x86_64.AppImage
./VideoFlow-2.90.1-x86_64.AppImage version
./VideoFlow-2.90.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
