"""Human-facing metadata for every step parameter.

The Pydantic models define types and bounds; this module adds the copy that the
UI, MCP clients, and documentation need: a readable label, description, unit,
group, optional control override, and placeholder.

Keeping the copy here avoids 47 near-identical edits to the models and makes it
possible to audit that no parameter ships without help text.
"""

from __future__ import annotations

from typing import Any

# Keys whose meaning is the same in every step.
_DESCRIPTIONS: dict[str, str] = {
    "allow_external_services": (
        "Allow this step to call an external service. Off keeps the run local."
    ),
    "allowed_external_hosts": (
        "Extra hostnames allowed for external calls, beyond the loopback default."
    ),
    "anchor_point": "Point used as the zoom anchor.",
    "api_key_env": (
        "Environment variable that holds the API key. "
        "The key itself is never stored in the recipe."
    ),
    "apply_pads": "Apply speech handles inside the VAD instead of only in the timeline.",
    "approve_label": "Label of the approve button shown at the human gate.",
    "aspect_ratio": "Output aspect ratio for the Shorts.",
    "asset_dir": "Folder with local B-roll footage.",
    "audio_crossfade_ms": "Audio crossfade length at J/L-cut joins.",
    "audio_energy_boost": "Prefer windows with strong audio energy peaks.",
    "audio_filters": "FFmpeg audio filters applied to the rendered Short.",
    "base_url": "OpenAI-compatible base URL, for example http://127.0.0.1:11434/v1.",
    "batch_size": "Number of sentences translated per model request.",
    "broll_enabled": "Apply the approved B-roll plan while rendering this Short.",
    "brightness": "Brightness adjustment, where 1.0 is unchanged.",
    "burn_subtitles": "Burn the generated captions into the rendered video.",
    "caption_style": "Caption appearance: font, colours, timing, animation, and censorship.",
    "choose_best": "Pick the highest-scoring variant instead of keeping all of them.",
    "collect": "Collect the loop or map results into the output context.",
    "compute_type": "CTranslate2 compute type, such as int8 or float16.",
    "condition": "Expression evaluated to choose the branch.",
    "context_window": "Number of neighbouring sentences sent to the model per retake window.",
    "contrast": "Contrast adjustment, where 1.0 is unchanged.",
    "copy_thumbnail": "Copy the selected thumbnail into the delivery package.",
    "ctr_column": "CSV column that contains click-through rate.",
    "cut_mode": "Cut style at sentence joins: hard, J-cut, L-cut, or custom.",
    "denoise": "Apply FFT denoise to the audio master.",
    "denoise_db": "Denoise strength in decibels.",
    "device": "Execution device: CPU, CUDA, or auto.",
    "dialect": "FCPXML dialect written by the exporter.",
    "directory": "Folder used by this step.",
    "diversity_threshold": "Minimum title difference before two Shorts are considered distinct.",
    "duration_column": "CSV column that contains watch duration.",
    "duration_factors": "Multipliers used to create duration variants.",
    "duration_sec": "Duration of the B-roll cutaway in seconds.",
    "enable_j_cuts": "Start the audio before the video at each join.",
    "enable_l_cuts": "Keep the audio after the video at each join.",
    "enabled": "Enable or disable this behaviour.",
    "engine": "Analysis engine used by the step.",
    "export_format": "Which Short deliverables to write.",
    "extract_pcm": "Extract a 48 kHz PCM analysis track during ingest.",
    "fade_curve": "Fade curve applied to audio fades.",
    "fade_in_ms": "Audio fade-in length.",
    "fade_out_ms": "Audio fade-out length.",
    "fallback_to_heuristic": "Fall back to the heuristic method when the model is unavailable.",
    "filler_words": "Words removed from Short audio when filler removal is enabled.",
    "gamma": "Gamma adjustment, where 1.0 is unchanged.",
    "gate_id": "Identifier for this human approval gate.",
    "glob": "Glob pattern used to select input files.",
    "handle_check": "Warn when a cut lacks enough source handles.",
    "hashtags": "Hashtags included in the generated metadata.",
    "hf_token_env": "Environment variable that holds the Hugging Face token.",
    "highpass_hz": "High-pass cutoff for the audio master.",
    "hook_mode": "How the opening hook is chosen or moved.",
    "hooks": "Hook variants used by the A/B test.",
    "include_music": "Include the music bed in the delivery package.",
    "include_sfx": "Include sound effects in the delivery package.",
    "intro_duration_sec": "Duration of the intro card.",
    "intro_path": "Image used as the intro card.",
    "intro_title": "Title shown on the intro card.",
    "language": "Language spoken in the source media.",
    "llm_base_url": "OpenAI-compatible base URL used for translation or wording.",
    "llm_model": "Model used for translation or wording.",
    "loudnorm": "Apply EBU R128 loudness normalisation.",
    "lut_path": "Path to a .cube LUT applied to the timeline.",
    "manual_overrides": "Per-sentence keep/discard overrides applied after automatic culling.",
    "max_chapters": "Maximum number of chapters to plan.",
    "max_clips_to_generate": "Maximum number of Shorts to select.",
    "max_items": "Maximum number of items a loop or map may process.",
    "max_lower_thirds": "Maximum number of lower-third titles.",
    "max_per_short": "Maximum number of cues or assets assigned to each Short.",
    "max_speakers": "Maximum number of speakers to label.",
    "max_true_peak_db": "Maximum allowed true peak.",
    "max_variants": "Maximum number of variants to create.",
    "merge_gap_ms": "Gaps shorter than this are merged into one speech span.",
    "method": "Algorithm used for this analysis.",
    "min_clips": "Minimum number of Shorts required for the run to be useful.",
    "min_score": "Minimum match score accepted for an asset.",
    "min_silence_ms": "Silence shorter than this does not split a speech span.",
    "min_speech_ms": "Speech shorter than this is discarded.",
    "mix_second_audio": "Mix the second source's audio into the Short.",
    "mode": "Operating mode for this step.",
    "model": "Model name passed to the provider.",
    "model_path": "Local model path or Hugging Face model id.",
    "model_size": "Faster-Whisper model size.",
    "music_ducking": "Lower the music while speech is present.",
    "music_fade_in_ms": "Music fade-in length.",
    "music_fade_out_ms": "Music fade-out length.",
    "music_path": "Background music file.",
    "music_volume": "Music level relative to speech.",
    "noise_db": "Noise floor used by the speech detector.",
    "noise_floor_db": "Measured noise floor used by denoise.",
    "offset_ms": "Audio offset for J/L-cuts.",
    "on_error": "What to do when a loop or map item fails.",
    "original_volume": "Level of the original audio under the dub.",
    "outro_duration_sec": "Duration of the outro card.",
    "outro_path": "Image used as the outro card.",
    "outro_title": "Title shown on the outro card.",
    "over": "Collection or folder the loop iterates over.",
    "overlay_margin": "Margin between the overlay and the frame edge.",
    "overlay_opacity": "Overlay opacity from 0 to 1.",
    "overlay_path": "Image used as a watermark or overlay.",
    "overlay_position": "Corner or position of the overlay.",
    "overlay_width_ratio": "Overlay width as a fraction of the frame.",
    "pad_after_ms": "Speech handle added after each span.",
    "pad_before_ms": "Speech handle added before each span.",
    "pan_direction": "Pan direction used by the zoom animation.",
    "parallel": "Process loop or map items in parallel.",
    "path": "File used by this step.",
    "pause_ms": "Pause length that suggests a speaker change.",
    "platform": "Target platform for metadata or publishing.",
    "profile": "Selection or scoring profile.",
    "progressive_zoom": "Animate the zoom across the clip instead of holding one scale.",
    "project_id": "Project identifier carried into the timeline state.",
    "prompt": "Topic or instruction that focuses Short selection.",
    "prompt_mode": "Replace the previous selection or refine it.",
    "provider": "Provider used for this step.",
    "provider_id": "Configured provider selected for this node.",
    "punch_in_scale": "Scale used for punch-in zooms.",
    "query": "Optional search keywords.",
    "recipe_id": "Recipe used by the subflow or loop body.",
    "reframe_mode": "How the vertical frame follows the subject.",
    "reject_label": "Label of the reject button shown at the human gate.",
    "remove_fillers": "Remove filler words from the selected Shorts.",
    "reprompt": "Refinement instruction applied to a previous selection.",
    "resolution": "Short-edge resolution of the rendered Shorts.",
    "retention_column": "CSV column that contains retention.",
    "revision": "Timeline revision stored with the project state.",
    "sample_rate": "Audio sample rate in Hz.",
    "saturation": "Saturation adjustment, where 1.0 is unchanged.",
    "scene_change_boost": "Prefer windows around visual scene changes.",
    "score_field": "Metadata field used to rank items.",
    "second_source_path": "Second camera angle used by split-screen.",
    "selection_mode": "Choose Shorts automatically, with the model, or heuristically.",
    "source": "Media file or input source for this step.",
    "source_end_sec": "End of the source window considered for Shorts.",
    "source_language": "Language of the source transcript.",
    "source_start_sec": "Start of the source window considered for Shorts.",
    "speech_threshold": "Speech probability threshold.",
    "speed": "Speech speed multiplier.",
    "spike_suppression_ms": "Suppress short speech spikes below this length.",
    "split_screen": "Render two panes side by side.",
    "split_screen_focus_left": "Horizontal focus of the left pane, from 0 to 1.",
    "split_screen_focus_right": "Horizontal focus of the right pane, from 0 to 1.",
    "split_screen_on_dialogue": "Use split-screen when the clip contains multiple speakers.",
    "split_screen_zoom": "Zoom applied inside split-screen panes.",
    "srt_path": "Subtitle file used instead of speech-to-text.",
    "start_fraction": "Where the B-roll starts inside the Short.",
    "steps": "Inline recipe steps used by the subflow.",
    "strategy": "Retake strategy: keep the last or the best take.",
    "strictness": "How aggressively retakes are removed.",
    "subdir": "Subdirectory below the exports folder.",
    "subtitles_preset": "Caption preset used when burn-in is enabled.",
    "tags": "Tags used by asset search.",
    "target": "Publishing target or destination name.",
    "target_duration_max_sec": "Maximum Short duration.",
    "target_duration_min_sec": "Minimum Short duration.",
    "target_language": "Language produced by translation or dubbing.",
    "target_lufs": "Target integrated loudness.",
    "targets": "Export formats to write.",
    "tempo_bpm": "Tempo used for the beat grid.",
    "threshold": "Detection threshold.",
    "thumbnails": "Generate one thumbnail per detected shot.",
    "title": "Human-facing title.",
    "tolerance_lu": "Allowed loudness tolerance.",
    "tone": "Writing tone for generated metadata.",
    "top_k": "Number of top candidates to keep.",
    "transition_frames": "Length of the transition at each join.",
    "transition_type": "Transition style at each join.",
    "true_peak_db": "True peak target for the master.",
    "use_llm": "Let the model re-rank the candidates.",
    "vad_filter": "Run voice-activity filtering inside Whisper.",
    "variants": "Number of thumbnail variants to generate.",
    "voice": "Voice name used by the TTS provider.",
    "volume": "Output volume multiplier.",
    "when_false": "Steps executed when the condition is false.",
    "when_true": "Steps executed when the condition is true.",
    "whisper_binary": "Path to the whisper.cpp binary.",
    "whisper_model": "Path to the whisper.cpp model.",
    "zoom_max_scale": "Maximum zoom scale.",
    "zoom_min_scale": "Minimum zoom scale.",
    "zoom_mode": "Zoom style applied to the timeline.",
    "font_family": "Font family name.",
    "font_size": "Caption font size.",
    "font_weight": "Caption font weight.",
    "italic": "Render captions in italic.",
    "uppercase": "Render captions in uppercase.",
    "primary_color": "Primary caption colour.",
    "highlight_color": "Highlight colour.",
    "outline_color": "Caption outline colour.",
    "outline_width": "Caption outline width.",
    "shadow_color": "Caption shadow colour.",
    "shadow_offset": "Caption shadow offset.",
    "shadow_opacity": "Caption shadow opacity.",
    "background_color": "Caption background colour.",
    "background_opacity": "Caption background opacity.",
    "background_padding": "Caption background padding.",
    "alignment": "ASS alignment code.",
    "position_x": "Horizontal caption position from 0 to 1.",
    "position_y": "Vertical caption position from 0 to 1.",
    "max_width": "Maximum caption width as a fraction of the frame.",
    "animation": "Caption animation style.",
    "word_timing": "Use engine timings, sentence timings, or proportional timings.",
    "censor_enabled": "Censor configured words.",
    "censor_words": "Words replaced in captions.",
    "censor_replacement": "Text used for censored words.",
    "keyword_highlight_enabled": "Highlight keywords in captions.",
    "keyword_color": "Keyword highlight colour.",
    "keyword_words": "Keywords to highlight. Empty means automatic.",
    "emoji_enabled": "Add contextual emoji to captions.",
    "emoji_map": "Word-to-emoji mapping.",
    "brand_vocabulary": "Brand spelling replacements.",
    "speaker_colors": "Colours assigned to speakers.",
}

