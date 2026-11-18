"""Headless recipes designed for OpenCode and the vf_* MCP tools."""

from __future__ import annotations

from videoflow.engine.recipes.catalog import _add_recipe

_add_recipe(
    "opencode_longform_studio",
    "OpenCode long-form studio",
    [
        {
            "id": "ingest",
            "type": "ingest",
            "needs": [],
            "params": {
                "extract_pcm": True,
                "force_cfr": True,
                "generate_proxy": True,
            },
        },
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "params": {"engine": "auto", "min_silence_ms": 350},
        },
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest", "vad"],
            "params": {"mode": "auto", "language": "auto", "offset_mode": "auto"},
        },
        {
            "id": "gaze",
            "type": "vision.gaze",
            "needs": ["ingest"],
            "params": {"backend": "auto", "sample_fps": 1.0},
        },
        {
            "id": "retakes",
            "type": "retakes.cull",
            "needs": ["vad", "transcribe"],
            "params": {"enabled": True, "strategy": "keep_last"},
        },
        {
            "id": "board",
            "type": "assets.reference_board",
            "needs": ["transcribe"],
            "params": {},
        },
        {
            "id": "archetype_gate",
            "type": "human.gate",
            "needs": ["board"],
            "params": {
                "gate_id": "archetypes",
                "title": "Approve archetype previews",
                "description": "Review the 1-minute archetype samples before the batch.",
            },
        },
        {
            "id": "motion",
            "type": "motion.web_render",
            "needs": ["archetype_gate"],
            "params": {"engine": "auto", "duration_sec": 8, "draft_scale": 0.5},
        },
        {
            "id": "capture",
            "type": "assets.screen_capture",
            "needs": ["archetype_gate"],
            "params": {"capture": "screenshot"},
        },
        {
            "id": "timeline",
            "type": "edit.timeline",
            "needs": ["vad", "transcribe", "retakes"],
            "params": {},
        },
        {
            "id": "qa",
            "type": "qa.visual_10fps",
            "needs": ["timeline"],
            "params": {"fps": 10, "window_pad_sec": 0.5},
        },
        {
            "id": "intro",
            "type": "intro.assemble_last",
            "needs": ["qa"],
            "params": {"max_sec": 120},
        },
        {
            "id": "audio_master",
            "type": "audio.master",
            "needs": ["ingest"],
            "params": {"loudnorm": True, "target_lufs": -16.5, "true_peak_db": -1.5},
        },
        {
            "id": "export_nle",
            "type": "export.nle",
            "needs": ["timeline"],
            "params": {"targets": ["resolve", "premiere", "kdenlive"]},
        },
        {
            "id": "export_master",
            "type": "export.video",
            "needs": ["timeline", "audio_master"],
            "params": {"preset": "ultrafast"},
        },
        {
            "id": "final_qa",
            "type": "qa.final",
            "needs": ["export_master"],
            "params": {"strict": True},
        },
    ],
    description=(
        "CFR ingest, gaze/retakes, reference board, archetype gate, motion, "
        "10 FPS QA, intro, and final export."
    ),
    llm={"provider": "auto"},
)

