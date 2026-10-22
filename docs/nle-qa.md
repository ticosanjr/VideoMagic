# NLE export QA

## Automated structural validation

`scripts/validate_nle.py` parses the three XML exports and checks the invariants
the importers depend on:

```bash
uv run python scripts/validate_nle.py /path/to/output/exports
```

It checks:

- FCPXML: root, sequence spine, asset-clip, media-rep, transitions, transform
  keyframes.
- XMEML: root, video/audio tracks, clipitems, video transitionitems, motion
  effects.
- Kdenlive: MLT root, profile, chain, video playlist entries, tractors, affine
  filters.

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

## Manual import checklist

Automated XML checks do not prove that an NLE accepts the project. Run this
checklist on a machine with the NLE installed:

### DaVinci Resolve

1. Import `timeline.fcpxml` into a new timeline.
2. Confirm both clips, audio offsets, zoom keyframes, and the crossfade.
3. Confirm media paths resolve without relinking.
4. Render a short range and check for black frames or audio drift.

### Adobe Premiere Pro

1. Import `timeline.xml`.
2. Confirm clip order, J/L-cut offsets, Basic Motion keyframes, and the video
   transition.
3. Check audio fades at the head and tail.
4. Render a short range.

### Kdenlive

1. Open `timeline.kdenlive`.
2. Confirm the sequence and both video/audio tracks.
3. Confirm the affine transform expands to the expected zoom.
4. Confirm the transition produces a visible fade at the cut.
5. Render a short range.

Record the NLE version, OS, import result, and any relinking needed next to the
release notes. Manual import status is still **pending** for this host because
Resolve, Premiere, and Kdenlive are not installed.