# Step-specific meaning for keys that are ambiguous on their own.
_STEP_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "ingest": {
        "source": "Source media file for this run.",
    },
    "audio.vad": {
        "engine": "VAD engine: auto, Silero, or FFmpeg.",
    },
    "edit.timeline": {
        "project_id": "Project identifier attached to the generated timeline.",
        "revision": "Timeline revision stored with the project state.",
        "noise_filter": (
            "Remove VAD intervals with no transcript words (coughs, breaths). "
            "The aggressive mode also removes ellipsis and subtitle watermarks."
        ),
        "noise_min_ms": "Do not remove non-speech intervals shorter than this.",
        "noise_confidence": (
            "Word-confidence threshold used by the aggressive noise filter."
        ),
        "use_transcript_spans": (
            "Build the cut from complete transcript sentences instead of VAD "
            "intervals. Recommended with the DeepSeek recipe."
        ),
        "max_internal_gap_ms": (
            "Remove pauses longer than this inside a sentence. Lower is tighter."
        ),
        "internal_gap_mode": (
            "smart removes breaths, coughs, and pauses but keeps long speech-like "
            "gaps; all removes every no-word gap; silence removes only quiet gaps."
        ),
        "gap_energy_threshold": (
            "RMS threshold used to decide whether a long gap may contain "
            "untranscribed speech."
        ),
        "long_gap_ms": "Gap length that can be kept as possible speech in smart mode.",
        "drop_isolated_words": (
            "Drop single-word tails inside a longer sentence. Common standalone "
            "answers are preserved."
        ),
        "max_silence_ms": (
            "Silence runs longer than this are capped. Defaults to the human "
            "reference maximum of about 500 ms."
        ),
        "keep_silence_ms": (
            "Natural pause retained when a long silence is capped."
        ),
        "silence_threshold_db": "RMS threshold used to classify silence.",
        "silence_frame_ms": "Frame size for audio silence detection.",
        "min_clip_ms": "Discard resulting pieces shorter than this.",
    },
    "retakes.cull": {
        "single_pass": (
            "Send the full transcript in one request instead of sentence windows. "
            "Better for semantic retakes and paraphrases."
        ),
        "max_group_span_seconds": (
            "Reject retake groups that span more than this many seconds."
        ),
        "max_discard_ratio": (
            "Fall back to deterministic near-duplicate groups when the LLM tries "
            "to discard more than this share of sentences."
        ),
    },
    "llm.timeline": {
        "provider_id": "Configured LLM provider that proposes timeline edits.",
        "prompt": (
            "Edit instruction for the LLM: what to tighten, crop, zoom, "
            "transition, or fade."
        ),
        "max_actions": "Maximum number of proposed edits applied from one response.",
        "allow_cuts": (
            "Allow this node to delete, trim, move, or ripple clips. Off keeps cuts "
            "deterministic; style and zoom are still allowed."
        ),
    },
    "llm.cleanup": {
        "provider_id": "Configured LLM provider that identifies clear out-of-context asides.",
        "prompt": (
            "Instruction for the conservative cleanup pass. Sponsor, pricing, "
            "links, CTAs, and unique content are protected by the step."
        ),
        "max_words": "Only sentences up to this length can be removed as asides.",
        "max_cuts": "Maximum number of sentences the cleanup pass may remove.",
    },
    "llm.zoom": {
        "provider_id": "Configured LLM provider that proposes zoom emphasis.",
        "prompt": "Instruction for choosing content-aware zooms from the clip text.",
        "max_actions": "Maximum number of zoom actions applied from one response.",
    },
    "llm.style": {
        "provider_id": "Configured LLM provider that proposes transitions and fades.",
        "prompt": "Instruction for choosing transitions, fades, scale, and position.",
        "max_actions": "Maximum number of style actions applied from one response.",
    },
    "transcribe": {
        "mode": "Transcription source: auto, SRT, project state, local model, HTTP, or none.",
    },
    "shorts.select": {
        "profile": "Selection profile that shapes duration and hook preferences.",
        "mode": "Selection mode.",
    },
    "shorts.score": {
        "profile": "Scoring profile.",
    },
    "shorts.reframe": {
        "mode": "Reframing mode: center crop, motion, or face tracking.",
    },
    "broll.plan": {
        "provider": "B-roll source: local assets or Pexels.",
        "duration_sec": "Length of each B-roll cutaway.",
    },
    "sfx.plan": {
        "directory": "Folder with local .wav/.mp3 sound effects.",
    },
    "nle.qa": {
        "directory": "Exports folder to validate.",
    },
    "music.beat": {
        "path": "Music file used for beat detection.",
    },
    "human.gate": {
        "title": "Heading shown at the approval gate.",
        "description": "Explanation shown at the approval gate.",
        "enabled": "Enable this gate.",
        "approve_label": "Label of the approve button shown at the human gate.",
        "reject_label": "Label of the reject button shown at the human gate.",
        "artifacts": "Output-relative files the human should review before approving.",
        "channels": "Notification channels: local, email, slack, signal.",
        "expires_hours": "Hours before the interaction is considered overdue.",
    },
    "human.input": {
        "gate_id": "Stable identifier for this interaction.",
        "title": "Heading shown in the human input panel.",
        "description": "What the human should answer and why.",
        "questions": "Typed questions: text, textarea, choice, boolean, number, file.",
        "channels": "Notification channels: local, email, slack, signal.",
        "expires_hours": "Hours before the interaction is considered overdue.",
        "save_as": "Optional output-relative path for the answers JSON.",
    },
    "human.files": {
        "gate_id": "Stable identifier for this file handoff.",
        "title": "Heading shown in the file request panel.",
        "description": "What files the human should provide and why.",
        "files": "Requested files with accept list, size limit, and optional target path.",
        "channels": "Notification channels: local, email, slack, signal.",
        "expires_hours": "Hours before the interaction is considered overdue.",
    },
    "research.multi_agent": {
        "topic": "Research directive; blank uses the recipe topic variable.",
        "scopes": "Optional scoped research questions; blank uses four default scopes.",
        "search_providers": (
            "Override the provider chain: local, crawl, searxng, wikipedia, "
            "internet_archive."
        ),
        "allow_external_services": "Allow external providers and page fetches for this step.",
        "allowed_external_hosts": "Optional host allowlist for external fetches.",
        "max_results": "Maximum search results per scope.",
        "fetch_pages": "Maximum pages to fetch per scope.",
        "max_cases": "Maximum cases kept per agent.",
    },
    "research.consolidate": {
        "provider_id": "Optional LLM provider id for deduplication.",
        "max_cases": "Maximum cases in the master dossier.",
        "require_sources": "Flag cases with no citation for human review.",
    },
    "presenter.profile": {
        "paths": "Transcript or script files used to derive the presenter voice.",
        "max_chars": "Maximum characters read from the samples.",
    },
    "script.dual_output": {
        "target_words": "Approximate narration length.",
        "max_sections": "Maximum number of script sections.",
        "presenter_profile": "Optional presenter profile text or profile path.",
        "max_cases_per_call": "Research cases sent to one model call.",
    },
    "metadata.pack": {
        "platform": "Platform whose metadata format is generated.",
    },
    "publish.queue": {
        "target": "Queue target name.",
        "platform": "Platform label stored with the publish item.",
    },
    "export.nle": {
        "targets": "NLE formats to write.",
        "filename_mode": (
            "source_timestamp names each export after the source video plus "
            "VideoFlow_Edited_<yymmddhhmmss>; fixed uses the base name."
        ),
        "basename": "Base name used when filename_mode is fixed.",
    },
    "export.video": {
        "filename_mode": (
            "source_timestamp names each render after the source video plus "
            "VideoFlow_Edited_<yymmddhhmmss>; fixed uses the filename."
        ),
        "filename": "Filename used when filename_mode is fixed.",
    },
    "flow.conditional": {
        "source": "Input source for the conditional branch.",
        "mode": "How the condition is evaluated.",
    },
    "flow.loop": {
        "source": "Input source for the loop.",
        "over": "Collection or folder the loop iterates over.",
        "mode": "How the loop collects items.",
    },
    "flow.map": {
        "source": "Input source for the map.",
        "over": "Collection or folder the map iterates over.",
    },
    "flow.reduce": {
        "source": "Input source for the reduce.",
        "over": "Collection or folder the reduce iterates over.",
    },
    "flow.subflow": {
        "source": "Input source for the subflow.",
    },
}

