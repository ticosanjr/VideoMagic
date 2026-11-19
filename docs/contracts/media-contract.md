# Media contract

Every boundary validates these invariants before accepting a file.

## Audio

- Final master: 48,000 Hz, stereo, `pcm_s24le` WAV.
- Delivery: 48,000 Hz, stereo, AAC at 192 kbps or higher.
- Loudness: `-16.0 ± 1.0 LUFS`, true peak `<= -1.0 dBTP`.
- Mono repair: if one channel is more than 18 dB quieter and below -50 dBFS,
  duplicate the active channel and record `mono_repaired: true`.

## Video

- SDR delivery: `bt709`, TV range, `yuv420p`.
- Alpha intermediates: `yuva420p`, `yuva444p10le`, or `rgba`.
- Dimensions must be even.
- Frame rate must be an exact rational. The timeline uses 30/1 or 60/1;
  NTSC sources keep 60000/1001 and are converted through the time map.
- Duration and frame count must match the timeline within one frame.

## Alpha

An overlay without a real alpha channel fails with `alpha_channel_missing`.
Opaque full-frame video is valid only when it is not used as a matte.

## Color

10-bit 4:2:2, HLG, and PQ sources require CPU decode and a tonemap to
`bt709`/TV/`yuv420p` before NVENC. S-Log3 or unknown profiles are flagged
instead of applying a channel LUT blindly.
