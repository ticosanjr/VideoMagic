# Settings

`settings.json` under the VideoFlow home stores the local configuration. An
unreadable file falls back to defaults and is reported through
`GET /api/v1/system` (`settings_error`) and the doctor checks. The
Settings tab adds search, units, help tips, and a discard-changes action.

| Section | Fields | Notes |
| --- | --- | --- |
| Runtime | host, port, log level, locale, max jobs, history, open browser | Host/port changes need a service restart |
| Paths | allowed roots, FFmpeg/FFprobe, cache, models, output, temp | Allowed roots gate every file access |
| Models | default per capability, device, compute type, threads, HF token env | Empty default lets the engine pick |
| Automation and quality | scheduler interval, retries, backoff, target LUFS, true peak, VMAF, proxy height | Quality values feed audio/visual QA |
| LLM and speech | temperature, timeout, max tokens, retries, JSON mode, ASR profile/engine/language/device, beam, CPU threads, word timestamps, VAD, remote ASR endpoint/model/key env | See [asr.md](asr.md) |
| Intelligence | provider order, OpenCode V2, DeepSeek, network, budget, timeout | See [intelligence.md](intelligence.md) |
| Headless / MCP | MCP-only mode, UI/tray startup, HILT pollers | See [mcp.md](mcp.md) |
| Sync | offset mode, offset ms, drift threshold, reference audio | Applied only above threshold |
| Render | serialized heavy renders, draft scale, motion blur, concurrency | Draft is for review, not final export |
| QA | visual FPS, window pad, fail-on-defect, backends | 10 FPS windowed audit |
| Web render | engine, browser, network, timeout | External Node/Chrome runtime |
| Presets | channel directory, max rules | Rulebooks are versioned JSON |
| TTS, stock, translation, UI | TTS voice/model, stock provider, translation, theme, density, locale | Theme/density are shell-only |
| Notifications | master switch, in-app/desktop levels, event checkboxes, local log/desktop, HILT delivery channels | Off by default; `required` keeps only human interaction, `important` adds failures, `all` adds routine events |

Search filters sections by their visible text. `Discard changes` reloads the
saved file without touching the server. `Reset` restores server defaults and
asks for confirmation.