_UNITS: dict[str, str] = {
    "min_silence_ms": "ms",
    "min_speech_ms": "ms",
    "pad_before_ms": "ms",
    "pad_after_ms": "ms",
    "spike_suppression_ms": "ms",
    "merge_gap_ms": "ms",
    "offset_ms": "ms",
    "audio_crossfade_ms": "ms",
    "fade_in_ms": "ms",
    "fade_out_ms": "ms",
    "pause_ms": "ms",
    "music_fade_in_ms": "ms",
    "music_fade_out_ms": "ms",
    "noise_db": "dB",
    "denoise_db": "dB",
    "noise_floor_db": "dB",
    "true_peak_db": "dB",
    "max_true_peak_db": "dB",
    "highpass_hz": "Hz",
    "target_lufs": "LUFS",
    "tolerance_lu": "LU",
    "duration_sec": "s",
    "source_start_sec": "s",
    "source_end_sec": "s",
    "intro_duration_sec": "s",
    "outro_duration_sec": "s",
    "target_duration_min_sec": "s",
    "target_duration_max_sec": "s",
    "tempo_bpm": "BPM",
    "transition_frames": "frames",
    "context_window": "turns",
    "sample_rate": "Hz",
    "batch_size": "sentences",
    "max_speakers": "speakers",
    "max_chapters": "chapters",
    "max_lower_thirds": "titles",
    "max_per_short": "cues",
    "max_items": "items",
    "max_variants": "variants",
    "top_k": "items",
    "min_clips": "clips",
    "max_clips_to_generate": "clips",
    "variants": "variants",
    "overlay_margin": "px",
    "overlay_width_ratio": "fraction",
}

