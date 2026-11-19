# QA modes

## `fast`

Always validates:

- duration and frame count (`±1 frame`);
- audio 48 kHz and loudness (`-16 ±1 LUFS`, true peak `<= -1.0 dBTP`);
- caption syntax, width, and safe zones when captions exist;
- overlay collisions and alpha where applicable.

It may skip black/freeze detection and WER re-ASR.

## `full`

Adds:

- black and freeze detection;
- contact sheet and waveform;
- WER re-ASR with lexicon normalization.

## Reporting

Each artifact gets its own immutable report:

```text
exports/qa/<artifact>/<run_id>.json
exports/qa/<artifact>/latest.json
```

`vf_qa_compare` compares two reports for duration, WER, loudness, collisions,
and render time.
