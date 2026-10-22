# Exporters

One timeline model, three NLE dialects, one optional render.

| Target | Artifact | Writer | Status |
| --- | --- | --- | --- |
| DaVinci Resolve | FCPXML 1.9 (1.10 optional) | typed XML builder | implemented |
| Adobe Premiere Pro | FCP 7 XML (`xmeml`) | typed XML builder | implemented |
| Kdenlive 23.04+ | native `.kdenlive` MLT XML | typed XML builder | implemented |
| Preview / main timeline / shorts | MP4 | FFmpeg | implemented |

All exporters live in `src/videoflow/exporters/`. `export_timeline` writes the
three timeline artifacts from one validated state.

## 1. Shared preflight

Every exporter runs the same checks before writing:

1. `media_info` exists and the source file is online.
2. At least one video segment exists.
3. Clip ids are unique and every video segment has exactly one audio segment.
4. Every source range is inside the media.
5. Video timeline is packed from frame zero; audio timeline is packed from sample
   zero.
6. The output directory exists or is created, and the write is atomic (temp file,
   then replace).

Failure is an `export_failed` error, not a partially valid file.

## 2. Audio offsets

A J/L-cut changes the audio cut point while each clip's audio stays at the same
source-to-timeline offset as its own video. That preserves sync and keeps one
contiguous audio track.

- **J-cut:** audio of the incoming clip starts earlier and the outgoing clip's
  audio ends earlier by the same amount. The picture cut does not move.
- **L-cut:** the opposite. The outgoing audio runs longer and the incoming audio
  starts later.
- A shift is applied only when the removed-silence gap is at least `offset_ms`
  (`handle_check`). Otherwise the join stays straight and the build reports a
  warning.

FCPXML represents this with `audioStart` and `audioDuration` on the composite
`asset-clip`, which is Apple's documented mechanism for J/L-cuts. xmeml and MLT
represent it with separate video and audio clips. xmeml emits single-sided
audio `transitionitem` fades; Kdenlive emits keyframed `volume` filters.
FCPXML emits keyframed ``adjust-volume`` fades on the composite
``asset-clip``.

## 3. Resolve — FCPXML

Version 1.9 by default; 1.10 is opt-in.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormat1920x1080p30"
            frameDuration="1/30s" width="1920" height="1080"/>
    <asset id="a1" name="source.mp4"
           start="0s" duration="3s" hasVideo="1" hasAudio="1"
           format="r1" videoSources="1" audioSources="1"
           audioChannels="1" audioRate="48000">
      <media-rep kind="original-media" src="file:///media/source.mp4"/>
    </asset>
  </resources>
  <library><event name="VideoFlow"><project name="VideoFlow">
    <sequence format="r1" duration="3s" tcStart="0s" tcFormat="NDF"
              audioLayout="mono" audioRate="48k">
      <spine>
        <asset-clip ref="a1" name="c1" offset="0s" start="0s"
                    duration="1s" audioStart="0s" audioDuration="49/50s"
                    srcEnable="all" audioRole="dialogue"/>
        <asset-clip ref="a1" name="c2" offset="1s" start="2s"
                    duration="1s" audioStart="59/30s" audioDuration="51/50s"
                    srcEnable="all" audioRole="dialogue">
          <adjust-transform scale="1.15 1.15" position="0 180"/>
        </asset-clip>
      </spine>
    </sequence>
  </project></event></library>
</fcpxml>
```

Mapping:

| Timeline concept | FCPXML |
| --- | --- |
| Source path | `<asset><media-rep src="file://..."/></asset>` |
| Frame rate | `<format frameDuration="1/30s">` |
| Video cut | `asset-clip offset`, `start`, `duration` |
| J/L-cut | `audioStart`, `audioDuration` |
| Punch-in | `<adjust-transform scale="1.15 1.15" position="0 180"/>` |
| Pan | `<adjust-transform position="..."/>` |
| Progressive zoom | FCPXML `adjust-transform` scale keyframes, XMEML Basic Motion keyframes, MP4 `zoompan`, and Kdenlive affine `transition.rect` keyframes |
| Transitions | FCPXML `transition`, XMEML video `transitionitem`, MP4 `xfade`/fades, Kdenlive affine opacity/volume fades |
| Fade | keyframed `adjust-volume` ramp inside the `asset-clip` |
| Markers | not emitted yet |

Audio fades use clip-relative volume keyframes:

```xml
<adjust-volume>
  <param name="amount">
    <keyframeAnimation>
      <keyframe time="0s" value="-60dB" interp="linear"/>
      <keyframe time="1/50s" value="0dB" interp="linear"/>
      <keyframe time="1s" value="0dB" interp="linear"/>
      <keyframe time="51/50s" value="-60dB" interp="linear"/>
    </keyframeAnimation>
  </param>
