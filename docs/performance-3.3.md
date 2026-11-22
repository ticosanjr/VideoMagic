> Histórico: os scripts de aceitação 3.3 foram removidos na v4.2. O gate atual é `scripts/e2e_micro_gate.py`.

# Performance acceptance — 3.3.0

The 3.3.0 delivery path changes four things at once:

- social MP4 output defaults to **30 fps**;
- the social preset defaults to **veryfast**;
- export QA defaults to **fast**, with full QA in the background;
- segmented video groups are cached across runs.

## How to measure

O harness de aceitação 3.3 foi removido na v4.2. Use o gate atual:

```bash
uv run python scripts/e2e_micro_gate.py --help
```

The historical harness generated a 1920×1080 `testsrc2` source with a 440 Hz tone, exports
with `fps=30`, `preset=veryfast`, and reports:

- source seconds;
- build seconds;
- export seconds;
- realtime factor;
- projected time for an 11-minute deliverable.

`testsrc2` is deliberately high-motion and is a pessimistic proxy for a talking
head. Real footage usually encodes faster and compresses smaller.

## Result on the reference host

```text
Host:        AMD Ryzen 5 PRO 5675U, 12 threads, no NVIDIA GPU
FFmpeg:      6.1.1
Source:      60 s, 1920×1080, 30 fps, H.264
Segments:    11
Build:       12.38 s
Export:      24.96 s
Realtime:    2.40×
Projected:   274.6 s for 11 min (4.6 min)
Target:      < 360 s for 11 min
```

The projection is **4.6 minutes**, inside the 6-minute acceptance target. A full
11-minute run uses the same code path; the 60 s run exists to keep local
iteration cheap. Re-run the full command above on release hardware when the
target needs a recorded, end-to-end number.

## Notes

- Without an NVIDIA GPU the encoder is `libx264 -preset veryfast`. With
  `nvidia-smi` and NVENC available, `vf_export` selects `h264_nvenc`.
- `qa_mode="fast"` validates frames, edge silence, and overlay bounds. Full QA
  (WER, contact sheet, waveform) is dispatched as a background job and does not
  block the measured export.
- The segmented cache is keyed by the group, filters, and output fps. Repeat
  exports reuse unchanged groups.
