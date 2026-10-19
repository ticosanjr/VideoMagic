# Exporters

One timeline model, three NLE dialects, one optional render.

| Target | Artifact | Writer | Status |
| --- | --- | --- | --- |
| DaVinci Resolve | FCPXML 1.9 (1.10 optional) | typed XML builder | implemented |
| Adobe Premiere Pro | FCP 7 XML (`xmeml`) | typed XML builder | implemented |
| Kdenlive 25.04+ | OTIO | `opentimelineio` | implemented |
| Preview / shorts | MP4 | FFmpeg | stub |

All four entry points live in `src/videoflow/exporters/`. `export_timeline`
writes the three timeline artifacts from one validated state.

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
`asset-clip`, which is Apple's documented mechanism for J/L-cuts. xmeml and OTIO
represent it with separate video and audio clips.

## 3. Resolve — FCPXML

Version 1.9 by default; 1.10 is opt-in.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    <format id="r1" name="FFVideoFormat1920x1080p30"
            frameDuration="1/30s" width="1920" height="1080"/>
    <asset id="a1" name="source.mp4" src="file:///media/source.mp4"
           start="0s" duration="3s" hasVideo="1" hasAudio="1"
           format="r1" audioSources="1" audioChannels="1" audioRate="48000"/>
  </resources>
  <library><event name="VideoFlow"><project name="VideoFlow">
    <sequence format="r1" duration="3s" tcStart="0s" tcFormat="NDF">
      <spine>
        <asset-clip ref="a1" name="c1" offset="0s" start="0s"
                    duration="1s" audioStart="0s" audioDuration="49/50s"/>
        <asset-clip ref="a1" name="c2" offset="1s" start="2s"
                    duration="1s" audioStart="59/30s" audioDuration="51/50s">
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
| Source path | `<asset src="file://...">` |
| Frame rate | `<format frameDuration="1/30s">` |
| Video cut | `asset-clip offset`, `start`, `duration` |
| J/L-cut | `audioStart`, `audioDuration` |
| Punch-in | `<adjust-transform scale="1.15 1.15" position="0 180"/>` |
| Pan | `<adjust-transform position="..."/>` |
| Progressive zoom | stored as metadata; keyframes are not emitted yet |
| Fade | stored in state; NLE transitions are not emitted yet |
| Markers | not emitted yet |

Dialect notes:

- `tcFormat` is `DF` only for drop-frame NTSC rates.
- 1.9 is the default because current Resolve imports it reliably. 1.10 is
  available for newer targets.
- The compatibility spike still gates the final dialect: import a straight cut, a
  J-cut, and a punch-in in Resolve before shipping a release.

## 4. Premiere — xmeml

Premiere does not import FCPXML directly. The reliable interchange is FCP 7 XML.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <sequence id="sequence-1">
    <name>VideoFlow</name>
    <duration>60</duration>
    <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
    <media>
      <video>
        <format><samplecharacteristics>
          <width>1920</width><height>1080</height>
          <anamorphic>FALSE</anamorphic>
          <pixelaspectratio>square</pixelaspectratio>
          <fielddominance>none</fielddominance>
          <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
        </samplecharacteristics></format>
        <track>
          <clipitem id="clipitem-1">
            <name>c1</name><duration>90</duration>
            <start>0</start><end>30</end><in>0</in><out>30</out>
            <file id="file-1">
              <name>source.mp4</name>
              <pathurl>file:///media/source.mp4</pathurl>
              <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
              <duration>90</duration>
              <media><video/><audio/></media>
            </file>
          </clipitem>
        </track>
      </video>
      <audio>
        <track>
          <clipitem id="audioitem-1">
            <name>c1</name><duration>90</duration>
            <start>0</start><end>29</end><in>0</in><out>29</out>
            <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>
            <file id="file-1"/>
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
- `pathurl` is a percent-encoded `file://` URI.
- Basic Motion carries the punch-in scale as a percentage.
- Audio transitions are not emitted yet. The model records fade samples for the
  next pass.

## 5. Kdenlive — OTIO

Kdenlive 25.04+ imports OTIO natively.

```python
timeline = otio.schema.Timeline(name="VideoFlow")
video = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
audio = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
```

- One V1 track with frame-based source ranges.
- One A1 track with sample-based source ranges.
- Clip metadata carries `clip_id`, the transform dict, and fade samples.
- Transitions and markers are not emitted yet.

## 6. MP4

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
| `test_xmeml_export_has_separate_video_and_audio_tracks` | Two tracks, different audio start, motion filter |
| `test_otio_export_has_two_tracks` | V1/A1 kinds and clip counts |
| `test_export_service_writes_all_three_targets` | One call, three artifacts |
| `test_export_rejects_*` | Offline media, empty timeline, missing audio, unpacked timeline |
| AC-01 (xfail) | Audio transitions at every join |
| AC-02 | All video times are integer frames; rational FCPXML times |

Normalize before comparing golden files: stable attribute order, absolute paths
replaced with a token, no timestamps.

## 9. Compatibility notes

- Resolve 17.4 imports FCPXML 1.9, not 1.10. Resolve 18.6+ is the modern floor.
- Premiere's FCP XML import is a legacy path. It works, but it is not the primary
  Adobe interchange and it does not accept every FCPXML feature.
- Kdenlive only gained native OTIO import in 25.04. Older versions need the
  deprecated adapter and are unsupported.
- A file that opens in one app is not proof for the others. AC-06 remains a
  three-app manual gate.
