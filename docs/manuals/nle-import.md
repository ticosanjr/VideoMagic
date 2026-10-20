# NLE import manual

The last mile cannot be automated. This is the click path and acceptance check
for each editor.

## 1. DaVinci Resolve

Minimum: 18.6. Newer 19/20 releases are preferred for FCPXML 1.10.

1. Open Resolve and create or open a project.
2. Set the timeline frame rate to match the source before importing. A mismatch
   can cause Resolve to retime clips.
3. File → Import → Timeline.
4. Choose `.videoflow/exports/timeline.fcpxml`.
5. In the import dialog, confirm the frame rate and the timeline name.
6. Resolve creates a timeline in the media pool.
7. Open it. Check:
   - video clips are in order;
   - audio starts before video at a J-cut (zoom into the waveform);
   - a punch-in clip is visibly scaled;
   - no red offline media.
8. Play each join with headphones. There must be no click.

If the file is rejected:

- confirm the FCPXML version (1.9 for older Resolve);
- check that the source path is still online and that the path is absolute;
- try a minimal straight-cut export to isolate a transform issue;
- export xmeml and import it into Premiere to see whether the timeline itself is
  valid.

Do not "fix" the exporter by adding attributes Resolve ignores. Record the
version and the failing element.

## 2. Adobe Premiere Pro

Premiere does not import FCPXML. Use the `.xml` (FCP 7 XML) artifact.

1. Open Premiere and create a sequence at the source frame rate.
2. File → Import.
3. Choose `.videoflow/exports/timeline.xml`.
4. Select the sequence in the bin and open it.
5. Check:
   - separate video and audio tracks exist;
   - a J-cut has audio earlier than its video;
   - motion scale is applied;
   - audio transitions are present at joins.
6. Link offline media if Premiere asks. Prefer relinking to the original source.

Common issues:

| Symptom | Cause | Action |
| --- | --- | --- |
| Nothing imports | Wrong artifact (`.fcpxml`) | Use `.xml` |
| Premiere imports but media is offline | The clipitem only had a file reference | Use the full `<file>` definition the exporter now writes |
| Audio and video identical | xmeml written as a single track | Split the tracks |
| Motion missing | Filter not on the clipitem | Add `basicmotion` |
| Sequence rate wrong | Missing `rate`/`ntsc` | Fix the writer, not the timeline |

## 3. Kdenlive

Minimum: 23.04. The artifact is a native `.kdenlive` MLT XML project, not OTIO.

1. Open Kdenlive.
2. File → Open.
3. Choose `.videoflow/exports/timeline.kdenlive`.
4. Save a copy if Kdenlive asks to upgrade the project format.
5. Check:
   - V1 and A1 exist as separate tracks;
   - a J-cut is visible as an audio clip that starts earlier;
   - the timeline duration matches the run summary;
   - no missing clips.
6. Play the joins.

If Kdenlive reports an MLT error, keep the `.kdenlive` file and the profile
(frame size and rate) for the bug report. Do not replace it with OTIO; OTIO is
no longer the Kdenlive deliverable.

## 4. Acceptance checklist

For each editor, record:

- [ ] app version
- [ ] artifact version and dialect
- [ ] timeline frame rate
- [ ] clip count matches the export
- [ ] J-cut audio offset is visible
- [ ] punch-in is visible
- [ ] no offline media
- [ ] no click at three sampled joins
- [ ] 60-minute import holds lip sync at the end

Any unchecked box blocks AC-06.

## 5. What to send back

If an import fails, provide:

1. the app and exact version;
2. the artifact (or a minimal three-clip version);
3. the error text or a screenshot;
4. whether a straight-cut export imports;
5. the source frame rate and duration.

Do not send private media. Reproduce with the synthetic fixture in
`tests/fixtures/`.
