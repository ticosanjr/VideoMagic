"""Advanced and variant built-in recipes."""

from __future__ import annotations

from videoflow.engine.recipes import definitions_base as _base  # noqa: F401
from videoflow.engine.recipes.catalog import (
    _EXPORT,
    _INGEST,
    _RETAKES,
    _TIMELINE,
    _TRANSCRIBE,
    _VAD,
    BUILTIN_RECIPES,
    _add_recipe,
    _localized_steps,
    _recut_steps,
)

BUILTIN_RECIPES["localized_shorts"] = {
    "schema_version": 1,
    "id": "localized_shorts",
    "name": "Localized Shorts",
    "description": (
        "Viral Shorts plus an optional translated dub per Short when a TTS provider is configured."
    ),
    "llm": {"provider": "none"},
    "steps": _localized_steps(),
}

_add_recipe(
    "recut_replacement",
    "Recut Replacement",
    _recut_steps(with_retakes=False),
    description=(
        "Remove silence with detailed VAD controls, choose a hard/J/L cut, and "
        "export Resolve, Premiere, and Kdenlive timelines. Render the MP4 from "
        "the Edit tab when the cut is final."
    ),
)
_add_recipe(
    "recut_replacement_retakes",
    "Recut Replacement + retakes",
    _recut_steps(with_retakes=True),
    description=(
        "The Recut Replacement flow plus transcription and retake culling before "
        "the timeline, with the same detailed silence and cut controls."
    ),
)

_add_recipe(
    "deepseek_full_edit",
    "DeepSeek full edit",
    [
        _INGEST,
        _VAD,
        {
            **_TRANSCRIBE,
            "params": {
                "mode": "auto",
                "language": "pt",
                "model_size": "large-v3",
                "model_id": "faster-whisper-large-v3",
            },
        },
        {
            **_RETAKES,
            "params": {
                # The deterministic take engine is the primary decision maker.
                # The LLM stays available per recipe as a semantic tie-breaker.
                "provider_id": "",
                "enabled": True,
                "strategy": "keep_last",
                "strictness": "balanced",
                "single_pass": True,
                "context_window": 25,
                "max_group_span_seconds": 180,
                "max_discard_ratio": 0.45,
                "semantic_duplicates": False,
            },
        },
        {
            "id": "llm_cleanup",
            "type": "llm.cleanup",
            "needs": ["retakes"],
            "inputs": {
                "transcript": "retakes.transcript",
                "discarded": "retakes.discarded",
            },
            "params": {
                "provider_id": "deepseek",
                "max_words": 10,
                "max_cuts": 12,
                "prompt": (
                    "Remove only clear out-of-context interruptions such as a "
                    "remark about the room or recording. Preserve sponsor "
                    "segments, prices, links, CTAs, examples, and any sentence "
                    "that introduces new information."
                ),
            },
        },
        {
            **_TIMELINE,
            "needs": ["vad", "retakes", "llm_cleanup"],
            "params": {
                "cut_mode": "hard",
                "replace_manual": True,
                "zoom_mode": "manual_rules",
                "audio_crossfade_ms": 10,
                "fade_in_ms": 10,
                "fade_out_ms": 10,
                "use_transcript_spans": True,
                "noise_filter": "non_speech",
                "noise_min_ms": 180,
                "pad_before_ms": 60,
                "pad_after_ms": 120,
                "head_guard_ms": 80,
                "tail_guard_ms": 160,
                "guard_energy_threshold": 1500,
                "max_internal_gap_ms": 150,
                "internal_gap_mode": "smart",
                "gap_energy_threshold": 800,
                "long_gap_ms": 800,
                "drop_isolated_words": False,
                "detect_repeats": True,
                "remove_fillers": False,
                "repeat_min_words": 5,
                "repeat_max_gap_seconds": 120.0,
                "repeat_pad_ms": 40,
                "repeat_max_cuts": 60,
                "word_cut_max_ratio": 0.2,
                "keep_untranscribed": False,
                "untranscribed_min_ms": 500,
                "untranscribed_energy_threshold": 1500,
                "remove_impulsive_noise": True,
                "impulsive_noise_min_ms": 40,
                "impulsive_noise_max_ms": 600,
                "impulsive_noise_margin_ms": 80,
                "use_audio_event_model": False,
                "use_ast_audio_tagger": False,
                "ast_noise_threshold": 0.1,
                "max_silence_ms": 500,
                "keep_silence_ms": 300,
                "silence_threshold_db": -35.0,
                "silence_frame_ms": 10,
                "silence_word_margin_ms": 20,
                "repair_word_tails": False,
                "word_repair_max_ms": 800,
                "word_integrity_max_ms": 1500,
                "word_integrity_gap_ms": 500,
                "min_clip_ms": 200,
            },
        },
        {
            "id": "llm_zoom",
            "type": "llm.zoom",
            "enabled": False,
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "provider_id": "deepseek",
                "max_actions": 24,
                "prompt": (
                    "This is a talking-head video. Read each clip's text and choose "
                    "at most one subtle zoom per major beat. Use punch_in or a smooth "
                    "envelope for numbers, comparisons, reveals, and key claims. "
                    "Never zoom non-speech or ellipsis clips, and do not alternate "
                    "zoom in/out at every hard cut."
                ),
            },
        },
        {
            "id": "llm_style",
            "type": "llm.style",
            "enabled": False,
            "needs": ["llm_zoom"],
            "inputs": {"timeline": "llm_zoom.timeline"},
            "params": {
                "provider_id": "deepseek",
                "max_actions": 16,
                "prompt": (
                    "Add only the transitions and fades that help the story. Keep "
                    "hard cuts as the default. Use a gentle fade at the start and "
                    "end, and avoid drawing attention to non-speech clips."
                ),
            },
        },
        {
            **_EXPORT,
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
        },
        {
            "id": "video_export",
            "type": "export.video",
            "needs": ["timeline"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "preset": "ultrafast",
                "subdir": "exports",
                "filename_mode": "source_timestamp",
                "filename": "video.mp4",
            },
        },
    ],
    description=(
        "Transcribe, group retakes with DeepSeek, remove clear out-of-context "
        "asides, cap silence to a tight reference profile, and export NLE and "
        "MP4. Zoom and style nodes remain available but disabled."
    ),
)