_PLACEHOLDERS: dict[str, str] = {
    "source": "/media/source.mp4",
    "srt_path": "/path/to/subtitles.srt",
    "asset_dir": "/path/to/broll",
    "directory": "/path/to/folder",
    "csv_path": "/path/to/metrics.csv",
    "lut_path": "/path/to/look.cube",
    "music_path": "/path/to/music.wav",
    "path": "/path/to/file",
    "overlay_path": "/path/to/watermark.png",
    "second_source_path": "/path/to/second-angle.mp4",
    "intro_path": "/path/to/intro.png",
    "outro_path": "/path/to/outro.png",
    "whisper_binary": "/usr/bin/whisper-cli",
    "whisper_model": "/path/to/ggml-model.bin",
    "model_path": "/path/to/model",
}

_CONTROL_OVERRIDES: dict[tuple[str, str], str] = {
    ("edit.timeline", "transition_frames"): "number",
    ("edit.timeline", "transition_type"): "select",
}

_PROVIDER_KEYS = {
    "provider",
    "provider_id",
    "base_url",
    "model",
    "voice",
    "api_key_env",
    "llm_base_url",
    "llm_model",
    "allow_external_services",
    "allowed_external_hosts",
    "hf_token_env",
}
_AUDIO_KEYS = {
    "engine",
    "noise_db",
    "min_silence_ms",
    "min_speech_ms",
    "speech_threshold",
    "pad_before_ms",
    "pad_after_ms",
    "spike_suppression_ms",
    "merge_gap_ms",
    "apply_pads",
    "highpass_hz",
    "denoise",
    "denoise_db",
    "noise_floor_db",
    "loudnorm",
    "target_lufs",
    "true_peak_db",
    "max_true_peak_db",
    "tolerance_lu",
    "sample_rate",
    "volume",
    "original_volume",
    "speed",
    "audio_filters",
    "audio_crossfade_ms",
    "fade_in_ms",
    "fade_out_ms",
    "fade_curve",
    "music_path",
    "music_volume",
    "music_ducking",
    "music_fade_in_ms",
    "music_fade_out_ms",
}
_TIMELINE_KEYS = {
    "cut_mode",
    "enable_j_cuts",
    "enable_l_cuts",
    "offset_ms",
    "handle_check",
    "zoom_mode",
    "zoom_min_scale",
    "zoom_max_scale",
    "punch_in_scale",
    "anchor_point",
    "progressive_zoom",
    "pan_direction",
    "transition_frames",
    "transition_type",
    "revision",
}
_SHORTS_KEYS = {
    "profile",
    "target_duration_min_sec",
    "target_duration_max_sec",
    "min_clips",
    "max_clips_to_generate",
    "selection_mode",
    "prompt",
    "reprompt",
    "prompt_mode",
    "hook_mode",
    "audio_energy_boost",
    "scene_change_boost",
    "remove_fillers",
    "filler_words",
    "reframe_mode",
    "aspect_ratio",
    "resolution",
    "source_start_sec",
    "source_end_sec",
    "split_screen",
    "split_screen_zoom",
    "split_screen_focus_left",
    "split_screen_focus_right",
    "split_screen_on_dialogue",
    "mix_second_audio",
    "broll_enabled",
    "second_source_path",
    "hooks",
    "duration_factors",
    "max_variants",
    "diversity_threshold",
    "use_llm",
    "top_k",
}
_METADATA_KEYS = {
    "title",
    "description",
    "platform",
    "tone",
    "hashtags",
    "tags",
    "intro_title",
    "outro_title",
    "gate_id",
    "approve_label",
    "reject_label",
    "max_chapters",
}
_FILES_KEYS = {
    "source",
    "directory",
    "csv_path",
    "asset_dir",
    "srt_path",
    "lut_path",
    "music_path",
    "path",
    "overlay_path",
    "second_source_path",
    "intro_path",
    "outro_path",
    "whisper_binary",
    "whisper_model",
    "model_path",
}

