# Fact-check, voice repair, and final assembly

## Fact-check audit

`factcheck.audit` compares the dual script against `research/master.json`:

- with an LLM, it returns claims marked `supported`, `unsupported`, or
  `uncertain`, with citations restricted to the master manifest;
- without an LLM, it extracts dates, numbers, and proper names as
  `manual_review` claims;
- invented source URLs are dropped from the report.

It writes `factcheck/report.json` and `report.md`. The HILT
`factcheck_review` gate asks for approval, corrections, patch start/end times,
and optional repair text.

## Voice repair

`voice.patch` replaces a spoken segment in the final master:

- uses an uploaded `audio/voice-patch.wav` from `voice_files`;
- or asks a configured TTS provider to synthesize the repair text;
- splices pre/patch/post with FFmpeg and copies the result to
  `audio/master.wav`;
- records `audio/final-repaired.wav`, the patch source, and the segment range.

This is a repair path, not a voice-clone claim. Voice cloning remains an
explicit provider/consent feature outside this build.

## Final assembly

The HILT `final_review` gate now shows:

- final NLE exports;
- asset licenses and assignments;
- audio QA and repaired master;
- fact-check report.

The final `export.nle` still requires approved licenses. `nle.qa` validates the
exported XML/MLT after the approval.

## Full AI Editor tail

```
sample_review
  → factcheck.audit
  → factcheck_review (human.input)
  → voice_files (human.files, optional)
  → voice.patch
  → final_review (human.gate)
  → export.nle
  → nle.qa
  → export.video
```
