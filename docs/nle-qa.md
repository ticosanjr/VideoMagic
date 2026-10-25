# NLE export QA

## Automated structural validation

`scripts/qa_nle.py` adds the 2.4.0 finishing checks and compares an export
against the job output:

```bash
uv run python scripts/qa_nle.py /path/to/output/exports --job-output /path/to/output
```

It fails when an expected native element is missing: markers, titles, colour
filters, the audio master stem on FCPXML, the B-roll lane, or Kdenlive guides.
It also warns when the number of transitions is lower than the number of joins.


`scripts/validate_nle.py` parses the three XML exports and checks the invariants
the importers depend on:

```bash
uv run python scripts/validate_nle.py /path/to/output/exports
```

It checks:

- FCPXML: root, sequence spine, asset-clip, media-rep, transitions, transform
  keyframes, native titles, markers, colour filters, B-roll lane, audio stem.
- XMEML: root, video/audio tracks, clipitems, video transitionitems, motion
  effects, generator titles, markers, colour filters, B-roll track.
- Kdenlive: MLT root, profile, chain, video playlist entries, tractors, affine
  filters, `kdenlivetitle` producers, guides, overlay and stem playlists.

The REST equivalent is:

```http
POST /api/v1/exports/validate
{"output": "/path/to/output"}
```

The route accepts either the output directory or its `exports` directory.

The 0.32.0 AppImage report validated a two-cut timeline with crossfade and
progressive zoom:

- FCPXML: 2 clips, 1 transition, 2 keyframes.
- XMEML: 2 clips, 1 transition, 1 motion effect.
- Kdenlive: 2 clips, 2 affine filters, 4 tractors.

## MLT/Kdenlive render smoke

If `melt` is installed, render the generated project directly:

```bash
uv run python scripts/melt_check.py timeline.kdenlive --output /tmp/kdenlive-smoke.mp4
```

The script returns JSON with `ok`, `returncode`, stdout, and stderr. It is a
stronger check than XML parsing because MLT must resolve the project graph.

The media test `test_kdenlive_project_renders_with_melt` runs this path in CI
when `melt` is available. MLT may warn about missing optional plugins such as
`movit`, `qtblend`, or `affine`; those warnings are reported, not hidden.

## Manual import checklist

Automated XML checks do not prove that an NLE accepts the project. Run this
checklist on a machine with the NLE installed:

### DaVinci Resolve

1. Import `timeline.fcpxml` into a new timeline.
2. Confirm both clips, audio offsets, zoom keyframes, and the crossfade.
3. Confirm native titles, sequence markers, the colour filter, the B-roll lane,
   and the audio master stem.
4. Confirm media paths resolve without relinking.
5. Render a short range and check for black frames or audio drift.

### Adobe Premiere Pro

1. Import `timeline.xml`.
2. Confirm clip order, J/L-cut offsets, Basic Motion keyframes, and the video
   transition.
3. Check audio fades at the head and tail.
4. Confirm the Text generators, markers, colour filter, B-roll track, and audio
   master track.
5. Render a short range.

### Kdenlive

1. Open `timeline.kdenlive`.
2. Confirm the sequence and both video/audio tracks.
3. Confirm the affine transform expands to the expected zoom.
4. Confirm the transition produces a visible fade at the cut.
5. Confirm the title track, guided markers, B-roll overlay, colour filter, and
   audio-master playlist.
6. Render a short range.

Record the NLE version, OS, import result, and any relinking needed next to the
release notes. Manual import status is still **pending** for this host because
Resolve, Premiere, and Kdenlive are not installed.

## Manual sign-off (3.0 gate)

Status: **pending**. Resolve, Premiere, and Kdenlive are not installed on the
release machine, and `melt` is absent. Automated structure validation is green,
but the plan requires a human import pass.

For each NLE, record:

| NLE | Version | Job id | Export folder | Titles | Colour | Audio | B-roll | Chapters | Transitions | Clicks | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DaVinci Resolve | | | | | | | | | | | pending |
| Adobe Premiere | | | | | | | | | | | pending |
| Kdenlive | | | | | | | | | | | pending |

Sign-off block:

- Reviewer:
- Date:
- Build: `releases/v2.14.1/videoflow-2.14.1-linux-x86_64`
- P0/P1 found: none / list
