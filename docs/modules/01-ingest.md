# Module 01 — Ingest and normalisation

## Implementation status

Implemented in `adapters/ffmpeg.py`: FFprobe metadata, rational frame rate,
frame count, 16 kHz mono PCM, and SHA-256 digest. Proxy generation and VFR
normalisation are specified but not implemented.

## Purpose

Validate the container, establish the rational timebase, and produce the audio
that every later module uses. Ingest is the only module that reads the source
video container.

## Inputs

- Source path (already checked by the path jail).
- `IngestConfig`.

## Outputs

- `MediaInfo` with `duration_frames`, `fps_num`, `fps_den`, dimensions, and
  `audio_sample_rate`.
- `work/source.wav`: analysis PCM at the source audio rate. Local transcription
  later extracts `work/transcribe.wav` at 16 kHz from the complete source. The
  analysis WAV stays at source rate so VAD spans and ASR timestamps share one
  timebase.
- `work/proxy.mp4`: optional intra-frame preview.
- PCM SHA-256: the **media fingerprint** used by every downstream hash.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `force_cfr` | `true` | Convert VFR to CFR before frame indexing |
| `extract_audio_pcm` | `true` | Produce the analysis WAV |
| `generate_proxy` | `false` | Produce a preview proxy |

## Algorithm

1. Probe with FFprobe JSON output. Read stream time bases, `avg_frame_rate`,
   `r_frame_rate`, duration, dimensions, and sample rate.
2. Decide whether the source is VFR. A mismatch between nominal and average rate,
   or a time-base pattern that changes, means VFR.
3. If `force_cfr`, transcode video to CFR at the declared rational rate. Never
   round 29.97 to 30.
4. Compute `duration_frames` from the CFR stream, not from a rounded seconds
   value.
5. Extract PCM. Apply no loudness normalisation; that would change VAD and
   Whisper behaviour.
6. Hash the PCM file. Store the digest, not the path.
7. If requested, build a proxy with an intra-frame codec. Record that the proxy
   is preview-only.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| File missing or unreadable | `videoflow_error`, no state write |
| No audio stream | Fail; the pipeline is speech-driven |
| Unknown frame rate | Fail with the probe payload |
| VFR that cannot be normalised | Fail rather than guess |
| FFmpeg non-zero exit | Fail with the last stderr lines, redacted |

## Cache

- Hash inputs: module id, version, config, media stats (size + mtime as a hint
  only), and the resolved path.
- Hash outputs: PCM digest becomes the fingerprint for all later modules.
- A copied file with identical PCM reuses downstream caches.

## Tests

| Id | Case |
| --- | --- |
| T-01-01 | 30 fps CFR source yields exact frame count |
| T-01-02 | 29.97 source keeps `30000/1001` |
| T-01-03 | VFR source is converted and the frame count is stable |
| T-01-04 | PCM is 16 kHz mono and hashed |
| T-01-05 | Missing audio fails cleanly |
| T-01-06 | A touched file with identical PCM keeps downstream hashes |
| T-01-07 | Proxy is not used by VAD or Whisper |

AC: 02, 05, 08.
