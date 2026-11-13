# Speech recognition profiles

Transcription is chosen per run, not hard-coded. The default profile is
`balanced`, which uses a Faster-Whisper large-v3-turbo model when installed,
greedy decoding (`beam_size=1`), VAD, and physical CPU cores.

## Profiles

| Profile | Engine | Model | Decoding |
| --- | --- | --- | --- |
| `auto` | best available | follows the saved profile | follows the profile |
| `balanced` | Faster-Whisper | `large-v3-turbo`, then `large-v3`, medium, small | beam 1, VAD on, 6 threads on a 6-core CPU |
| `fast` | Faster-Whisper | small, base, tiny | beam 1, VAD on |
| `quality` | Faster-Whisper | large-v3, turbo, medium | beam 5, VAD on |
| `vulkan` | whisper.cpp | `whisper-large-v3-turbo-q5_0` | beam 1, flash attention, Vulkan |
| `remote` | HTTP ASR | configured remote model | server-side |
| `custom` | explicit step settings | explicit `model_id` | explicit beam/threads/words |

Set the default in **Settings → LLM and speech → ASR profile**. A recipe step
can override it with `quality_profile`, `beam_size`, `cpu_threads`,
`word_timestamps`, `vad_filter`, and `condition_on_previous_text`.

`word_timestamps=off` keeps sentence timings only. Leave it on (`auto` or
`always`) when the recipe uses word-level retakes, drift repair, or recut.

## Model downloads

Install **Faster-Whisper large-v3-turbo** in Setup → AI models. If it is not
installed, `balanced` falls back to an installed large-v3/medium/small model.
The whisper.cpp profile also needs `whisper-large-v3-turbo-q5_0`.

## Vulkan

Build whisper.cpp with Vulkan when `glslc` is available:

```bash
PATH=/path/to/glslc:$PATH \
LD_LIBRARY_PATH=/path/to/libshaderc:$LD_LIBRARY_PATH \
uv run python scripts/fetch_whisper.py --vulkan --refresh
```

`scripts/build_portable.py --with-whisper --whisper-vulkan` includes the
Vulkan build. The `--vulkan` profile only activates when:

1. `vendor/whisper/vulkan.flag` or `VIDEOWFLOW_WHISPER_VULKAN=1` is present;
2. a `whisper-cli` binary is found;
3. `vulkaninfo --summary` does not report only `llvmpipe`.

If any check fails, the run falls back to `balanced` and logs the reason.
`vulkaninfo` on a remote/headless X session can report llvmpipe even when the
Radeon driver is loaded; in that case Vulkan does not accelerate whisper.cpp.

## Remote ASR

Set **Remote ASR URL**, model, and key environment in Settings, or use the
`remote` profile in a step. The endpoint must accept an OpenAI-compatible
`/audio/transcriptions` request (multipart `file`, `model`, `language`) and
return segments with word timestamps when word-level editing is needed.

Example server on a LAN/Tailscale GPU host:

```bash
uvicorn asr_server:app --host 0.0.0.0 --port 8000
```

Point `remote_base_url` at `http://<tailscale-ip>:8000/v1`.

## Measured on the Ryzen 5 PRO 5675U (6C/12T, no usable Vulkan device)

`scripts/benchmark_asr.py` with an 11 s speech sample:

| Configuration | Elapsed | RTF |
| --- | ---: | ---: |
| large-v3, beam 5, 4 threads, no VAD, words | 36.9 s | 0.30 |
| large-v3-turbo, beam 1, 6 threads, VAD, words | 13.3 s | 0.83 |

With a 110 s sample:

| Configuration | Elapsed | RTF |
| --- | ---: | ---: |
| balanced (turbo) | 108 s | 1.02 |
| fast (small) | 91.6 s | 1.20 |
| turbo with 8 threads | 110 s | 1.00 |
| turbo with 12 threads | 153 s | 0.72 |

The 6-physical-core setting is the sweet spot; 12 SMT threads are slower.
whisper.cpp large-v3-turbo on CPU is slower than Faster-Whisper on this host
(~34 s for 11 s of audio), so the Vulkan profile must only activate with a real
Vulkan device.

## Speed notes

- The old large-v3 + beam 5 + 4 threads + no VAD combination is the slow path.
- Balanced/turbo/greedy is the default speed-oriented profile.
- Actual RTF is logged at the end of the step; use `scripts/benchmark_asr.py`
  to compare profiles on a 60–120 s sample.
- `large-v3` remains available through the `quality` or `custom` profile.
- On this host, `vulkaninfo --summary` reports llvmpipe only, so the Vulkan
  profile intentionally falls back to balanced. A working Radeon Vulkan ICD is
  required for the 8–12 minute estimate.
