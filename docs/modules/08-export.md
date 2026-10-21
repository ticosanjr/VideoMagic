# Module 08 — Export

## Implementation status

FCPXML 1.9/1.10, xmeml, and native Kdenlive MLT XML are implemented and
covered by contract tests. `export_timeline` writes all three from one state.
Audio fades are emitted in all three dialects: xmeml `transitionitem` entries,
Kdenlive keyframed `volume` filters, and FCPXML `adjust-volume` ramps. Keyframed
progressive zooms and MP4 render are still pending. The three-app import spike is
a release gate.

## Purpose

Compile the timeline into files that open in three NLEs, and optionally render
shorts.

## Inputs

- `ProjectState`: media info, video and audio segments, transforms, vertical clips.
- `ExportConfig`.

## Outputs

```
.videoflow/exports/
  timeline.fcpxml      # Resolve
  timeline.xml         # Premiere (xmeml)
  timeline.kdenlive    # Kdenlive
  shorts/<title>.mp4   # optional
```

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `fcpxml_dialect` | `1.9` | 1.9 or 1.10 |
| `write_fcpxml` | `true` | Resolve artifact |
| `write_xmeml` | `true` | Premiere artifact |
| `write_otio` | `true` | Kdenlive artifact (historical key; writes MLT XML) |
| `write_mp4` | `false` | Direct render |

## Algorithm

1. Run the shared preflight from [exporters.md](../exporters.md).
2. Build one immutable timeline view: assets, video segments, audio segments,
   transforms, markers.
3. Write enabled artifacts from that view.
4. Validate each artifact: parse it back, check frame counts and clip counts,
   and confirm the required root element and media references.
5. Write atomically to `exports/`.
6. Return the artifact map.

Export never re-runs analysis and never mutates state.

## Dialect selection

| Target | Writer |
| --- | --- |
| Resolve | FCPXML, rational time, `adjust-transform` |
| Premiere | xmeml, separate video/audio tracks, motion filter |
| Kdenlive | native `.kdenlive` MLT XML, video/audio tractors, sequence tractor |

`videoflow_export_fcpxml` uses `target_nle` to choose. The function name is
historical; the artifact extension follows the target.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Offline media | Fail before writing |
| Zero segments | Fail |
| Overlap | Fail with clip ids |
| No fade at a join | Fail; the cut engine must fix it |
| Write permission denied | Fail, no partial file |
| One target fails | Fail the module; do not report success for the others |

## Tests

| Id | Case |
| --- | --- |
| T-08-01 | Straight-cut golden file matches |
| T-08-02 | J-cut golden file has offset audio |
| T-08-03 | Punch-in golden file carries transform |
| T-08-04 | Every join contains a fade |
| T-08-05 | `target_nle=premiere` writes xmeml, not fcpxml |
| T-08-06 | Offline media fails before writing |
| T-08-07 | Artifacts parse back |
| T-08-08 | Export is the only module dirty after a zoom change |
| T-08-09 | MP4 is skipped when FFmpeg is absent, timeline files still succeed |

AC: 01, 02, 05, 06.