</adjust-volume>
```

Dialect notes:

- `tcFormat` is `DF` only for drop-frame NTSC rates. The sequence `audioRate`
  uses FCPXML's enumerated labels (`48k`, `44.1k`, ...), not raw hertz.
- Fade ramps use the DTD form `param > keyframeAnimation > keyframe`, with
  clip-relative times and `-60dB` at the silent edge.
- 1.9 is the default because current Resolve imports it reliably. 1.10 is
  available for newer targets.
- The compatibility spike still gates the final dialect: import a straight cut, a
  J-cut, and a punch-in in Resolve before shipping a release.

## 4. Premiere — xmeml

Premiere's reliable interchange path is FCP 7 XML version 4. It does not import
FCPXML directly.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
  <sequence id="sequence-1" explodedTracks="true">
    <uuid>...</uuid>
    <name>VideoFlow</name>
    <duration>60</duration>
    <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
    <timecode>...</timecode>
    <media>
      <video>
        <format><samplecharacteristics>...</samplecharacteristics></format>
        <track>
          <clipitem id="clipitem-1">
            <name>c1</name><duration>90</duration>
            <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
            <start>0</start><end>30</end><in>0</in><out>30</out>
            <file id="file-video-1">
              <name>source.mp4</name>
              <pathurl>file://localhost/media/source.mp4</pathurl>
              <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
              <duration>90</duration>
              <media><video>...</video><audio>...</audio></media>
            </file>
            <link><linkclipref>clipitem-1</linkclipref>...</link>
            <link><linkclipref>audioitem-1</linkclipref>...</link>
          </clipitem>
        </track>
      </video>
      <audio>
        <format>...</format>
        <track>
          <clipitem id="audioitem-1">
            <name>c1</name><duration>90</duration>
            <start>0</start><end>29</end><in>0</in><out>29</out>
            <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>
            <file id="file-audio-1">...</file>
            <link><linkclipref>clipitem-1</linkclipref>...</link>
            <link><linkclipref>audioitem-1</linkclipref>...</link>
          </clipitem>
        </track>
      </audio>
    </media>
  </sequence>
</xmeml>
```

Rules:

- Frame counts, not seconds. Fractional rates use `ntsc=TRUE` and the integer
  timebase.
- `version="4"` and `explodedTracks="true"` match Premiere's own FCP XML path.
- Every video and audio clipitem carries a full `<file>` definition. A bare
  `<file id="..."/>` reference does not reliably create linked media.
- `pathurl` is a percent-encoded `file://localhost/` URL. Windows drive letters
  are written as `C%3a`.
- Both sides of an A/V link carry two `<link>` elements with the same
  `groupindex`.
- Basic Motion carries the punch-in scale as a percentage.
- Audio transitions are single-sided `transitionitem` fades around each audio
  clip edge, using the Cross Fade (0 dB) transition ID.

## 5. Kdenlive — native MLT XML

Kdenlive's own `.kdenlive` project is MLT XML. The exporter writes that native
format instead of asking Kdenlive to import OTIO.

- One `main_bin` playlist holds the sequence and source clip.
- One video tractor (`playlist0`) and one audio tractor (`playlist1`).
- A sequence tractor with a stable `kdenlive:uuid`, `qtblend` video compositing,
  and a `mix` audio transition.
- Source ranges use frame timecodes; sample ranges are converted to frames.
- `kdenlive:clipname`, `kdenlive:sequenceproperties.trackCount`, and the
  document properties are written so Kdenlive opens the project as a normal
  sequence rather than a loose MLT graph.
- Audio fades are keyframed `volume` filters. Punch-in transforms are not
  emitted yet.

The target key in the API remains `kdenlive`; the artifact is
`timeline.kdenlive`. The historical `write_otio` config field now controls this
Kdenlive artifact. `export_otio` remains available as a library helper for other
OTIO hosts, but it is not the Kdenlive deliverable.

## 6. MP4

The direct MP4 exporter builds a filter graph from the validated timeline:

- video: `trim` + `setpts` + optional static scale/crop, then `concat`;
- audio: `atrim` + `asetpts` + optional fades, then `concat`;
- output: H.264 (`libx264`), AAC, `+faststart`.

`export.nle` accepts `mp4` as a target. The render is not a replacement for the
NLE master; it is the direct review/social deliverable.

FFmpeg direct render is for shorts and previews. It is a stub. When implemented it
will apply the cull list, transforms, and fades, burn subtitles, and write
H.264/AAC at 1080x1920 for vertical or source resolution for preview. It never
replaces the timeline artifacts.

## 7. Subtitles

Two stages:

1. ASS generation from word timings, with `tiktok_bold`, `minimalist_box`, or
   `highlight_word`.
2. FFmpeg burns the ASS file for a short or preview.

Jinja2 is allowed for ASS templates. It is not used for FCPXML or xmeml.

## 8. Tests

| Test | Assertion |
| --- | --- |
| `test_fcpxml_export_uses_audio_offset_and_transform` | Version, clip count, J-cut audio offset, transform |
| `test_xmeml_export_has_separate_video_and_audio_tracks` | Version 4, full files, link groups, different audio start, motion filter |
| `test_kdenlive_export_is_a_native_mlt_project` | MLT root, profile, source chain, tracks, sequence tractor, final tractor |
| `test_otio_export_has_two_tracks` | Legacy OTIO helper: V1/A1 kinds and clip counts |
| `test_export_service_writes_all_three_targets` | One call, `.fcpxml`, `.xml`, `.kdenlive` artifacts |
| `test_export_rejects_*` | Offline media, empty timeline, missing audio, unpacked timeline |
| AC-01 (xfail) | Audio transitions at every join |
| AC-02 | All video times are integer frames; rational FCPXML times |

Normalize before comparing golden files: stable attribute order, absolute paths
replaced with a token, no timestamps.

## 9. Compatibility notes

- Resolve 17.4 imports FCPXML 1.9, not 1.10. Resolve 18.6+ is the modern floor.
  FCPXML 1.9 media must use `<media-rep>`; the old `<asset src>` form is only for
  FCPXML 1.8 and earlier.
- Premiere's FCP XML import is a legacy path. Version 4 with full file
  definitions and explicit A/V links is the reliable shape.
- Kdenlive 23.04+ opens native `.kdenlive` MLT projects. OTIO remains available
  as a library helper, but it is not the Kdenlive deliverable.
- A file that opens in one app is not proof for the others. AC-06 remains a
  three-app manual gate.
