"""Full AI Editor: a long-form, human-reviewed documentary editing recipe.

The recipe is deliberately explicit about its checkpoints. Steps that need a
different engine (face tracking, motion rendering, voice cloning) stay available
as later nodes; the HILT checkpoints make the handoff durable today.
"""

from __future__ import annotations

from videoflow.engine.recipes.catalog import _add_recipe

_add_recipe(
    "full_ai_editor",
    "Full AI Editor",
    [
        {
            "id": "brief",
            "type": "human.input",
            "params": {
                "gate_id": "brief",
                "title": "Editorial brief",
                "description": (
                    "Define the topic, temporal scope, presenter voice, visual "
                    "direction, and target length before research starts."
                ),
                "save_as": "hilt/brief.json",
                "questions": [
                    {
                        "id": "topic",
                        "label": "Topic or directive",
                        "type": "textarea",
                        "required": True,
                        "placeholder": "e.g. the history of a political party's scandals",
                    },
                    {
                        "id": "temporal_scope",
                        "label": "Temporal and thematic boundaries",
                        "type": "textarea",
                        "required": True,
                        "placeholder": "Start year, end year, people, regions, exclusions",
                    },
                    {
                        "id": "presenter_profile",
                        "label": "Presenter speech profile",
                        "type": "textarea",
                        "required": False,
                        "help": "Vocabulary, cadence, sample videos, or a transcript path.",
                    },
                    {
                        "id": "visual_style",
                        "label": "Visual and audio direction",
                        "type": "textarea",
                        "required": False,
                        "help": "Palette, typography, textures, music, Foley, references.",
                    },
                    {
                        "id": "target_duration",
                        "label": "Target duration (minutes)",
                        "type": "number",
                        "required": False,
                        "default": 70,
                    },
                ],
            },
        },
        {
            "id": "research",
            "type": "research.multi_agent",
            "needs": ["brief"],
            "params": {
                "topic": "$topic",
                "allow_external_services": "$allow_external_services",
                "max_results": 6,
                "fetch_pages": 3,
            },
        },
        {
            "id": "research_files",
            "type": "human.files",
            "needs": ["research"],
            "params": {
                "gate_id": "research_files",
                "title": "Revise research (optional)",
                "description": (
                    "Review the generated dossiers. Upload corrected or additional "
                    "Markdown files here; otherwise submit without files and continue."
                ),
                "files": [
                    {
                        "id": "agent_a",
                        "label": "Revised Agent A",
                        "required": False,
                        "accept": [".md", ".txt", ".json"],
                        "target": "research/revised/agent-a.md",
                    },
                    {
                        "id": "agent_b",
                        "label": "Revised Agent B",
                        "required": False,
                        "accept": [".md", ".txt", ".json"],
                        "target": "research/revised/agent-b.md",
                    },
                    {
                        "id": "agent_c",
                        "label": "Revised Agent C",
                        "required": False,
                        "accept": [".md", ".txt", ".json"],
                        "target": "research/revised/agent-c.md",
                    },
                    {
                        "id": "agent_d",
                        "label": "Revised Agent D",
                        "required": False,
                        "accept": [".md", ".txt", ".json"],
                        "target": "research/revised/agent-d.md",
                    },
                ],
            },
        },
        {
            "id": "research_review",
            "type": "human.gate",
            "needs": ["research_files"],
            "params": {
                "gate_id": "research_review",
                "title": "Research review",
                "description": "Approve the scoped dossiers after reviewing their citations.",
                "artifacts": ["research/"],
            },
        },
        {
            "id": "research_consolidate",
            "type": "research.consolidate",
            "needs": ["research_review"],
            "params": {"max_cases": 200, "require_sources": True},
        },
        {
            "id": "research_master_review",
            "type": "human.gate",
            "needs": ["research_consolidate"],
            "params": {
                "gate_id": "research_master_review",
                "title": "Master dossier review",
                "description": "Approve the deduplicated master dossier before the script.",
                "artifacts": ["research/master.md", "research/master.json"],
            },
        },
        {
            "id": "script",
            "type": "script.dual_output",
            "needs": ["research_master_review"],
            "params": {
                "target_words": 11000,
                "max_sections": 314,
                "max_cases_per_call": 8,
            },
        },
        {
            "id": "script_files",
            "type": "human.files",
            "needs": ["script"],
            "params": {
                "gate_id": "script_files",
                "title": "Revise the dual script (optional)",
                "description": (
                    "Upload a revised narration or edition script; otherwise submit "
                    "without files and review the generated script."
                ),
                "files": [
                    {
                        "id": "narration",
                        "label": "Revised narration script",
                        "required": False,
                        "accept": [".txt", ".md"],
                        "target": "script/narration.txt",
                    },
                    {
                        "id": "edition",
                        "label": "Revised edition script",
                        "required": False,
                        "accept": [".md", ".txt"],
                        "target": "script/edition.md",
                    },
                ],
            },
        },
        {
            "id": "script_review",
            "type": "human.gate",
            "needs": ["script_files"],
            "params": {
                "gate_id": "script_review",
                "title": "Script lock",
                "description": "Lock the narration and edition script before media assembly.",
                "artifacts": ["script/"],
            },
        },
        {
            "id": "ingest",
            "type": "ingest",
            "needs": ["script_review"],
            "params": {"extract_pcm": True},
        },
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "params": {},
        },
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest"],
            "params": {"mode": "auto", "language": "pt", "model_size": "small"},
        },
        {
            "id": "retakes",
            "type": "retakes.cull",
            "needs": ["vad", "transcribe"],
            "params": {"enabled": True},
        },
        {
            "id": "drift",
            "type": "edit.drift",
            "needs": ["transcribe"],
            "params": {"offset_ms": 200.0},
        },
        {
            "id": "timeline",
            "type": "edit.timeline",
            "needs": ["vad", "retakes", "drift"],
            "params": {
                "cut_mode": "hard",
                "replace_manual": True,
                "use_transcript_spans": True,
                "noise_filter": "non_speech",
                "pad_before_ms": 60,
                "pad_after_ms": 120,
                "max_silence_ms": 500,
                "keep_silence_ms": 300,
            },
        },
        {
            "id": "export_preview",
            "type": "export.nle",
            "needs": ["timeline"],
            "params": {
                "targets": ["resolve", "premiere", "kdenlive"],
                "filename_mode": "fixed",
                "basename": "decoupage-preview",
            },
        },
        {
            "id": "decoupage_files",
            "type": "human.files",
            "needs": ["export_preview"],
            "params": {
                "gate_id": "decoupage_files",
                "title": "Optional revised decoupage XML",
                "description": (
                    "Review the automated decoupage. If you corrected it in an NLE, "
                    "upload the revised XML here; otherwise submit without a file."
                ),
                "files": [
                    {
                        "id": "revised_xml",
                        "label": "Revised timeline XML",
                        "required": False,
                        "accept": [".xml", ".fcpxml", ".kdenlive"],
                        "target": "decoupage/revised.xml",
                    }
                ],
            },
        },
        {
            "id": "decoupage_review",
            "type": "human.gate",
            "needs": ["decoupage_files"],
            "params": {
                "gate_id": "decoupage_review",
                "title": "Decoupage audit",
                "description": (
                    "Approve the cut or send the job back. Green-label eye-contact "
                    "clips are metadata in the timeline and NLE markers."
                ),
                "artifacts": ["exports/", "project_state.json", "decoupage/"],
            },
        },
        {
            "id": "narrative",
            "type": "narrative.beats",
            "needs": ["transcribe"],
            "params": {"min_block_words": 100, "max_block_words": 300},
        },
        {
            "id": "entities_review",
            "type": "human.input",
            "needs": ["narrative"],
            "params": {
                "gate_id": "entities_review",
                "title": "Entity and fact corrections",
                "description": (
                    "Correct phonetic names, locations, objects, and metrics before "
                    "the art-direction and asset passes."
                ),
                "save_as": "entities/corrections.json",
                "questions": [
                    {
                        "id": "people_corrections",
                        "label": "Name and phonetics corrections",
                        "type": "textarea",
                        "required": False,
                        "help": "One correction per line: heard -> canonical.",
                    },
                    {
                        "id": "visual_corrections",
                        "label": "Objects, locations, and events",
                        "type": "textarea",
                        "required": False,
                    },
                    {
                        "id": "metric_corrections",
                        "label": "Numbers, dates, and percentages",
                        "type": "textarea",
                        "required": False,
                    },
                ],
            },
        },
        {
            "id": "style_files",
            "type": "human.files",
            "needs": ["script_review"],
            "params": {
                "gate_id": "style_files",
                "title": "Art direction references",
                "description": (
                    "Upload reference boards or a style guide. The recipe records "
                    "the palette, typography, texture, and audio direction."
                ),
                "files": [
                    {
                        "id": "reference",
                        "label": "Reference board or style note",
                        "required": False,
                        "accept": [".png", ".jpg", ".jpeg", ".webp", ".pdf", ".md", ".txt"],
                        "target": "style/references/",
                    }
                ],
            },
        },
        {
            "id": "style_review",
            "type": "human.gate",
            "needs": ["style_files", "entities_review"],
            "params": {
                "gate_id": "style_review",
                "title": "Style lock",
                "description": "Approve the art direction before asset harvesting.",
                "artifacts": ["style/", "entities/"],
            },
        },
        {
            "id": "storyboard",
            "type": "storyboard.plan",
            "needs": ["timeline", "script_review"],
            "params": {},
        },
        {
            "id": "assets_index",
            "type": "assets.index",
            "needs": ["ingest"],
            "params": {"asset_dir": "$assets_dir"},
        },
        {
            "id": "broll",
            "type": "broll.plan_master",
            "needs": ["timeline", "assets_index", "narrative"],
            "params": {"asset_dir": "$assets_dir", "max_per_block": 2},
        },
        {
            "id": "audio_master",
            "type": "audio.master",
            "needs": ["ingest"],
            "params": {},
        },
        {
            "id": "audio_qa",
            "type": "audio.qa",
            "needs": ["audio_master"],
            "params": {},
        },
        {
            "id": "sample_review",
            "type": "human.gate",
            "needs": [
                "decoupage_review",
                "style_review",
                "storyboard",
                "broll",
                "audio_qa",
            ],
            "params": {
                "gate_id": "sample_review",
                "title": "Sample homologation",
                "description": (
                    "Review the preview, B-roll plan, audio QA, and storyboard. "
                    "Leave feedback in the comment; it is recorded with the approval."
                ),
                "artifacts": [
                    "exports/",
                    "broll/",
                    "audio/qa.json",
                    "storyboard.json",
                    "style/",
                ],
            },
        },
        {
            "id": "factcheck_review",
            "type": "human.input",
            "needs": ["narrative", "sample_review"],
            "params": {
                "gate_id": "factcheck",
                "title": "Fact-check and repair",
                "description": (
                    "Audit factual and legal flags. Upload a corrected audio patch "
                    "or voice note when a line must be repaired."
                ),
                "save_as": "factcheck/review.json",
                "questions": [
                    {
                        "id": "facts_ok",
                        "label": "Are the facts and attributions correct?",
                        "type": "boolean",
                        "required": True,
                    },
                    {
                        "id": "corrections",
                        "label": "Corrections or repair notes",
                        "type": "textarea",
                        "required": False,
                    },
                ],
            },
        },
        {
            "id": "final_review",
            "type": "human.gate",
            "needs": ["factcheck_review", "sample_review"],
            "params": {
                "gate_id": "final_review",
                "title": "Final approval",
                "description": "Approve the final assembly and delivery package.",
                "artifacts": [
                    "exports/",
                    "audio/qa.json",
                    "factcheck/",
                    "broll/",
                ],
            },
        },
        {
            "id": "export",
            "type": "export.nle",
            "needs": ["final_review", "timeline"],
            "params": {
                "targets": ["resolve", "premiere", "kdenlive"],
                "filename_mode": "source_timestamp",
            },
        },
        {
            "id": "nle_qa",
            "type": "nle.qa",
            "needs": ["export"],
            "params": {},
        },
        {
            "id": "video_export",
            "type": "export.video",
            "needs": ["export"],
            "params": {"preset": "ultrafast", "subdir": "exports"},
        },
        {
            "id": "chapters",
            "type": "chapters.plan",
            "needs": ["transcribe"],
            "params": {"max_chapters": 12},
        },
    ],
    description=(
        "A long-form, human-reviewed documentary pipeline: brief, research, dual "
        "script, decoupage audit, entity corrections, style lock, asset and audio "
        "review, fact-check, final approval, and NLE/video export. HILT checkpoints "
        "persist every question, approval, and uploaded file."
    ),
    variables={
        "assets_dir": {
            "type": "string",
            "default": "",
            "description": "Optional local folder with licensed video and image assets.",
        },
        "target_duration": {
            "type": "number",
            "default": 70,
            "description": "Target runtime in minutes.",
        },
        "topic": {
            "type": "string",
            "default": "",
            "description": "Research directive; the brief answer is used when empty.",
        },
        "allow_external_services": {
            "type": "boolean",
            "default": False,
            "description": "Allow SearXNG, Wikipedia, Internet Archive, and page fetches.",
        },
    },
)
