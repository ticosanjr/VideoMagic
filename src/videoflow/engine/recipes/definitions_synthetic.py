"""Synthetic Code Studio: script-first, code-rendered video with human gates."""

from __future__ import annotations

from typing import Any

from videoflow.engine.recipes.catalog import _add_recipe
from videoflow.engine.recipes.ui_layout import build_ui


def _ui() -> dict[str, Any]:
    return build_ui(
        [
            (
                "brief",
                "1 · Briefing, pesquisa e roteiro",
                (
                    "Direção criativa, pesquisa, voz do apresentador, roteiro e "
                    "fact-check antes de gastar tempo com áudio ou render."
                ),
                "#38bdf8",
                [
                    ["brief", "research_a", "research_b"],
                    ["research_files", "research_review", "research_consolidate"],
                    ["research_master_review", "presenter_profile", "presenter_review"],
                    ["script", "script_files", "factcheck_audit", "script_review"],
                ],
            ),
            (
                "voice",
                "2 · Voz e timing",
                (
                    "Síntese da narração, alinhamento por palavra e aprovação da "
                    "amostra de voz antes do storyboard temporal."
                ),
                "#a78bfa",
                [
                    ["narration_synthesize", "narration_align", "voice_review"],
                ],
            ),
            (
                "art",
                "3 · Direção de arte e storyboard",
                (
                    "Style guide, units temporizados, previews de composição e "
                    "aprovação do plano visual."
                ),
                "#ec4899",
                [
                    ["style_files", "style_guide", "style_review"],
                    ["storyboard_timed", "storyboard_preview", "units_review"],
                ],
            ),
            (
                "media",
                "4 · Mídia e cenas",
                (
                    "Busca de mídia licenciada, atribuição, codegen HTML/CSS/3D e "
                    "render headless com fallback FFmpeg."
                ),
                "#06b6d4",
                [
                    ["assets_discover", "assets_harvest", "assets_license_audit"],
                    ["assets_review", "assets_assign", "scene_codegen"],
                    ["scene_render", "scene_review"],
                ],
            ),
            (
                "audio",
                "5 · Áudio programático",
                (
                    "Trilha procedural, Foley por cena, ducking, mix final e "
                    "normalização de loudness."
                ),
                "#f59e0b",
                [
                    ["audio_compose", "sfx_synthesize", "audio_mix", "audio_qa"],
                ],
            ),
            (
                "delivery",
                "6 · QA, correção e entrega",
                (
                    "Legendas, montagem do draft, QA de frames e transcript, "
                    "reparo assistido, aprovação final e master MP4."
                ),
                "#fb7185",
                [
                    ["captions", "scene_assemble", "qa_frames"],
                    ["qa_transcript", "qa_vision", "qa_repair"],
                    ["qa_review", "export_master", "final_review"],
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
            "title": "Briefing do vídeo sintético",
            "summary": (
                "Defina o tema, o recorte, a voz e a regra de não mostrar "
                "rosto antes da pesquisa."
            ),
            "checklist": [
                "Tema e recorte claros",
                "Duração e formato definidos",
                "Perfil de voz ou TTS escolhido",
                "Regra de rosto documentada",
            ],
            "next_step": "Pesquisa e roteiro",
            "severity": "warning",
            "group": "brief",
            "description": (
                "Defina tema, recorte, voz, duração, formato e a regra de não "
                "mostrar rosto humano. O roteiro só começa depois desta direção."
            ),
            "save_as": "hilt/brief.json",
            "questions": [
                {
                    "id": "topic",
                    "label": "Tema e diretriz",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "Ex.: como funciona o protocolo HTTP/3",
                },
                {
                    "id": "temporal_scope",
                    "label": "Recorte e exclusões",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "target_duration",
                    "label": "Duração alvo (min)",
                    "type": "number",
                    "required": False,
                },
                {
                    "id": "aspect",
                    "label": "Formato",
                    "type": "select",
                    "required": False,
                    "options": ["16:9", "9:16", "1:1"],
                },
                {
                    "id": "language",
                    "label": "Idioma",
                    "type": "text",
                    "required": False,
                    "placeholder": "pt",
                },
                {
                    "id": "voice_profile_id",
                    "label": "ID do perfil de voz (opcional)",
                    "type": "text",
                    "required": False,
                    "help": (
                        "Crie o perfil em Setup → AI providers ou deixe vazio "
                        "para o TTS padrão."
                    ),
                },
                {
                    "id": "narration_file",
                    "label": "Narração pronta (opcional)",
                    "type": "text",
                    "required": False,
                    "help": (
                        "Caminho local de um WAV/MP3 narrado; quando preenchido, "
                        "o TTS não é chamado."
                    ),
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
                    "id": "no_face",
                    "label": "Sem rosto humano em cena",
                    "type": "boolean",
                    "required": False,
                },
            ],
        },
    },
    {
        "id": "research_a",
        "type": "research.multi_agent",
        "needs": ["brief"],
        "params": {
            "topic": "$topic",
            "scopes": ["fundamentos, definições e documentação oficial"],
            "allow_external_services": "$allow_external_services",
            "max_results": 5,
            "fetch_pages": 2,
            "max_cases": 40,
        },
    },
    {
        "id": "research_b",
        "type": "research.multi_agent",
        "needs": ["brief"],
        "params": {
            "topic": "$topic",
            "scopes": ["exemplos práticos, comparações e erros comuns"],
            "allow_external_services": "$allow_external_services",
            "max_results": 5,
            "fetch_pages": 2,
            "max_cases": 40,
        },
    },
    {
        "id": "research_files",
        "type": "human.files",
        "needs": ["research_a", "research_b"],
        "params": {
            "gate_id": "research_files",
            "title": "Fontes adicionais (opcional)",
            "description": "Anexe PDFs, páginas ou notas que a pesquisa deve respeitar.",
            "files": [
                {
                    "id": "sources",
                    "label": "Fontes de referência",
                    "required": False,
                    "accept": [".pdf", ".md", ".txt", ".html"],
                }
            ],
        },
    },
    {
        "id": "research_review",
        "type": "human.gate",
        "needs": ["research_files"],
        "params": {
            "gate_id": "research_review",
            "title": "Pesquisa aprovada",
            "description": "Revise os dossiês e remova fontes fracas ou fora do recorte.",
            "artifacts": ["research/agents.json"],
        },
    },
    {
        "id": "research_consolidate",
        "type": "research.consolidate",
        "needs": ["research_review"],
        "params": {"language": "$language"},
    },
    {
        "id": "research_master_review",
        "type": "human.gate",
        "needs": ["research_consolidate"],
        "params": {
            "gate_id": "research_master_review",
            "title": "Dossiê mestre aprovado",
            "description": "Aprove o dossiê que vai sustentar o roteiro e o fact-check.",
            "artifacts": ["research/master.json", "research/master.md"],
        },
    },
    {
        "id": "presenter_profile",
        "type": "presenter.profile",
        "needs": ["brief"],
        "params": {"max_chars": 12000},
    },
    {
        "id": "presenter_review",
        "type": "human.gate",
        "needs": ["presenter_profile"],
        "params": {
            "gate_id": "presenter_review",
            "title": "Voz do apresentador aprovada",
            "description": "Confirme vocabulário, cadência e perfil de voz antes do roteiro.",
            "artifacts": ["research/presenter-profile.md"],
        },
    },
    {
        "id": "script",
        "type": "script.dual_output",
        "needs": ["research_master_review", "presenter_review"],
        "params": {"target_words": 1800, "max_sections": 18},
    },
    {
        "id": "script_files",
        "type": "human.files",
        "needs": ["script"],
        "params": {
            "gate_id": "script_files",
            "title": "Revisão do roteiro (opcional)",
            "description": "Anexe um roteiro corrigido ou notas antes do fact-check.",
            "files": [
                {
                    "id": "script",
                    "label": "Roteiro corrigido",
                    "required": False,
                    "accept": [".md", ".txt", ".json"],
                }
            ],
        },
    },
    {
        "id": "factcheck_audit",
        "type": "factcheck.audit",
        "needs": ["script"],
        "params": {"max_claims": 120},
    },
    {
        "id": "script_review",
        "type": "human.gate",
        "needs": ["script_files", "factcheck_audit"],
        "params": {
            "gate_id": "script_review",
            "title": "Roteiro e fatos aprovados",
            "summary": (
                "Corrija o texto agora; depois da narração, mudar palavras "
                "invalida o timing."
            ),
            "checklist": [
                "Fact-check revisado",
                "Narração sem erros factuais",
                "Duração compatível com o alvo",
            ],
            "next_step": "Síntese da narração",
            "severity": "critical",
            "group": "script",
            "description": (
                "Corrija o texto agora. Depois da narração, mudar palavras altera "
                "todos os tempos e invalida o storyboard."
            ),
            "artifacts": [
                "script/script.json",
                "script/narration.txt",
                "factcheck/report.md",
            ],
        },
    },
    {
        "id": "style_files",
        "type": "human.files",
        "needs": ["script_review"],
        "params": {
            "gate_id": "style_files",
            "title": "Referências visuais",
            "description": "Envie boards, prints, paletas ou imagens de referência.",
            "files": [
                {
                    "id": "references",
                    "label": "Referências visuais",
                    "required": False,
                    "accept": [".png", ".jpg", ".jpeg", ".webp", ".pdf"],
                }
            ],
        },
    },
    {
        "id": "style_guide",
        "type": "style.guide",
        "needs": ["style_files", "script_review"],
        "params": {"palette_colors": 6},
    },
    {
        "id": "style_review",
        "type": "human.gate",
        "needs": ["style_guide"],
        "params": {
            "gate_id": "style_review",
            "title": "Direção de arte aprovada",
            "description": "Aprove paleta, tipografia, textura e regras de movimento.",
            "artifacts": ["style/style-guide.json"],
        },
    },
    {
        "id": "narration_synthesize",
        "type": "narration.synthesize",
        "needs": ["script_review", "presenter_review"],
        "params": {"output_path": "audio/narration.wav"},
    },
    {
        "id": "narration_align",
        "type": "narration.align",
        "needs": ["narration_synthesize"],
        "params": {"mode": "auto", "model_size": "$whisper_model"},
    },
    {
        "id": "voice_review",
        "type": "human.gate",
        "needs": ["narration_align"],
        "params": {
            "gate_id": "voice_review",
            "title": "Narração aprovada",
            "description": "Ouça a narração e confira a transcrição antes do storyboard.",
            "artifacts": ["audio/narration.wav", "narration/transcript.json"],
        },
    },
    {
        "id": "storyboard_timed",
        "type": "storyboard.timed",
        "needs": ["narration_align", "script_review"],
        "params": {"target_units": 90, "max_unit_seconds": 12.0},
    },
    {
        "id": "storyboard_preview",
        "type": "storyboard.preview",
        "needs": ["storyboard_timed", "style_guide"],
        "params": {"render": True},
    },
    {
        "id": "units_review",
        "type": "human.gate",
        "needs": ["storyboard_preview"],
        "params": {
            "gate_id": "units_review",
            "title": "Storyboard temporal aprovado",
            "description": "Confira unidades, layouts e previews antes de buscar mídia.",
            "artifacts": ["storyboard/units.json", "storyboard/units.md"],
        },
    },
    {
        "id": "assets_discover",
        "type": "assets.discover",
        "needs": ["storyboard_timed", "style_review", "units_review"],
        "params": {
            "providers": ["pexels", "pixabay", "openverse", "wikimedia"],
            "media": "all",
            "max_per_unit": 4,
            "allow_external_services": "$allow_external_services",
        },
    },
    {
        "id": "assets_harvest",
        "type": "assets.harvest",
        "needs": ["assets_discover"],
        "params": {
            "max_assets": 120,
            "allow_external_services": "$allow_external_services",
        },
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
            "description": "Remova mídia sem licença clara ou fora do tom visual.",
            "artifacts": ["assets/ledger.json", "assets/manifest.json"],
        },
    },
    {
        "id": "assets_assign",
        "type": "assets.assign",
        "needs": ["assets_review", "storyboard_timed"],
        "params": {},
    },
    {
        "id": "scene_codegen",
        "type": "scene.codegen",
        "needs": ["assets_assign", "style_review", "units_review"],
        "params": {"engine": "html", "title_style": "lower_third"},
    },
    {
        "id": "scene_render",
        "type": "scene.render",
        "needs": ["scene_codegen"],
        "params": {"engine": "auto", "draft_scale": 1.0},
    },
    {
        "id": "scene_review",
        "type": "human.gate",
        "needs": ["scene_render"],
        "params": {
            "gate_id": "scene_review",
            "title": "Cenas renderizadas aprovadas",
            "summary": "Confira composição, texto e movimento antes de misturar o áudio final.",
            "checklist": [
                "Nenhum texto cortado",
                "Cenas sem buracos ou quadros vazios",
                "Movimento e transições coerentes",
            ],
            "next_step": "Mix de áudio e montagem",
            "group": "scenes",
            "description": "Confira composição, texto e movimento antes do áudio final.",
            "artifacts": ["motion/render-manifest.json", "motion/scenes.json"],
        },
    },
    {
        "id": "audio_compose",
        "type": "audio.compose",
        "needs": ["narration_align", "style_review"],
        "params": {"stems": True},
    },
    {
        "id": "sfx_synthesize",
        "type": "sfx.synthesize",
        "needs": ["scene_render", "style_review"],
        "params": {"use_scenes": True, "max_cues": 80},
    },
    {
        "id": "audio_mix",
        "type": "audio.mix",
        "needs": ["narration_synthesize", "audio_compose", "sfx_synthesize"],
        "params": {"music_gain": 0.20, "duck_music": True, "target_lufs": -15.5},
    },
    {
        "id": "audio_qa",
        "type": "audio.qa",
        "needs": ["audio_mix"],
        "params": {"target_lufs": -15.5},
    },
    {
        "id": "captions",
        "type": "captions.plan",
        "needs": ["narration_align", "audio_mix"],
        "params": {"max_chars": 42},
    },
    {
        "id": "scene_assemble",
        "type": "scene.assemble",
        "needs": ["scene_review", "audio_mix", "captions"],
        "params": {"output_path": "exports/draft.mp4"},
    },
    {
        "id": "qa_frames",
        "type": "qa.frames",
        "needs": ["scene_assemble"],
        "params": {"sample_fps": 1.0, "max_frames": 80},
    },
    {
        "id": "qa_transcript",
        "type": "qa.transcript",
        "needs": ["scene_assemble", "narration_align"],
        "params": {},
    },
    {
        "id": "qa_vision",
        "type": "qa.vision",
        "needs": ["qa_frames", "qa_transcript", "audio_qa"],
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
        "needs": ["qa_vision", "qa_repair", "audio_qa"],
        "params": {
            "gate_id": "qa_review",
            "title": "QA aprovado",
            "description": "Revise frames, transcript e loudness; aprove ou rejeite o draft.",
            "artifacts": [
                "qa/vision-report.md",
                "qa/repair-plan.md",
                "qa/frames.json",
            ],
        },
    },
    {
        "id": "export_master",
        "type": "export.master",
        "needs": ["qa_review", "scene_assemble"],
        "params": {"filename": "master.mp4"},
    },
    {
        "id": "final_review",
        "type": "human.gate",
        "needs": ["export_master", "assets_license_audit"],
        "params": {
            "gate_id": "final_review",
            "title": "Master aprovado",
            "description": "Aprovação humana final antes da entrega.",
            "artifacts": ["exports/master.mp4", "exports/master.json"],
        },
    },
]

_add_recipe(
    "synthetic_code_studio",
    "Synthetic Code Studio",
    _STEPS,
    description=(
        "Vídeo sintético sem gravação: pesquisa e roteiro revisados, narração "
        "com timestamps de palavra, storyboard temporal, cenas HTML/CSS/3D "
        "renderizadas por navegador headless (fallback FFmpeg), áudio "
        "programático, legendas, QA e master MP4 com gates humanos."
    ),
    variables={
        "topic": {
            "type": "string",
            "default": "",
            "description": "Tema; a resposta do briefing é usada quando vazio.",
        },
        "language": {
            "type": "string",
            "default": "pt",
            "description": "Idioma da pesquisa, roteiro e narração.",
        },
        "whisper_model": {
            "type": "string",
            "default": "small",
            "description": "Modelo Faster-Whisper para alinhar a narração.",
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