_ACRONYMS = {
    "db": "dB",
    "hz": "Hz",
    "ms": "ms",
    "lufs": "LUFS",
    "lu": "LU",
    "bpm": "BPM",
    "ctr": "CTR",
    "api": "API",
    "llm": "LLM",
    "sfx": "SFX",
    "vad": "VAD",
    "id": "ID",
    "url": "URL",
    "hf": "HF",
    "csv": "CSV",
    "lut": "LUT",
}


def pretty_label(key: str) -> str:
    parts = [part for part in key.split("_") if part]
    words: list[str] = []
    for part in parts:
        if part in _ACRONYMS:
            words.append(_ACRONYMS[part])
        elif part.isdigit():
            words.append(part)
        else:
            words.append(part.capitalize())
    return " ".join(words) or key


def _group_for(step_type: str, key: str) -> str:
    if key in _PROVIDER_KEYS:
        return "Provider"
    if key in _FILES_KEYS or key.endswith(("_path", "_dir")):
        return "Files"
    if key in _AUDIO_KEYS:
        return "Audio"
    if key in _TIMELINE_KEYS or step_type == "edit.timeline":
        return "Timeline"
    if key in _SHORTS_KEYS or step_type.startswith("shorts."):
        return "Shorts"
    if key in _METADATA_KEYS:
        return "Metadata"
    if key.startswith(("max_", "min_", "target_")) or key.endswith(("_count", "_size")):
        return "Limits"
    return "Parameters"


