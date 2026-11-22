# Cycle 2 gate

Historical evidence from the removed cycle 2 gate.

## Result

```text
PASS  3 Shorts from the edited timeline (9:16, 4:5, intro PNG)
PASS  30 fps CFR
PASS  duration within tolerance and ±2 frames
PASS  48 kHz stereo audio
PASS  -15.5 ± 1.5 LUFS
PASS  caption safe zones, <=18 chars/line, no literal color tags
PASS  pad floor 110/190 ms with valley RMS
```

Machine-readable result: `docs/qa-evidence/cycle2-gate.json`.

## Clips

| Clip | Aspect | Duration | FPS | LUFS | Caption zone |
| --- | --- | ---: | ---: | ---: | --- |
| Vertical 30 | 9:16 | 30.000 s | 30 | -15.5 | `\pos(500,1340)` |
| Feed 30 | 4:5 | 30.000 s | 30 | -15.5 | MarginV 189 |
| Intro 30 | 9:16 | 32.000 s | 30 | -15.4 | `\pos(500,840)` |

Intro clip uses a real PNG (`-loop 1` internally) and the `.ass` is shifted once
by 2 seconds.

## Checks

- edited-timeline `timeline_to_source` mapping;
- 30 fps CFR batch;
- frame tolerance `max(2, segments)`;
- video/audio drift `<= 0.05 s`;
- `loudnorm I=-15.5 TP=-1.5 LRA=9`;
- safe-zone captions with `WrapStyle: 2`, MarginL 60 / MarginR 160;
- no event extends past `duration - 0.05`;
- pad floor after snap, `valley_rms_dbfs` populated.
