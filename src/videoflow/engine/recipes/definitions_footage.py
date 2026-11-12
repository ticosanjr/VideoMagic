"""Footage Intelligence Edit: real footage, vision anchors, overlays, and QA."""

from __future__ import annotations

from typing import Any

from videoflow.engine.recipes.catalog import _add_recipe
from videoflow.engine.recipes.ui_layout import build_ui


def _ui() -> dict[str, Any]:
    return build_ui(
        [
            (
                "decoupage",
                "1 · Ingest e decupagem",
                (
                    "Transcrição, retakes, drift, timeline e auditoria humana do "
                    "corte com XML de referência."
                ),
                "#f59e0b",
                [
                    ["brief", "ingest", "vad"],
                    ["transcribe", "drift", "retakes", "llm_cleanup"],
                    ["narrative", "timeline", "export_preview"],
                    ["decoupage_files", "decoupage_review"],
                ],
            ),
            (
                "story",
                "2 · Entidades, estilo e storyboard",
                (
                    "Pessoas, objetos e métricas; style guide; unidades visuais e "
                    "previews antes da mídia."
                ),
                "#22c55e",
                [
                    ["transcript_blocks", "entities_extract", "entities_review"],
                    ["entities_apply", "style_files", "style_guide"],
                    ["style_review", "storyboard", "storyboard_units"],
                    ["storyboard_preview", "units_review"],
                ],
            ),
            (
                "vision",
                "3 · Visão e ancoragem",
                (
                    "OCR, máscaras de sujeito, tracking, revisão humana e callouts "
                    "ancorados no texto e no movimento real."
                ),
                "#38bdf8",
                [
                    ["vision_ocr", "vision_segment", "vision_track"],
                    ["vision_review", "composite_matte", "motion_callout"],
                ],
            ),
            (
                "media",
                "4 · Mídia, overlays e cor",
                (
                    "Mídia licenciada, atribuição, overlays no estado do projeto, "
                    "títulos, legendas e correção de cor."
                ),
                "#06b6d4",
                [
                    ["assets_index", "assets_discover", "assets_harvest"],
                    ["assets_license_audit", "assets_review", "assets_assign"],
                    ["motion_attach", "titles", "captions", "color"],
                ],
            ),
            (
                "audio",
                "5 · Áudio e mix",
                (
                    "Master de diálogo, trilha, Foley, ducking, mix e loudness."
                ),
                "#a78bfa",
                [
                    ["audio_master", "audio_compose", "sfx_synthesize"],
                    ["audio_mix", "audio_qa"],
                ],
            ),
            (
                "delivery",
                "6 · QA e entrega",
                (
                    "Export MP4 com mix e legendas, NLE/EDL, QA de frames e visão, "
                    "plano de reparo, aprovação final e capítulos."
                ),
                "#fb7185",
                [
                    ["motion_review", "export_video", "export_nle"],
                    ["nle_qa", "qa_frames", "qa_vision"],
                    ["qa_repair", "qa_review", "final_review", "chapters"],
                ],
            ),
        ]
    )


