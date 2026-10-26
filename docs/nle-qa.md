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

The automated report validates a two-cut timeline with crossfade and progressive
zoom:

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

### Kdenlive

1. Open `timeline.kdenlive`.
2. Confirm the sequence and both video/audio tracks.
3. Confirm the affine transform expands to the expected zoom.
4. Confirm the transition produces a visible fade at the cut.
5. Confirm the title track, guided markers, B-roll overlay, colour filter, and
   audio-master playlist.
6. Render a short range.

Record the NLE version, OS, import result, and any relinking needed next to the
release notes. Manual import status is still **pending** for this host.
Kdenlive 26.08.2 is installed via Flatpak (`org.kde.kdenlive`).

## Manual sign-off (3.0 gate)

Status: **pending**. Kdenlive 26.08.2 is installed via Flatpak
(`org.kde.kdenlive`) and is the only NLE in the QA plan. `melt` is absent, so
the optional MLT CLI smoke is skipped. Automated structure
validation is green, but a human Kdenlive import pass is still required.

Record:

| NLE | Version | Job id | Export folder | Titles | Colour | Audio | B-roll | Chapters | Transitions | Clicks | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kdenlive | 26.08.2 | | | | | | | | | | pending |

Sign-off block:

- Reviewer:
- Date:
- Build: `releases/v2.21.0/videoflow-2.21.0-linux-x86_64`
- P0/P1 found: none / list
