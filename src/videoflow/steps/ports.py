"""Typed ports exposed by recipe steps, plus wiring validation helpers."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from videoflow.core.recipe import depends_on
from videoflow.domain.errors import RecipeError, VideoFlowError
from videoflow.steps.base import PortSpec

_ARTIFACTS = "artifacts"

PORTS: dict[str, tuple[tuple[PortSpec, ...], tuple[PortSpec, ...]]] = {
    "ingest": (
        (),
        (
            PortSpec("media", "Media info", "media", "media"),
            PortSpec("pcm", "PCM audio", "pcm", "pcm_path"),
            PortSpec("digest", "PCM digest", "string", "pcm_digest"),
        ),
    ),
    "audio.vad": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals"),
            PortSpec("silence", "Silence spans", "inactive_spans", "silence_spans"),
            PortSpec("engine", "VAD engine", "string", "vad_engine"),
        ),
    ),
    "transcribe": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (
            PortSpec("transcript", "Transcript", "transcript", "transcript"),
            PortSpec("source", "Transcript source", "string", "transcript_source"),
        ),
    ),
    "flow.junction": (
        tuple(
            PortSpec(
                f"in{index}",
                f"Input {index}",
                "any",
                f"metadata:junction_in{index}",
            )
            for index in range(1, 9)
        ),
        (PortSpec("out", "Output", "any", "metadata:junction_out"),),
    ),
    "llm.cleanup": (
        (
            PortSpec("transcript", "Transcript", "transcript", "transcript", True),
            PortSpec(
                "discarded",
                "Discarded sentence ids",
                "integer_list",
                "discard_sentence_ids",
                False,
            ),
        ),
        (
            PortSpec(
                "discarded",
                "Kept/discarded sentence ids",
                "integer_list",
                "discard_sentence_ids",
            ),
            PortSpec("report", "Cleanup report", "json", "metadata:cleanup_report"),
        ),
    ),
    "llm.timeline": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec(
                "report",
                "Action report",
                "json",
                "metadata:llm_timeline_report",
            ),
        ),
    ),
    "llm.zoom": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec("report", "Zoom report", "json", "metadata:llm_zoom_report"),
        ),
    ),
    "llm.style": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec("report", "Style report", "json", "metadata:llm_style_report"),
        ),
    ),
    "retakes.cull": (
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals", True),
            PortSpec("transcript", "Transcript", "transcript", "transcript", True),
        ),
        (
            PortSpec("speech", "Kept speech", "sample_spans", "speech_intervals"),
            PortSpec("retakes", "Retake spans", "inactive_spans", "retake_spans"),
            PortSpec(
                "overlap_cuts",
                "Overlap cuts",
                "sample_spans",
                "retake_overlap_cuts",
            ),
            PortSpec("discarded", "Discarded sentence ids", "integer_list", "discard_sentence_ids"),
            PortSpec("transcript", "Normalized transcript", "transcript", "transcript"),
            PortSpec(
                "normalized",
                "Transcript normalized",
                "boolean",
                "metadata:transcript_normalized",
            ),
            PortSpec("report", "Retake report", "json", "metadata:retakes_report"),
        ),
    ),
    "edit.timeline": (
        (
            PortSpec("speech", "Speech spans", "sample_spans", "speech_intervals", True),
            PortSpec("transcript", "Transcript", "transcript", "transcript", False),
            PortSpec("silence", "Silence spans", "inactive_spans", "silence_spans", False),
            PortSpec("retakes", "Retake spans", "inactive_spans", "retake_spans", False),
        ),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec("warnings", "Warnings", "string_list", "warnings"),
        ),
    ),
    "export.nle": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "NLE artifacts", "artifact_map", "artifacts"),),
    ),
    "export.video": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Video artifacts", "artifact_map", "artifacts"),),
    ),
    "session.ingest": (
        (),
        (
            PortSpec("timeline", "Session timeline", "timeline", "state"),
            PortSpec("media", "Primary media", "media", "media"),
            PortSpec(
                "manifest",
                "Session manifest",
                "json",
                "metadata:session_manifest",
            ),
            PortSpec(
                "audio",
                "Session audio",
                "path",
                "metadata:session_audio",
            ),
        ),
    ),
    "session.cull": (
        (
            PortSpec("timeline", "Timeline state", "timeline", "state", True),
            PortSpec("transcript", "Transcript", "transcript", "transcript", False),
        ),
        (
            PortSpec("timeline", "Culled timeline", "timeline", "state"),
            PortSpec(
                "report",
                "Cull report",
                "json",
                "metadata:session_cull_report",
            ),
        ),
    ),
    "multicam.plan": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Planned timeline", "timeline", "state"),
            PortSpec("plan", "Multicam plan", "json", "metadata:multicam_plan"),
        ),
    ),
    "multicam.apply": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("timeline", "Applied timeline", "timeline", "state"),),
    ),
    "sync.multicam_audio": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Synced timeline", "timeline", "state"),
            PortSpec(
                "report",
                "Multicam report",
                "json",
                "metadata:multicam_report",
            ),
        ),
    ),
    "timeline.load": (
        (),
        (
            PortSpec("timeline", "Loaded timeline", "timeline", "state"),
            PortSpec("media", "Media info", "media", "media"),
        ),
    ),
    "curation.prepare": (
        (PortSpec("artifacts", "Project artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Curation manifest", "artifact_map", "artifacts"),),
    ),
    "transcript.dedupe": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("transcript", "Clean transcript", "transcript", "transcript"),
            PortSpec("artifacts", "Transcript artifacts", "artifact_map", "artifacts"),
        ),
    ),
    "speech.editorial_clean": (
        (
            PortSpec("transcript", "Transcript", "transcript", "transcript", True),
            PortSpec(
                "speech",
                "Speech spans",
                "sample_spans",
                "speech_intervals",
                False,
            ),
        ),
        (
            PortSpec("transcript", "Clean transcript", "transcript", "transcript"),
            PortSpec(
                "discarded",
                "Discarded sentence ids",
                "integer_list",
                "discard_sentence_ids",
            ),
            PortSpec(
                "artifacts",
                "Editorial artifacts",
                "artifact_map",
                "artifacts",
            ),
            PortSpec(
                "report",
                "Editorial cleanup report",
                "json",
                "metadata:editorial_clean",
            ),
        ),
    ),
    "shorts.select": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("shorts", "Selected Shorts", "short_list", "shorts"),),
    ),
    "shorts.tighten": (
        (PortSpec("shorts", "Selected Shorts", "short_list", "shorts", True),),
        (PortSpec("shorts", "Tightened Shorts", "short_list", "shorts"),),
    ),
    "shorts.score": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("shorts", "Scored Shorts", "short_list", "shorts"),),
    ),
    "shorts.reframe": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("shorts", "Reframed Shorts", "short_list", "shorts"),),
    ),
    "shorts.captions": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("captions", "Short captions", "dict", "short_captions"),),
    ),
    "shorts.render": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts"),),
    ),
    "broll.plan": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("plan", "B-roll plan", "dict", "metadata:broll_plan"),),
    ),
    "assets.shots": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("shots", "Shot detection", "dict", "metadata:shots"),),
    ),
    "assets.match": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("matches", "B-roll matches", "dict", "metadata:broll_matches"),),
    ),
    "music.beat": ((), (PortSpec("beat", "Beat grid", "dict", "metadata:beat"),)),
    "sfx.plan": ((), (PortSpec("plan", "SFX plan", "dict", "metadata:sfx_plan"),)),
    "assets.index": ((), (PortSpec("assets", "Asset index", "dict", "artifacts"),)),
    "audio.master": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Audio master", "artifact_map", "artifacts"),),
    ),
    "audio.isolate": (
        (PortSpec("master", "Audio master", "audio", "artifacts:audio_master", False),),
        (PortSpec("isolated", "Isolated voice", "audio", "artifacts:audio_isolated"),),
    ),
    "broll.generate": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("generated", "Generated B-roll", "json", "metadata:generated_broll"),),
    ),
    "audio.qa": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Audio QA", "artifact_map", "artifacts"),),
    ),
    "color.grade": ((), (PortSpec("artifacts", "Colour filters", "artifact_map", "artifacts"),)),
    "titles.plan": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Titles", "artifact_map", "artifacts"),),
    ),
    "thumbnail.generate": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("artifacts", "Thumbnails", "artifact_map", "artifacts"),),
    ),
    "storyboard.plan": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Storyboard", "artifact_map", "artifacts"),),
    ),
    "transcript.translate": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("transcript", "Translated transcript", "transcript", "transcript"),),
    ),
    "audio.diarize": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("speakers", "Speaker turns", "dict", "metadata:speaker_turns"),),
    ),
    "alignment.forced": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("transcript", "Word-aligned transcript", "transcript", "transcript"),
            PortSpec("report", "Alignment report", "json", "metadata:forced_alignment"),
        ),
    ),
    "localization.dub": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Dubbed Shorts", "artifact_map", "artifacts"),),
    ),
    "human.gate": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", False),),
        (),
    ),
    "human.input": (
        (PortSpec("metadata", "Context metadata", "dict", "metadata", False),),
        (),
    ),
    "human.files": (
        (PortSpec("metadata", "Context metadata", "dict", "metadata", False),),
        (),
    ),
    "research.multi_agent": (
        (),
        (PortSpec("agents", "Scoped research", "json", "metadata:research_agents"),),
    ),
    "research.consolidate": (
        (PortSpec("agents", "Scoped research", "json", "metadata:research_agents", True),),
        (PortSpec("master", "Master research", "json", "metadata:research_master"),),
    ),
    "presenter.profile": (
        (),
        (PortSpec("profile", "Presenter profile", "json", "metadata:presenter_profile"),),
    ),
    "script.dual_output": (
        (PortSpec("master", "Master research", "json", "metadata:research_master", True),),
        (PortSpec("script", "Dual script", "json", "metadata:script"),),
    ),
    "metadata.pack": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "Metadata", "artifact_map", "artifacts"),),
    ),
    "thumbnail.pack": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Thumbnails", "artifact_map", "artifacts"),),
    ),
    "publish.queue": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Publish queue", "artifact_map", "artifacts"),),
    ),
    "chapters.plan": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (PortSpec("artifacts", "Chapters", "artifact_map", "artifacts"),),
    ),
    "nle.qa": (
        (PortSpec("artifacts", "NLE artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "NLE QA", "artifact_map", "artifacts"),),
    ),
    "delivery.package": (
        (PortSpec("artifacts", "Short files", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Delivery package", "artifact_map", "artifacts"),),
    ),
    "qa.caption_effect": (
        (PortSpec("artifacts", "Caption artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Caption QA report", "artifact_map", "artifacts"),),
    ),
    "qa.overlay_bounds": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "Overlay bounds report", "artifact_map", "artifacts"),),
    ),
    "qa.final": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("artifacts", "QA report", "artifact_map", "artifacts"),),
    ),
    "publish.release_kit": (
        (PortSpec("artifacts", "Delivery artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Release kit", "artifact_map", "artifacts"),),
    ),
    "shorts.ab": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", True),),
        (PortSpec("artifacts", "A/B variants", "artifact_map", "artifacts"),),
    ),
    "analytics.import": ((), (PortSpec("artifacts", "Analytics", "artifact_map", "artifacts"),)),
    "review.queue": ((), (PortSpec("artifacts", "Review queue", "artifact_map", "artifacts"),)),
    "analytics.review": ((), (PortSpec("artifacts", "Review", "artifact_map", "artifacts"),)),
    "content.idea": ((), (PortSpec("artifacts", "Idea", "artifact_map", "artifacts"),)),
    "content.research": ((), (PortSpec("artifacts", "Research", "artifact_map", "artifacts"),)),
    "content.script": ((), (PortSpec("artifacts", "Script", "artifact_map", "artifacts"),)),
    "publish.webhook": (
        (PortSpec("artifacts", "Artifacts", "artifact_map", "artifacts", True),),
        (PortSpec("artifacts", "Published", "artifact_map", "artifacts"),),
    ),
    "flow.conditional": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.loop": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.subflow": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.map": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "flow.reduce": (
        (PortSpec("input", "Input", "any", "artifacts", True),),
        (PortSpec("output", "Output", "any", "artifacts"),),
    ),
    "experiment.evaluate": ((), (PortSpec("artifacts", "Winner", "artifact_map", "artifacts"),)),
    "edit.drift": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("transcript", "Corrected transcript", "transcript", "transcript"),
            PortSpec("report", "Drift report", "json", "metadata:drift_correction"),
            PortSpec("map", "Frame-accurate speech map", "json", "metadata:speech_map"),
        ),
    ),
    "narrative.beats": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("beats", "Narrative beats", "json", "metadata:narrative_beats"),
            PortSpec(
                "entities",
                "Narrative entities",
                "json",
                "artifacts:narrative_entities",
            ),
        ),
    ),
    "transcript.blocks": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("blocks", "Context blocks", "json", "metadata:narrative_blocks"),
            PortSpec(
                "blocks_markdown",
                "Context blocks (Markdown)",
                "artifact",
                "artifacts:narrative_blocks_md",
            ),
        ),
    ),
    "entities.extract": (
        (
            PortSpec("blocks", "Context blocks", "json", "metadata:narrative_blocks", True),
            PortSpec("script", "Dual script", "json", "metadata:script", False),
        ),
        (
            PortSpec(
                "entities",
                "Entity manifest",
                "json",
                "metadata:narrative_entities",
            ),
        ),
    ),
    "storyboard.preview": (
        (
            PortSpec("units", "Unit storyboard", "json", "metadata:storyboard_units", True),
            PortSpec("style", "Style guide", "json", "metadata:style_guide", True),
        ),
        (
            PortSpec(
                "previews",
                "Placeholder previews",
                "json",
                "metadata:storyboard_previews",
            ),
        ),
    ),
    "broll.plan_master": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (PortSpec("plan", "B-roll plan", "json", "metadata:broll_plan"),),
    ),
    "audio.duck": (
        (PortSpec("master", "Audio master", "audio", "artifacts:audio_master", True),),
        (PortSpec("mix", "Audio mix", "audio", "artifacts:audio_mix"),),
    ),
    "rules.memory": (
        (),
        (PortSpec("report", "Rules report", "json", "metadata:rules_memory"),),
    ),
    "motion.codegen": (
        (),
        (PortSpec("scenes", "Motion scenes", "json", "metadata:motion_scenes"),),
    ),
    "motion.render": (
        (PortSpec("scenes", "Motion scenes", "json", "metadata:motion_scenes", False),),
        (PortSpec("manifest", "Motion render manifest", "json", "metadata:motion_manifest"),),
    ),
    "audio.compose": (
        (PortSpec("media", "Media info", "media", "media", False),),
        (PortSpec("music", "Music bed", "artifact", "artifacts:audio_music"),),
    ),
    "sfx.synthesize": (
        (),
        (PortSpec("cues", "Foley cues", "json", "metadata:sfx_cues"),),
    ),
    "audio.mix": (
        (PortSpec("master", "Audio master", "audio", "artifacts:audio_master", True),),
        (PortSpec("mix", "Final mix", "audio", "artifacts:audio_mix"),),
    ),
    "factcheck.audit": (
        (),
        (PortSpec("report", "Fact-check report", "json", "metadata:factcheck"),),
    ),
    "voice.patch": (
        (PortSpec("master", "Audio master", "audio", "artifacts:audio_mix", False),),
        (PortSpec("master", "Repaired master", "audio", "artifacts:audio_master"),),
    ),
    "intro.compile": (
        (),
        (PortSpec("intro", "Intro clip", "artifact", "artifacts:intro"),),
    ),
    "style.guide": (
        (),
        (PortSpec("style", "Style guide", "json", "metadata:style_guide"),),
    ),
    "storyboard.units": (
        (PortSpec("script", "Dual script", "json", "metadata:script", False),),
        (PortSpec("units", "Unit storyboard", "json", "metadata:storyboard_units"),),
    ),
    "assets.discover": (
        (PortSpec("units", "Unit storyboard", "json", "metadata:storyboard_units", False),),
        (PortSpec("candidates", "Asset candidates", "json", "metadata:asset_candidates"),),
    ),
    "assets.harvest": (
        (PortSpec("candidates", "Asset candidates", "json", "metadata:asset_candidates", False),),
        (PortSpec("manifest", "Harvest manifest", "json", "metadata:assets_manifest"),),
    ),
    "assets.license_audit": (
        (PortSpec("manifest", "Harvest manifest", "json", "metadata:assets_manifest", False),),
        (PortSpec("blockers", "License blockers", "json", "metadata:license_blockers"),),
    ),
    "assets.assign": (
        (PortSpec("units", "Unit storyboard", "json", "metadata:storyboard_units", False),),
        (PortSpec("assignments", "Asset assignments", "json", "metadata:asset_assignments"),),
    ),
    "voice.clone": (
        (),
        (
            PortSpec(
                "patch",
                "Cloned voice patch",
                "audio",
                "artifacts:voice_clone_patch",
            ),
        ),
    ),
    "narration.synthesize": (
        (),
        (
            PortSpec("audio", "Narration WAV", "string", "artifacts:audio_narration"),
            PortSpec("master", "Dialogue master", "string", "artifacts:audio_master"),
        ),
    ),
    "narration.align": (
        (PortSpec("audio", "Narration WAV", "string", "artifacts:audio_narration", True),),
        (
            PortSpec("transcript", "Narration transcript", "transcript", "transcript"),
            PortSpec("words", "Word timings", "json", "artifacts:narration_words"),
        ),
    ),
    "storyboard.timed": (
        (PortSpec("transcript", "Narration transcript", "transcript", "transcript", True),),
        (PortSpec("units", "Timed units", "json", "artifacts:storyboard_units"),),
    ),
    "captions.plan": (
        (PortSpec("transcript", "Transcript", "transcript", "transcript", True),),
        (
            PortSpec("captions", "Caption ASS", "string", "artifacts:captions_ass"),
            PortSpec("subtitles", "Merged ASS", "string", "artifacts:subtitles_ass"),
        ),
    ),
    "scene.codegen": (
        (
            PortSpec("units", "Timed units", "json", "artifacts:storyboard_units", True),
            PortSpec("style", "Style guide", "json", "metadata:style_guide", False),
        ),
        (
            PortSpec("scenes", "Scene graph", "json", "artifacts:motion_scenes"),
            PortSpec("code", "Scene code", "string", "artifacts:scene_code"),
        ),
    ),
    "scene.render": (
        (PortSpec("scenes", "Scene graph", "json", "artifacts:motion_scenes", True),),
        (PortSpec("manifest", "Render manifest", "json", "artifacts:motion_manifest"),),
    ),
    "scene.assemble": (
        (
            PortSpec("manifest", "Render manifest", "json", "artifacts:motion_manifest", True),
            PortSpec("audio", "Final audio", "string", "artifacts:audio_mix", True),
        ),
        (PortSpec("draft", "Draft video", "string", "artifacts:video_draft"),),
    ),
    "export.master": (
        (PortSpec("draft", "Draft video", "string", "artifacts:video_draft", True),),
        (
            PortSpec("video", "Master video", "string", "artifacts:video"),
            PortSpec("report", "Master report", "json", "artifacts:master_report"),
        ),
    ),
    "vision.ocr": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("ocr", "OCR boxes", "json", "artifacts:vision_ocr"),),
    ),
    "vision.segment": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("segments", "Subject masks", "json", "artifacts:vision_segments"),),
    ),
    "vision.track": (
        (PortSpec("ocr", "OCR boxes", "json", "artifacts:vision_ocr", True),),
        (PortSpec("tracks", "Track keyframes", "json", "artifacts:vision_tracks"),),
    ),
    "motion.callout": (
        (PortSpec("units", "Timed units", "json", "artifacts:storyboard_units", True),),
        (PortSpec("callouts", "Callout cards", "json", "artifacts:motion_callouts"),),
    ),
    "motion.attach": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", True),),
        (
            PortSpec("timeline", "Timeline state", "timeline", "state"),
            PortSpec("report", "Overlay sync", "json", "artifacts:motion_attached"),
        ),
    ),
    "composite.matte": (
        (PortSpec("segments", "Subject masks", "json", "artifacts:vision_segments", True),),
        (PortSpec("plan", "Matte plan", "json", "artifacts:matte_plan"),),
    ),
    "qa.frames": (
        (),
        (PortSpec("report", "Frame QA", "json", "artifacts:qa_frames"),),
    ),
    "qa.transcript": (
        (),
        (PortSpec("report", "Transcript QA", "json", "artifacts:qa_transcript"),),
    ),
    "qa.vision": (
        (),
        (
            PortSpec("report", "Vision QA", "json", "artifacts:vision_qa"),
            PortSpec("markdown", "Vision QA markdown", "string", "artifacts:vision_qa_md"),
        ),
    ),
    "qa.repair": (
        (),
        (
            PortSpec("plan", "Repair plan", "json", "artifacts:qa_repair"),
            PortSpec("markdown", "Repair markdown", "string", "artifacts:qa_repair_md"),
        ),
    ),
    "entities.apply": (
        (),
        (
            PortSpec(
                "entities",
                "Corrected entities",
                "json",
                "metadata:narrative_entities_corrected",
            ),
        ),
    ),
    "decoupage.calibrate": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("profile", "Calibration profile", "json", "metadata:decoupage_profile"),),
    ),
    "vision.face_contact": (
        (PortSpec("media", "Media info", "media", "media", True),),
        (PortSpec("labels", "Eye-contact spans", "json", "metadata:eye_contact"),),
    ),
    "step.self_heal": (
        (),
        (PortSpec("report", "Self-heal report", "json", "metadata:self_heal_report"),),
    ),
    "qa.safezone": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", False),),
        (PortSpec("report", "Safe-zone report", "json", "metadata:safezone_report"),),
    ),
    "qa.visual_10fps": (
        (PortSpec("media", "Media info", "media", "media", False),),
        (PortSpec("report", "Visual QA report", "json", "metadata:qa_report"),),
    ),
    "pacing.visual_audit": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", False),),
        (PortSpec("plan", "Pacing plan", "json", "metadata:pacing_plan"),),
    ),
    "sfx.procedural": (
        (),
        (PortSpec("cues", "SFX cues", "json", "metadata:sfx_cues"),),
    ),
    "preset.compile_rule": (
        (),
        (PortSpec("rulebook", "Channel rulebook", "json", "metadata:preset_rulebook"),),
    ),
    "assets.reference_board": (
        (),
        (PortSpec("board", "Reference board", "json", "metadata:reference_board"),),
    ),
    "motion.web_render": (
        (),
        (PortSpec("motion_assets", "Motion assets", "json", "metadata:motion_assets"),),
    ),
    "layout.cutout": (
        (PortSpec("shorts", "Shorts", "short_list", "shorts", False),),
        (PortSpec("layout_plan", "Layout plan", "json", "metadata:layout_plan"),),
    ),
    "vision.gaze": (
        (PortSpec("media", "Media info", "media", "media", False),),
        (PortSpec("gaze_spans", "Gaze spans", "json", "metadata:gaze_spans"),),
    ),
    "assets.screen_capture": (
        (),
        (PortSpec("captured_assets", "Captured assets", "json", "metadata:captured_assets"),),
    ),
    "assets.transformative_guard": (
        (),
        (PortSpec("records", "Transformative records", "json", "metadata:transformative_records"),),
    ),
    "style.reverse_engineer": (
        (),
        (PortSpec("style_preset", "Style preset", "json", "metadata:style_preset"),),
    ),
    "nle.sync_back": (
        (PortSpec("timeline", "Timeline state", "timeline", "state", False),),
        (PortSpec("sync_back_report", "NLE sync report", "json", "metadata:sync_back_report"),),
    ),
    "intro.assemble_last": (
        (),
        (PortSpec("intro_plan", "Intro plan", "json", "metadata:intro_plan"),),
    ),
}


EXTRA_OUTPUTS: dict[str, tuple[PortSpec, ...]] = {
    "analytics.import": (PortSpec("analytics", "Analytics", "dict", "metadata:analytics"),),
    "analytics.review": (
        PortSpec("weights", "Analytics weights", "dict", "metadata:analytics_weights"),
    ),
    "assets.index": (PortSpec("index", "Asset index", "dict", "metadata:assets_index"),),
    "assets.match": (
        PortSpec("plan", "B-roll plan", "dict", "metadata:broll_plan"),
        PortSpec("licenses", "B-roll licenses", "dict", "metadata:broll_licenses"),
        PortSpec("artifacts", "Match files", "artifact_map", "artifacts"),
    ),
    "assets.shots": (
        PortSpec("scenes", "Shot list", "dict", "metadata:scenes"),
        PortSpec("artifacts", "Shot files", "artifact_map", "artifacts"),
    ),
    "audio.diarize": (
        PortSpec("transcript", "Speaker-labelled transcript", "transcript", "transcript"),
        PortSpec("method", "Diarization method", "string", "metadata:diarization_method"),
        PortSpec("turns", "Turn count", "integer", "metadata:diarization_turns"),
        PortSpec("speaker_count", "Speaker count", "integer", "metadata:speaker_count"),
    ),
    "audio.master": (
        PortSpec("filters", "Master filters", "dict", "metadata:audio_master_filters"),
    ),
    "audio.qa": (PortSpec("qa", "Audio QA", "dict", "metadata:audio_qa"),),
    "audio.vad": (
        PortSpec("pad_before_ms", "Pad before", "integer", "metadata:speech_pad_before_ms"),
        PortSpec("pad_after_ms", "Pad after", "integer", "metadata:speech_pad_after_ms"),
        PortSpec("min_speech_ms", "Minimum speech", "integer", "metadata:min_speech_ms"),
        PortSpec(
            "spike_suppression_ms",
            "Spike suppression",
            "integer",
            "metadata:spike_suppression_ms",
        ),
        PortSpec("merge_gap_ms", "Merge gap", "integer", "metadata:merge_gap_ms"),
    ),
    "broll.plan": (PortSpec("artifacts", "B-roll artifacts", "artifact_map", "artifacts"),),
    "color.grade": (PortSpec("filters", "Colour filters", "dict", "metadata:color_filters"),),
    "delivery.package": (
        PortSpec("package", "Delivery manifest", "dict", "metadata:delivery_package"),
    ),
    "edit.timeline": (
        PortSpec("speech", "Adjusted speech", "sample_spans", "speech_intervals"),
        PortSpec("inactive", "Inactive spans", "inactive_spans", "inactive_spans"),
    ),
    "flow.conditional": (PortSpec("metadata", "Flow metadata", "dict", "metadata"),),
    "flow.loop": (PortSpec("metadata", "Loop metadata", "dict", "metadata"),),
    "flow.map": (PortSpec("metadata", "Map metadata", "dict", "metadata"),),
    "flow.reduce": (PortSpec("metadata", "Reduce metadata", "dict", "metadata"),),
    "human.gate": (PortSpec("metadata", "Gate result", "dict", "metadata"),),
    "human.input": (PortSpec("answers", "Human answers", "dict", "metadata:hilt_answers"),),
    "human.files": (PortSpec("files", "Received files", "dict", "metadata:hilt_files"),),
    "localization.dub": (PortSpec("dubbed", "Dubbed Shorts", "list", "metadata:dubbed_shorts"),),
    "music.beat": (
        PortSpec("artifacts", "Beat files", "artifact_map", "artifacts"),
        PortSpec("beats", "Beat list", "list", "metadata:beats"),
    ),
    "review.queue": (PortSpec("review", "Review queue", "dict", "metadata:review"),),
    "sfx.plan": (PortSpec("artifacts", "SFX files", "artifact_map", "artifacts"),),
    "shorts.ab": (
        PortSpec("selected", "A/B Shorts", "short_list", "selected_shorts"),
        PortSpec("variants", "A/B variants", "list", "metadata:ab_variants"),
    ),
    "shorts.captions": (
        PortSpec("shorts", "Shorts", "short_list", "shorts"),
        PortSpec("disabled", "Captions disabled", "boolean", "metadata:captions_disabled"),
    ),
    "shorts.reframe": (PortSpec("selected", "Reframed Shorts", "short_list", "selected_shorts"),),
    "shorts.render": (PortSpec("shorts", "Rendered Shorts", "short_list", "shorts"),),
    "shorts.score": (PortSpec("selected", "Scored Shorts", "short_list", "selected_shorts"),),
    "shorts.select": (PortSpec("selected", "Selected Shorts", "short_list", "selected_shorts"),),
    "thumbnail.generate": (
        PortSpec("thumbs", "Thumbnails", "list", "metadata:thumbnails"),
        PortSpec("title", "Thumbnail title", "string", "metadata:thumbnail_title"),
    ),
    "thumbnail.pack": (PortSpec("pack", "Thumbnail pack", "list", "metadata:thumbnail_pack"),),
    "titles.plan": (PortSpec("titles", "Title plan", "dict", "metadata:titles"),),
    "transcript.translate": (
        PortSpec("artifacts", "Translated files", "artifact_map", "artifacts"),
        PortSpec("translation", "Translation report", "dict", "metadata:translation"),
    ),
}


def ports_for_type(
    step_type: str,
) -> tuple[tuple[PortSpec, ...], tuple[PortSpec, ...]]:
    inputs, outputs = PORTS.get(step_type, ((), ()))
    extra = EXTRA_OUTPUTS.get(step_type, ())
    return inputs, outputs + extra


def type_compatible(source: str, target: str) -> bool:
    return source == target or source == "any" or target == "any"


def validate_recipe_ports(recipe: Any, *, through: str | None = None) -> None:
    """Validate explicit port wiring while leaving legacy ``needs`` untouched.

    When ``through`` is set, only the target and its ancestors are checked, so a
    later export cannot block running to an earlier node.
    """

    from videoflow.steps import get_step

    step_by_id = {step.id: step for step in recipe.steps}
    order = [step.id for step in recipe.topological_order()]
    position = {step_id: index for index, step_id in enumerate(order)}
    allowed = recipe.ids_through(through) if through is not None else None

    for step in recipe.steps:
        # A disabled step is not part of the executable graph. Its wiring is
        # kept for re-enabling, but it must not block the recipe from running.
        if not step.enabled or not step.inputs:
            continue
        if allowed is not None and step.id not in allowed:
            continue
        input_ports = {port.id: port for port in get_step(step.type).input_ports}
        for input_id, reference in step.inputs.items():
            port = input_ports.get(input_id)
            if port is None:
                raise RecipeError(f"{step.id}: unknown input port {input_id}")
            source_id, separator, source_port = str(reference).partition(".")
            if not separator or not source_id or not source_port:
                raise RecipeError(f"{step.id}.{input_id}: expected node.port, got {reference}")
            source = step_by_id.get(source_id)
            if source is None:
                raise RecipeError(f"{step.id}.{input_id}: unknown node {source_id}")
            if not source.enabled:
                raise RecipeError(
                    f"{step.id}.{input_id}: source {source_id} is disabled; "
                    "enable it or remove this input"
                )
            if position.get(source_id, 10**9) >= position.get(step.id, -1):
                if depends_on(source_id, step.id, step_by_id):
                    raise RecipeError(
                        f"{step.id}.{input_id}: source {source_id} must run earlier "
                        f"(wiring {source_id}.{source_port} -> "
                        f"{step.id}.{input_id} creates a cycle)"
                    )
                raise RecipeError(f"{step.id}.{input_id}: source {source_id} must run earlier")
            ancestors: set[str] = set()
            stack = list(step.needs)
            while stack:
                dependency = stack.pop()
                if dependency in ancestors:
                    continue
                ancestors.add(dependency)
                parent = step_by_id.get(dependency)
                if parent is not None:
                    stack.extend(parent.needs)
            if source_id not in ancestors:
                raise RecipeError(
                    f"{step.id}.{input_id}: add {source_id} to needs to guarantee ordering"
                )
            outputs = {port.id: port for port in _output_ports(source.type)}
            output_port = outputs.get(source_port)
            if output_port is None:
                raise RecipeError(f"{step.id}.{input_id}: unknown output {source_id}.{source_port}")
            if not type_compatible(output_port.type, port.type):
                raise RecipeError(
                    f"{step.id}.{input_id}: type mismatch {output_port.type} -> {port.type}"
                )
    from videoflow.domain.paths import resolve_allowed
    from videoflow.runtime import allowed_roots

    for step in recipe.steps:
        try:
            if step.media_override.strip():
                media = resolve_allowed(Path(step.media_override), allowed_roots())
                if not media.is_file():
                    raise RecipeError(f"{step.id}: media override is not a file: {media}")
            if step.output_mode == "folder":
                if not step.output_dir.strip():
                    raise RecipeError(f"{step.id}: output folder is required")
                resolve_allowed(Path(step.output_dir), allowed_roots())
        except VideoFlowError as exc:
            raise RecipeError(f"{step.id}: {exc}") from exc

    # Required ports may remain implicit for legacy recipes. Explicit wiring must
    # supply every required input it declares.
    for step in recipe.steps:
        if not step.inputs:
            continue
        required = {port.id for port in _input_ports(step.type) if port.required}
        missing = sorted(required - set(step.inputs))
        if missing:
            raise RecipeError(f"{step.id}: missing required inputs {missing}")


def _input_ports(step_type: str) -> tuple[PortSpec, ...]:
    return ports_for_type(step_type)[0]


def _output_ports(step_type: str) -> tuple[PortSpec, ...]:
    return ports_for_type(step_type)[1]


def read_context(context: Any, key: str) -> Any:
    if key.startswith("artifacts:"):
        return context.artifacts.get(key.split(":", 1)[1])
    if key.startswith("metadata:"):
        return context.metadata.get(key.split(":", 1)[1])
    return getattr(context, key, None)


def write_context(context: Any, key: str, value: Any) -> None:
    if key.startswith("artifacts:"):
        context.artifacts[key.split(":", 1)[1]] = value
    elif key.startswith("metadata:"):
        context.metadata[key.split(":", 1)[1]] = value
    else:
        setattr(context, key, value)


def capture_outputs(context: Any, step: Any, node_id: str) -> None:
    outputs: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for port in step.output_ports:
        value = copy.deepcopy(read_context(context, port.context_key))
        outputs[port.id] = value
        hashes[port.id] = digest_value(value)
    context.port_outputs[node_id] = outputs
    context.port_hashes[node_id] = hashes


def apply_inputs(context: Any, step: Any, wiring: dict[str, str]) -> None:
    input_ports = {port.id: port for port in step.input_ports}
    for input_id, reference in wiring.items():
        port = input_ports[input_id]
        source_id, _, source_port = reference.partition(".")
        if source_id not in context.port_outputs:
            raise RecipeError(f"Input source {source_id} has not produced an output")
        source_outputs = context.port_outputs[source_id]
        if source_port not in source_outputs:
            raise RecipeError(f"Input source {source_id}.{source_port} is missing")
        write_context(context, port.context_key, copy.deepcopy(source_outputs[source_port]))


def input_fingerprint(context: Any, wiring: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for input_id, reference in wiring.items():
        source_id, _, source_port = reference.partition(".")
        result[input_id] = context.port_hashes.get(source_id, {}).get(source_port, "")
    return result


def digest_value(value: Any) -> str:
    try:
        serialized = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = repr(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
