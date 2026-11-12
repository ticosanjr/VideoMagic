# Voice cloning decision

## Status

Optional in 2.68.0. The default provider is `none`; ElevenLabs cloning is
enabled only when `VIDEOWFLOW_VOICE_CLONE_PROVIDER=elevenlabs` and the
`ELEVENLABS_API_KEY` secret are configured.

## Why

VideoFlow already supports:

- local Piper and OpenAI-compatible TTS,
- dubbing with duration alignment, review, and fallback,
- voice selection per provider.

The default remains local-only. The optional provider uses the documented
ElevenLabs voice API, requires an explicit consent reference and server-local
reference samples, and is never enabled implicitly. Shipping a local clone model
would require a separate licence/size decision.

## Behaviour today

- With no provider, a recipe that asks for a cloned voice falls back to the
  selected TTS voice or an uploaded patch.
- With ElevenLabs configured, `voice.clone` creates a profile from reference
  samples and synthesizes the repair line into `audio/voice-patch.mp3`.
- `voice.patch` prefers a human-uploaded WAV, then the clone MP3, then TTS.
- The result records `capability_unavailable` with the next action: configure a
  cloning provider or choose a stock voice.
- Dubbing still aligns duration and can be reviewed before render.

## Acceptance for a future release

1. Approved provider with an explicit clone API and licence.
2. Consent record stored with the project (who authorised the voice).
3. Local sample upload inside the allowed roots, never sent without policy.
4. Fake-provider tests for create/clone/synthesize/delete, plus real media smoke
   (fake-provider tests are in place; real media smoke remains a release item).
5. Fallback to the existing TTS path when the clone endpoint is offline.

Until then, the limitation is visible in the UI and release notes.