_add_recipe(
    "autonomous_studio_master",
    "Autonomous studio master",
    [
        _INGEST,
        _VAD,
        {
            **_TRANSCRIBE,
            "params": {
                "mode": "auto",
                "language": "pt",
                "model_size": "large-v3",
                "model_id": "faster-whisper-large-v3",
            },
        },
        {
            "id": "drift",
            "type": "edit.drift",
            "needs": ["transcribe"],
            "params": {"offset_ms": "$drift_offset_ms", "min_ms": 0.0, "max_ms": 500.0},
        },
        {
            **_RETAKES,
            "needs": ["vad", "drift"],
            "params": {
                "provider_id": "",
                "enabled": True,
                "strategy": "keep_last",
                "strictness": "balanced",
                "single_pass": True,
                "context_window": 25,
                "max_group_span_seconds": 180,
                "max_discard_ratio": 0.45,
                "semantic_duplicates": False,
            },
        },
        {
            "id": "llm_cleanup",
            "type": "llm.cleanup",
            "needs": ["retakes"],
            "inputs": {
                "transcript": "retakes.transcript",
                "discarded": "retakes.discarded",
            },
            "params": {"provider_id": "", "max_words": 10, "max_cuts": 12},
        },
        {
            "id": "beats",
            "type": "narrative.beats",
            "needs": ["retakes", "llm_cleanup"],
            "params": {
                "provider_id": "",
                "min_block_words": 100,
                "max_block_words": 300,
                "beats": [
                    "hook",
                    "context",
                    "conflict",
                    "turning_point",
                    "proof",
                    "payoff",
                ],
            },
        },
        {
            "id": "assets_index",
            "type": "assets.index",
            "needs": ["ingest"],
            "params": {"asset_dir": "$asset_dir", "tags": []},
        },
        {
            "id": "shots",
            "type": "assets.shots",
            "needs": ["ingest"],
            "params": {"threshold": 0.35, "thumbnails": True},
        },
        {
            **_TIMELINE,
            "needs": ["vad", "retakes", "llm_cleanup"],
            "params": {
                "cut_mode": "hard",
                "replace_manual": True,
                "zoom_mode": "manual_rules",
                "audio_crossfade_ms": 10,
                "fade_in_ms": 10,
                "fade_out_ms": 10,
                "use_transcript_spans": True,
                "noise_filter": "non_speech",
                "noise_min_ms": 180,
                "pad_before_ms": 60,
                "pad_after_ms": 120,
                "head_guard_ms": 80,
                "tail_guard_ms": 160,
                "guard_energy_threshold": 1500,
                "max_internal_gap_ms": 150,
                "internal_gap_mode": "smart",
                "gap_energy_threshold": 800,
                "long_gap_ms": 800,
                "drop_isolated_words": False,
                "detect_repeats": True,
                "remove_fillers": False,
                "repeat_min_words": 5,
                "repeat_max_gap_seconds": 120.0,
                "repeat_pad_ms": 40,
                "repeat_max_cuts": 60,
                "word_cut_max_ratio": 0.2,
                "keep_untranscribed": False,
                "untranscribed_min_ms": 500,
                "untranscribed_energy_threshold": 1500,
                "remove_impulsive_noise": True,
                "impulsive_noise_min_ms": 40,
                "impulsive_noise_max_ms": 600,
                "impulsive_noise_margin_ms": 80,
                "use_audio_event_model": False,
                "use_ast_audio_tagger": False,
                "ast_noise_threshold": 0.1,
                "max_silence_ms": 500,
                "keep_silence_ms": 300,
                "silence_threshold_db": -35.0,
                "silence_frame_ms": 10,
                "silence_word_margin_ms": 20,
                "repair_word_tails": False,
                "word_repair_max_ms": 800,
                "word_integrity_max_ms": 1500,
                "word_integrity_gap_ms": 500,
                "min_clip_ms": 200,
            },
        },
        {
            "id": "broll_master",
            "type": "broll.plan_master",
            "needs": ["timeline", "beats", "assets_index"],
            "params": {
                "asset_dir": "$asset_dir",
                "max_per_block": 2,
                "min_score": 0.05,
                "duration_sec": 3.0,
            },
        },
        {
            "id": "titles",
            "type": "titles.plan",
            "needs": ["timeline"],
            "params": {"max_lower_thirds": 40},
        },
        {
            "id": "audio_master",
            "type": "audio.master",
            "needs": ["ingest"],
            "params": {
                "target_lufs": "$target_loudness_lufs",
                "true_peak_db": "$true_peak_db",
                "highpass_hz": 80,
                "denoise": True,
                "loudnorm": True,
            },
        },
        {
            "id": "audio_duck",
            "type": "audio.duck",
            "needs": ["audio_master"],
            "params": {
                "music_path": "$music_path",
                "duck_db": -12.0,
                "threshold": 0.015,
                "ratio": 8.0,
                "attack_ms": 20,
                "release_ms": 300,
                "music_gain": 0.4,
            },
        },
        {
            "id": "color",
            "type": "color.grade",
            "params": {"saturation": 1.0, "contrast": 1.0, "gamma": 1.0},
        },
        {
            "id": "motion",
            "type": "motion.render",
            "needs": ["timeline", "beats"],
            "params": {
                "engine": "hyperframes",
                "fps": 30,
                "width": 1920,
                "height": 1080,
                "draft_scale": 0.5,
                "motion_blur": False,
            },
        },
        {
            "id": "export_nle",
            "type": "export.nle",
            "needs": ["timeline", "titles", "broll_master", "color", "audio_duck"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "targets": ["resolve", "premiere", "kdenlive"],
                "filename_mode": "source_timestamp",
            },
        },
        {
            "id": "export_video",
            "type": "export.video",
            "needs": ["timeline", "titles", "color"],
            "inputs": {"timeline": "timeline.timeline"},
            "params": {
                "preset": "ultrafast",
                "subdir": "exports",
                "filename_mode": "source_timestamp",
                "filename": "video.mp4",
            },
        },
        {
            "id": "nle_qa",
            "type": "nle.qa",
            "needs": ["export_nle"],
            "params": {},
        },
        {
            "id": "audio_qa",
            "type": "audio.qa",
            "needs": ["audio_duck"],
            "params": {
                "target_lufs": "$target_loudness_lufs",
                "tolerance_lu": 0.5,
                "max_true_peak_db": "$true_peak_db",
            },
        },
        {
            "id": "vision_qa",
            "type": "qa.vision",
            "needs": ["export_video"],
            "params": {
                "sample_fps": 10.0,
                "max_flash_frames": 3,
                "max_text_latency_ms": 100,
                "max_lip_sync_frames": 2,
                "face_obscuration": True,
            },
        },
        {
            "id": "human_gate",
            "type": "human.gate",
            "enabled": False,
            "needs": ["vision_qa"],
            "params": {
                "gate_id": "master_review",
                "title": "Master review",
                "description": "Approve the master edit before delivery.",
            },
        },
        {
            "id": "rules",
            "type": "rules.memory",
            "needs": ["export_video", "audio_qa"],
            "params": {
                "paths": ["agents.md", "claude.md"],
                "rules": [
                    "style_schema = $style_schema",
                    "target_aspect_ratio = $target_aspect_ratio",
                    "target_loudness_lufs = $target_loudness_lufs",
                ],
                "dedupe": True,
            },
        },
    ],
    description=(
        "Autonomous master edit: drift-corrected transcription, deterministic "
        "de-talking, narrative beats and entities, local B-roll planning, audio "
        "mastering and ducking, XML/MP4 export, and QA. Motion graphics and "
        "vision QA are phase-2 shells; external APIs are off by default."
    ),
    variables={
        "target_aspect_ratio": {
            "type": "enum",
            "default": "16:9",
            "options": ["16:9", "9:16", "1:1"],
        },
        "style_schema": {
            "type": "enum",
            "default": "Minimal_Tech",
            "options": [
                "Apple_Liquid_Glass",
                "Dark_Dossier",
                "3D_Paper_Collage",
                "Minimal_Tech",
            ],
        },
        "drift_offset_ms": {"type": "number", "default": 0.0},
        "target_loudness_lufs": {"type": "number", "default": -16.5},
        "true_peak_db": {"type": "number", "default": -1.5},
        "asset_dir": {"type": "string", "default": ""},
        "music_path": {"type": "string", "default": ""},
        "preview_mode": {"type": "boolean", "default": True},
    },
)
