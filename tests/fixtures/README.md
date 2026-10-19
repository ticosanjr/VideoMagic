# Fixtures

This directory intentionally contains no copyrighted media. Synthetic fixtures are
generated with FFmpeg `lavfi` sources by tests marked `media`:

```bash
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -t 60 -c:v libx264 -pix_fmt yuv420p -c:a aac tests/fixtures/generated/sample.mp4
```

Speech-shaped fixtures use a tone gated by silence, never a real voice. Golden
FCPXML, xmeml, and OTIO files will live here once the exporter pass lands.
