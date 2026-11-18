# Beatmap v2

`vf_timeline(action="apply_beatmap")` applies one declarative manifest
atomically. A validation error leaves the timeline untouched.

## Fields

```json
{
  "revision": 1,
  "time_basis": "timeline",
  "keep_ranges": [{"start_sec": 0, "end_sec": 30}],
  "remove_ranges": [{"start_sec": 45, "end_sec": 50}],
  "cuts": [{"start_frame": 10, "end_frame": 40}],
  "transitions": [
    {
      "clip_id": "c1",
      "type": "wipe_left",
      "duration_frames": 8,
      "linked_sfx": "assets/sfx/whoosh.wav"
    }
  ],
  "broll": [
    {
      "path": "assets/broll/x.mp4",
      "start_frame": 20,
      "duration_frames": 60,
      "layout": "pip_top_right"
    }
  ],
  "graphics": [
    {
      "path": "assets/graphics/card.mov",
      "start_frame": 20,
      "duration_frames": 30,
      "engine": "hyperframes",
      "alpha": true
    }
  ],
  "captions": [
    {"text": "primeira frase", "start_frame": 0, "end_frame": 30}
  ],
  "sfx_events": [],
  "music_tracks": []
}
```

## Ranges and safety

- `keep_ranges` and `remove_ranges` are seconds in `time_basis`
  (`timeline` by default, or `source`).
- `cuts` is still accepted as a timeline-frame keep-list for 3.0
  compatibility, with a warning. New callers should use `keep_ranges` or
  `remove_ranges`.
- `dry_run=true` returns `before_duration_sec`, `after_duration_sec`,
  `delta_sec`, `delta_pct`, and `affected_clips` without saving.
- An edit that removes more than 50% of the timeline aborts unless
  `force=true`.
- Every saved beatmap edit creates a `history/rev_NNN.json` snapshot;
  `vf_project(action="history" | "undo" | "restore")` operates on those
  revisions.

## Transitions

- `crossfade`
- `fade_to_black`
- `wipe_left`
- `wipe_right`
- `slide_up`
- `zoom_in`
- `whip_pan`
- `glitch`

XFade transitions are mapped to FFmpeg `xfade` effects; `fade_to_black` uses
fade filters. Every video chain is normalized to `setsar=1`.

## B-roll layouts

- `fullscreen`
- `pip_top_right`
- `split_screen`
- `cutout_overlay`
- `ken_burns`
- `transformative_crop`

## Overlay motion

B-roll overlays carry `ken_burns` and `transformative_crop`. The MP4 exporter
applies a slow zoom/crop before scaling and positioning, and normalizes SAR.

## Captions and audio

Beatmap captions are written to `captions/beatmap.ass`; if `subtitles.ass` does
not exist, the same file is copied as the export subtitle track. Linked SFX are
placed at the transition start. Music supports a three-act arc with ducking.