_add_recipe(
    "opencode_reels_from_raw",
    "OpenCode Reels from raw",
    [
        {
            "id": "ingest",
            "type": "ingest",
            "needs": [],
            "params": {"force_cfr": True, "generate_proxy": True},
        },
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "params": {"engine": "auto", "min_silence_ms": 350},
        },
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest", "vad"],
            "params": {"mode": "auto", "language": "auto"},
        },
        {
            "id": "retakes",
            "type": "retakes.cull",
            "needs": ["vad", "transcribe"],
            "params": {"enabled": True, "strategy": "keep_last"},
        },
        {
            "id": "pacing",
            "type": "pacing.visual_audit",
            "needs": ["transcribe"],
            "params": {"short_static_sec": 5, "inject": "zoom"},
        },
        {
            "id": "layout",
            "type": "layout.cutout",
            "needs": ["pacing"],
            "params": {"style": "auto"},
        },
        {
            "id": "motion",
            "type": "motion.web_render",
            "needs": ["layout"],
            "params": {"engine": "auto", "duration_sec": 6, "draft_scale": 0.5},
        },
        {
            "id": "timeline",
            "type": "edit.timeline",
            "needs": ["vad", "transcribe", "retakes"],
            "params": {},
        },
        {
            "id": "qa_safezone",
            "type": "qa.safezone",
            "needs": ["timeline"],
            "params": {"platforms": ["reels", "tiktok", "shorts"]},
        },
        {
            "id": "qa_visual",
            "type": "qa.visual_10fps",
            "needs": ["timeline"],
            "params": {"fps": 10},
        },
        {
            "id": "audio_master",
            "type": "audio.master",
            "needs": ["ingest"],
            "params": {"loudnorm": True, "target_lufs": -16.5},
        },
        {
            "id": "export",
            "type": "export.video",
            "needs": ["timeline", "audio_master"],
            "params": {"preset": "ultrafast", "aspect_ratio": "9:16"},
        },
    ],
    description=(
        "Raw footage to a vertical Reel with CFR, pacing, cutout layout, "
        "safe-zone QA, and 10 FPS visual QA."
    ),
    llm={"provider": "auto"},
)

_add_recipe(
    "opencode_shorts_batch_from_long",
    "OpenCode Shorts batch",
    [
        {
            "id": "ingest",
            "type": "ingest",
            "needs": [],
            "params": {"force_cfr": True},
        },
        {
            "id": "timeline",
            "type": "timeline.load",
            "needs": ["ingest"],
            "params": {},
        },
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest", "timeline"],
            "params": {"mode": "auto", "language": "auto"},
        },
        {
            "id": "shorts",
            "type": "shorts.select",
            "needs": ["transcribe"],
            "params": {
                "selection_mode": "auto",
                "hook_mode": "reorder",
                "target_duration_min_sec": 30,
                "target_duration_max_sec": 60,
            },
        },
        {
            "id": "score",
            "type": "shorts.score",
            "needs": ["shorts"],
            "params": {"score_mode": "hybrid", "top_k": 5},
        },
        {
            "id": "reframe",
            "type": "shorts.reframe",
            "needs": ["score"],
            "params": {"mode": "face_tracking", "layout": "single"},
        },
        {
            "id": "layout",
            "type": "layout.cutout",
            "needs": ["reframe"],
            "params": {"style": "auto"},
        },
        {
            "id": "captions",
            "type": "shorts.captions",
            "needs": ["shorts"],
            "params": {"enabled": True, "preset": "tiktok_bold"},
        },
        {
            "id": "qa_safezone",
            "type": "qa.safezone",
            "needs": ["captions"],
            "params": {"platforms": ["reels", "tiktok", "shorts"]},
        },
        {
            "id": "qa_visual",
            "type": "qa.visual_10fps",
            "needs": ["captions"],
            "params": {"fps": 10},
        },
        {
            "id": "render",
            "type": "shorts.render",
            "needs": ["layout", "captions"],
            "params": {},
        },
    ],
    description=(
        "Load an edited timeline, select open-loop Shorts, captions, "
        "safe-zone QA, and batch render."
    ),
    llm={"provider": "auto"},
)

_add_recipe(
    "opencode_clone_style",
    "OpenCode clone style",
    [
        {
            "id": "reverse",
            "type": "style.reverse_engineer",
            "needs": [],
            "params": {"mode": "both"},
        },
        {
            "id": "rules",
            "type": "preset.compile_rule",
            "needs": ["reverse"],
            "params": {"channel_id": "default", "mode": "merge"},
        },
    ],
    description="Reverse-engineer a reference into a Light/Dark preset and durable channel rules.",
    llm={"provider": "auto"},
)