def field_metadata(
    step_type: str,
    step_title: str,
    key: str,
    spec: dict[str, Any],
) -> dict[str, str]:
    description = (
        _STEP_DESCRIPTIONS.get(step_type, {}).get(key)
        or _DESCRIPTIONS.get(key)
        or f"{pretty_label(key)} for the {step_title} step."
    )
    group = _group_for(step_type, key)
    held = {
        "label": pretty_label(key),
        "description": description,
        "unit": _UNITS.get(key, ""),
        "group": group,
        "placeholder": _PLACEHOLDERS.get(key, ""),
        "control": _CONTROL_OVERRIDES.get((step_type, key), ""),
    }
    return held


def _apply(spec: dict[str, Any], meta: dict[str, str]) -> None:
    if not isinstance(spec, dict):
        return
    spec["title"] = meta["label"]
    spec["description"] = meta["description"]
    spec["x-unit"] = meta["unit"]
    spec["x-group"] = meta["group"]
    if meta["placeholder"]:
        spec["x-placeholder"] = meta["placeholder"]
    if meta["control"]:
        spec["x-control"] = meta["control"]


def apply_field_metadata(
    step_type: str,
    step_title: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Attach labels, help, units, groups, and placeholders to a JSON schema."""

    for key, spec in (schema.get("properties") or {}).items():
        _apply(spec, field_metadata(step_type, step_title, key, spec))
    for definition in (schema.get("$defs") or {}).values():
        if not isinstance(definition, dict):
            continue
        for key, spec in (definition.get("properties") or {}).items():
            _apply(spec, field_metadata(step_type, step_title, key, spec))
    return schema
