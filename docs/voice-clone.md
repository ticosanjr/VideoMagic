# Voice cloning decision

## Status

Deferred for 3.0. No cloning is performed by 2.14.0.

## Why

VideoFlow already supports:

- local Piper and OpenAI-compatible TTS,
- dubbing with duration alignment, review, and fallback,
- voice selection per provider.

No configured provider exposes a documented voice-clone endpoint, and the
project is local-only. Scraping an undocumented clone API or shipping an
unlicensed model would violate the security and licensing posture.

## Behaviour today

- A recipe that asks for a cloned voice falls back to the selected TTS voice.
- The result records `capability_unavailable` with the next action: configure a
  cloning provider or choose a stock voice.
- Dubbing still aligns duration and can be reviewed before render.

## Acceptance for a future release

1. Approved provider with an explicit clone API and licence.
2. Consent record stored with the project (who authorised the voice).
3. Local sample upload inside the allowed roots, never sent without policy.
4. Fake-provider tests for create/clone/synthesize/delete, plus real media smoke.
5. Fallback to the existing TTS path when the clone endpoint is offline.

Until then, the limitation is visible in the UI and release notes.