_STEPS: list[dict[str, Any]] = [
    {
        "id": "brief",
        "type": "human.input",
        "params": {
            "gate_id": "brief",
            "title": "Briefing do footage",
            "description": (
                "Defina regras criativas, estilo, legenda, direitos e uso de "
                "mídia externa antes da decupagem."
            ),
            "save_as": "hilt/brief.json",
            "questions": [
                {
                    "id": "topic",
                    "label": "Tema e recorte editorial",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "id": "visual_style",
                    "label": "Direção visual",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "audio_direction",
                    "label": "Direção de áudio",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "caption_language",
                    "label": "Idioma das legendas",
                    "type": "text",
                    "required": False,
                    "placeholder": "pt",
                },
                {
                    "id": "allow_external_services",
                    "label": "Permitir mídia externa",
                    "type": "boolean",
                    "required": False,
                },
                {
                    "id": "rights_rule",
                    "label": "Regra de direitos",
                    "type": "textarea",
                    "required": False,
                    "help": "Ex.: só Pexels/Pixabay com licença clara; sem YouTube.",
                },
            ],
        },
    },
    {"id": "ingest", "type": "ingest", "needs": ["brief"], "params": {"extract_pcm": True}},
    {"id": "vad", "type": "audio.vad", "needs": ["ingest"], "params": {}},
    {
        "id": "transcribe",
        "type": "transcribe",
        "needs": ["ingest"],
        "params": {"mode": "auto", "language": "$language", "model_size": "$whisper_model"},
    },
    {
        "id": "drift",
        "type": "edit.drift",
        "needs": ["transcribe"],
        "params": {"offset_ms": 0.0, "min_ms": 0.0, "max_ms": 500.0},
    },
    {
        "id": "retakes",
        "type": "retakes.cull",
        "needs": ["vad", "transcribe"],
        "params": {"enabled": True, "strategy": "keep_last"},
    },
    {
        "id": "llm_cleanup",
        "type": "llm.cleanup",
        "needs": ["retakes"],
        "params": {"max_words": 12, "max_cuts": 20},
    },
    {
        "id": "narrative",
        "type": "narrative.beats",
        "needs": ["transcribe", "retakes"],
        "params": {"min_block_words": 80, "max_block_words": 280},
    },
    {
        "id": "timeline",
        "type": "edit.timeline",
        "needs": ["vad", "retakes", "llm_cleanup"],
        "params": {
            "cut_mode": "hard",
            "replace_manual": True,
            "use_transcript_spans": True,
            "remove_fillers": True,
            "detect_repeats": True,
            "max_silence_ms": 450,
            "keep_silence_ms": 220,
        },
    },
    {
        "id": "export_preview",
        "type": "export.nle",
        "needs": ["timeline"],
        "params": {"targets": ["resolve", "kdenlive"]},
    },
    {
        "id": "decoupage_files",
        "type": "human.files",
        "needs": ["export_preview"],
        "params": {
            "gate_id": "decoupage_files",
            "title": "Correções de decupagem (opcional)",
            "description": "Anexe XML/MLT corrigido ou notas de corte.",
            "files": [
                {
                    "id": "edit",
                    "label": "Timeline de referência",
                    "required": False,
                    "accept": [".xml", ".fcpxml", ".kdenlive"],
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
            "title": "Corte aprovado",
            "description": "Confira silêncios, retakes e limites antes de seguir.",
            "artifacts": ["exports/", "project_state.json"],
        },
    },
    {
        "id": "transcript_blocks",
        "type": "transcript.blocks",
        "needs": ["transcribe", "retakes"],
        "params": {},
    },
    {
        "id": "entities_extract",
        "type": "entities.extract",
        "needs": ["transcript_blocks"],
        "params": {},
    },
    {
        "id": "entities_review",
        "type": "human.input",
        "needs": ["entities_extract"],
        "params": {
            "gate_id": "entities_review",
            "title": "Corrigir nomes e entidades",
            "description": "Ajuste grafias e termos antes dos callouts e legendas.",
            "save_as": "hilt/entities.json",
            "questions": [
                {
                    "id": "corrections",
                    "label": "Correções (uma por linha: errado = certo)",
                    "type": "textarea",
                    "required": False,
                }
            ],
        },
    },
    {
        "id": "entities_apply",
        "type": "entities.apply",
        "needs": ["entities_review"],
        "params": {},
    },
    {
        "id": "style_files",
        "type": "human.files",
        "needs": ["entities_apply"],
        "params": {
            "gate_id": "style_files",
            "title": "Referências visuais",
            "description": "Envie boards, paletas, prints ou imagens de referência.",
            "files": [
                {
                    "id": "references",
                    "label": "Referências",
                    "required": False,
                    "accept": [".png", ".jpg", ".jpeg", ".webp", ".pdf"],
                }
            ],
        },
    },
    {
        "id": "style_guide",
        "type": "style.guide",
        "needs": ["style_files", "entities_apply"],
        "params": {"palette_colors": 6},
    },
    {
        "id": "style_review",
        "type": "human.gate",
        "needs": ["style_guide"],
        "params": {
            "gate_id": "style_review",
            "title": "Direção de arte aprovada",
            "artifacts": ["style/style-guide.json"],
        },
    },
    {
        "id": "storyboard",
        "type": "storyboard.plan",
        "needs": ["timeline", "decoupage_review"],
        "params": {},
    },
    {
        "id": "storyboard_units",
        "type": "storyboard.units",
        "needs": ["storyboard", "style_guide"],
        "params": {"target_units": 80},
    },
    {
        "id": "storyboard_preview",
        "type": "storyboard.preview",
        "needs": ["storyboard_units", "style_guide"],
        "params": {"render": True},
    },
    {
        "id": "units_review",
        "type": "human.gate",
        "needs": ["storyboard_preview"],
        "params": {
            "gate_id": "units_review",
            "title": "Storyboard aprovado",
            "artifacts": ["storyboard/units.json", "storyboard/units.md"],
        },
    },
    {
        "id": "vision_ocr",
        "type": "vision.ocr",
        "needs": ["ingest"],
        "params": {"sample_fps": 1.0, "max_frames": 120},
    },
    {
        "id": "vision_segment",
        "type": "vision.segment",
        "needs": ["ingest"],
        "params": {"sample_fps": 0.5, "max_frames": 60},
    },
    {
        "id": "vision_track",
        "type": "vision.track",
        "needs": ["vision_ocr"],
        "params": {"max_tracks": 12},
    },
    {
        "id": "vision_review",
        "type": "human.gate",
        "needs": ["vision_ocr", "vision_segment", "vision_track"],
        "params": {
            "gate_id": "vision_review",
            "title": "Âncoras visuais aprovadas",
            "description": "Confira caixas de OCR, máscaras e tracks antes dos callouts.",
            "artifacts": ["vision/ocr.json", "vision/segments.json", "vision/tracks.json"],
        },
    },
    {
        "id": "composite_matte",
        "type": "composite.matte",
        "needs": ["vision_segment"],
        "params": {},
    },
    {
        "id": "assets_index",
        "type": "assets.index",
        "needs": ["ingest"],
        "params": {},
    },
    {
        "id": "assets_discover",
        "type": "assets.discover",
        "needs": ["storyboard_units", "style_review", "units_review"],
        "params": {
            "providers": ["pexels", "pixabay", "openverse", "wikimedia"],
            "media": "all",
            "allow_external_services": "$allow_external_services",
        },
    },
    {
        "id": "assets_harvest",
        "type": "assets.harvest",
        "needs": ["assets_discover"],
        "params": {"allow_external_services": "$allow_external_services"},
    },
    {
        "id": "assets_license_audit",
        "type": "assets.license_audit",
        "needs": ["assets_harvest"],
        "params": {},
    },
    {
        "id": "assets_review",
        "type": "human.gate",
        "needs": ["assets_license_audit"],
        "params": {
            "gate_id": "assets_review",
            "title": "Mídia e licenças aprovadas",
            "artifacts": ["assets/ledger.json"],
        },
    },
    {
        "id": "assets_assign",
        "type": "assets.assign",
        "needs": ["assets_review", "storyboard_units"],
        "params": {},
    },
    {
        "id": "motion_callout",
        "type": "motion.callout",
        "needs": [
            "storyboard_units",
            "vision_ocr",
            "vision_track",
            "style_review",
        ],
        "params": {"max_callouts": 40},
    },
    {
        "id": "motion_review",
        "type": "human.gate",
        "needs": ["motion_callout"],
        "params": {
            "gate_id": "motion_review",
            "title": "Callouts aprovados",
            "description": "Confira texto, posição e duração dos cartões.",
            "artifacts": ["motion/callouts.json", "motion/callouts/"],
        },
    },
    {
        "id": "motion_attach",
        "type": "motion.attach",
        "needs": ["motion_review", "timeline"],
        "params": {},
    },
    {
        "id": "titles",
        "type": "titles.plan",
        "needs": ["timeline"],
        "params": {},
    },
    {
        "id": "captions",
        "type": "captions.plan",
        "needs": ["titles", "transcribe"],
        "params": {"max_chars": 42},
    },
    {
        "id": "color",
        "type": "color.grade",
        "needs": ["ingest"],
        "params": {},
    },
    {
        "id": "audio_master",
        "type": "audio.master",
        "needs": ["ingest"],
        "params": {"target_lufs": -14.0},
    },
    {
        "id": "audio_compose",
        "type": "audio.compose",
        "needs": ["ingest", "style_review"],
        "params": {"stems": True},
    },
    {
        "id": "sfx_synthesize",
        "type": "sfx.synthesize",
        "needs": ["timeline", "style_review"],
        "params": {"use_scenes": True},
    },
    {
        "id": "audio_mix",
        "type": "audio.mix",
        "needs": ["audio_master", "audio_compose", "sfx_synthesize"],
        "params": {"music_gain": 0.20, "duck_music": True, "target_lufs": -14.0},
    },
    {
        "id": "audio_qa",
        "type": "audio.qa",
        "needs": ["audio_mix"],
        "params": {"target_lufs": -14.0},
    },
    {
        "id": "export_video",
        "type": "export.video",
        "needs": ["timeline", "motion_attach", "color", "titles", "captions", "audio_mix"],
        "params": {"audio_source": "mix", "preset": "fast"},
    },
    {
        "id": "export_nle",
        "type": "export.nle",
        "needs": ["timeline", "titles", "motion_attach", "color", "audio_mix"],
        "params": {
            "targets": ["resolve", "premiere", "kdenlive", "edl"],
        },
    },
    {
        "id": "nle_qa",
        "type": "nle.qa",
        "needs": ["export_nle"],
        "params": {},
    },
    {
        "id": "qa_frames",
        "type": "qa.frames",
        "needs": ["export_video"],
        "params": {"sample_fps": 1.0, "max_frames": 100},
    },
    {
        "id": "qa_vision",
        "type": "qa.vision",
        "needs": ["qa_frames", "audio_qa"],
        "params": {"min_score": 0.75},
    },
    {
        "id": "qa_repair",
        "type": "qa.repair",
        "needs": ["qa_vision"],
        "params": {},
    },
    {
        "id": "qa_review",
        "type": "human.gate",
        "needs": ["qa_vision", "qa_repair"],
        "params": {
            "gate_id": "qa_review",
            "title": "QA aprovado",
            "artifacts": ["qa/vision-report.md", "qa/repair-plan.md"],
        },
    },
    {
        "id": "final_review",
        "type": "human.gate",
        "needs": ["qa_review", "nle_qa", "assets_license_audit"],
        "params": {
            "gate_id": "final_review",
            "title": "Entrega aprovada",
            "description": "Aprovação humana final do MP4, NLE e licenças.",
            "artifacts": ["exports/", "audio/qa.json", "qa/vision-report.md"],
        },
    },
    {
        "id": "chapters",
        "type": "chapters.plan",
        "needs": ["transcribe"],
        "params": {},
    },
]

_add_recipe(
    "footage_intelligence_edit",
    "Footage Intelligence Edit",
    _STEPS,
    description=(
        "Pós-produção autônoma de footage real: decupagem por transcript, "
        "retakes, storyboard, OCR/segmentação/tracking, callouts ancorados, "
        "mídia licenciada, legendas, mix com ducking/LUFS, QA, MP4 e NLE/EDL "
        "com gates humanos."
    ),
    variables={
        "topic": {"type": "string", "default": "", "description": "Recorte editorial."},
        "language": {
            "type": "string",
            "default": "pt",
            "description": "Idioma da transcrição e das legendas.",
        },
        "whisper_model": {
            "type": "string",
            "default": "small",
            "description": "Modelo Faster-Whisper da decupagem.",
        },
        "allow_external_services": {
            "type": "boolean",
            "default": False,
            "description": "Permite busca e download de mídia externa.",
        },
    },
    ui=_ui(),
    llm={"provider": "auto"},
)
