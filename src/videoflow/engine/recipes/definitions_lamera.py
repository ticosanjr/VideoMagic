"""Lamera Video Edit: the full long-form, human-reviewed documentary recipe.

The graph is intentionally grouped by production phase. Each phase has its own
approval or correction checkpoint, and the overloaded research/narrative nodes
are split into one research agent per scope plus separate context-block and
entity-extraction steps.
"""

from __future__ import annotations

from typing import Any

from videoflow.engine.recipes.catalog import _add_recipe


def _ui() -> dict[str, Any]:
    groups = [
        (
            "research",
            "1 · Pesquisa e roteiro",
            (
                "Briefing, quatro agentes de pesquisa, consolidação, perfil do "
                "apresentador e roteiro duplo (narração e edição)."
            ),
            "#38bdf8",
            [
                ["brief", "research_a", "research_b", "research_c"],
                ["research_d", "research_files", "research_review", "research_consolidate"],
                ["research_master_review", "presenter_profile", "presenter_review", "script"],
                ["script_files", "narration_review", "edition_review"],
            ],
        ),
        (
            "decoupage",
            "2 · Decupagem e auditoria",
            (
                "Ingest, calibração com XML de referência, eye-contact, transcrição, "
                "corte de retakes, correção de drift e auditoria humana do corte."
            ),
            "#f59e0b",
            [
                ["ingest", "baseline_files", "decoupage_calibrate", "face_contact"],
                ["vad", "transcribe", "retakes", "drift"],
                ["timeline", "export_preview", "decoupage_files", "decoupage_review"],
            ],
        ),
        (
            "speech",
            "3 · Fala e entidades",
            (
                "Blocos contextuais, extração de pessoas/objetos/métricas, "
                "correções fonéticas e aprovação do manifesto."
            ),
            "#22c55e",
            [
                ["transcript_blocks", "entities_extract", "entities_review"],
                ["entities_apply", "entities_gate"],
            ],
        ),
        (
            "art",
            "4 · Direção de arte e unidades",
            (
                "Referências visuais, style guide, storyboard de unidades, "
                "previews de placeholder e trava de direção de arte."
            ),
            "#ec4899",
            [
                ["style_files", "style_guide", "style_review"],
                ["storyboard", "storyboard_units", "storyboard_preview"],
                ["units_review"],
            ],
        ),
        (
            "production",
            "5 · Mídia, movimento e áudio",
            (
                "Descoberta e licenças de mídia, atribuição de assets, cenas de "
                "movimento, música/Foley, mix, QA de áudio e intro de retenção."
            ),
            "#06b6d4",
            [
                ["assets_index", "assets_discover", "assets_harvest", "assets_license_audit"],
                ["assets_review", "assets_assign", "motion_codegen", "motion_render"],
                ["audio_master", "audio_compose", "sfx_synthesize", "audio_mix"],
                ["audio_qa", "intro_compile", "intro_review"],
            ],
        ),
        (
            "delivery",
            "6 · Validação e entrega",
            (
                "Homologação de amostras, fact-check, reparo de voz, aprovação "
                "final, XML do Premiere/Resolve/Kdenlive, QA e export de vídeo."
            ),
            "#fb7185",
            [
                ["sample_review", "factcheck_audit", "factcheck_review", "voice_files"],
                ["voice_patch", "voice_review", "final_review", "export"],
                ["nle_qa", "video_export", "chapters"],
            ],
        ),
    ]
    nodes: dict[str, dict[str, Any]] = {}
    layout_groups: list[dict[str, Any]] = []
    y = 80.0
    for group_id, label, description, color, rows in groups:
        columns = max(len(row) for row in rows)
        width = columns * 460.0 + 80.0
        height = len(rows) * 160.0 + 120.0
        members: list[str] = []
        for row_index, row in enumerate(rows):
            for column, node_id in enumerate(row):
                nodes[node_id] = {
                    "x": 80.0 + column * 460.0,
                    "y": y + 80.0 + row_index * 160.0,
                    "expanded": False,
                    "pinned": False,
                    "width": 420,
                }
                members.append(node_id)
        layout_groups.append(
            {
                "id": group_id,
                "label": label,
                "description": description,
                "color": color,
                "x": 80.0,
                "y": y,
                "width": width,
                "height": height,
                "nodes": members,
            }
        )
        y += height + 60.0
    return {
        "version": 1,
        "viewport": {"x": 0.0, "y": 0.0, "zoom": 1.0},
        "nodes": nodes,
        "groups": layout_groups,
    }


_STEPS: list[dict[str, Any]] = [
    {
        "id": "brief",
        "type": "human.input",
        "params": {
            "gate_id": "brief",
            "title": "Briefing editorial",
            "description": (
                "Defina o tema, o recorte temporal, a voz do apresentador, a "
                "direção visual/áudio e a duração antes da pesquisa."
            ),
            "save_as": "hilt/brief.json",
            "questions": [
                {
                    "id": "topic",
                    "label": "Tema ou diretriz",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "Ex.: história dos escândalos de um partido",
                },
                {
                    "id": "temporal_scope",
                    "label": "Recorte temporal e temático",
                    "type": "textarea",
                    "required": True,
                    "placeholder": "Ano inicial, ano final, pessoas, regiões, exclusões",
                },
                {
                    "id": "presenter_profile",
                    "label": "Perfil de fala do apresentador",
                    "type": "textarea",
                    "required": False,
                    "help": "Vocabulário, cadência e características da voz.",
                },
                {
                    "id": "presenter_samples",
                    "label": "Transcrições de amostra do apresentador",
                    "type": "textarea",
                    "required": False,
                    "help": "Um caminho de arquivo por linha; alimenta o presenter.profile.",
                },
                {
                    "id": "visual_style",
                    "label": "Direção visual",
                    "type": "textarea",
                    "required": False,
                    "help": "Paleta, tipografia, texturas, referências e enquadramento.",
                },
                {
                    "id": "audio_direction",
                    "label": "Direção de áudio",
                    "type": "textarea",
                    "required": False,
                    "help": "Música, Foley, intensidade e tratamentos de frequência.",
                },
                {
                    "id": "target_duration",
                    "label": "Duração alvo (minutos)",
                    "type": "number",
                    "required": False,
                    "default": 70,
                },
                {
                    "id": "decoupage_path",
                    "label": "Caminho da decupagem",
                    "type": "choice",
                    "required": False,
                    "default": "approve_auto",
                    "options": ["approve_auto", "manual_xml"],
                    "help": "Aprovar o corte automático ou enviar um XML revisado no gate.",
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
            "scopes": [
                "serious crimes, homicides, investigations, court cases, and convictions"
            ],
            "allow_external_services": "$allow_external_services",
            "max_results": 6,
            "fetch_pages": 3,
            "max_cases": 60,
        },
    },
    {
        "id": "research_b",
        "type": "research.multi_agent",
        "needs": ["brief"],
        "params": {
            "topic": "$topic",
            "scopes": ["corruption cases from 1980 to 2010"],
            "allow_external_services": "$allow_external_services",
            "max_results": 6,
            "fetch_pages": 3,
            "max_cases": 60,
        },
    },
    {
        "id": "research_c",
        "type": "research.multi_agent",
        "needs": ["brief"],
        "params": {
            "topic": "$topic",
            "scopes": ["Dilma Rousseff administration up to 2018"],
            "allow_external_services": "$allow_external_services",
            "max_results": 6,
            "fetch_pages": 3,
            "max_cases": 60,
        },
    },
    {
        "id": "research_d",
        "type": "research.multi_agent",
        "needs": ["brief"],
        "params": {
            "topic": "$topic",
            "scopes": ["2018 to the present day"],
            "allow_external_services": "$allow_external_services",
            "max_results": 6,
            "fetch_pages": 3,
            "max_cases": 60,
        },
    },
    {
        "id": "research_files",
        "type": "human.files",
        "needs": ["research_a", "research_b", "research_c", "research_d"],
        "params": {
            "gate_id": "research_files",
            "title": "Revisar pesquisa (opcional)",
            "description": (
                "Revise os dossiês. Envie Markdown corrigido ou adicional; "
                "envie sem arquivos para continuar com o que foi gerado."
            ),
            "files": [
                {
                    "id": "agent_a",
                    "label": "Agent A revisado",
                    "required": False,
                    "accept": [".md", ".txt", ".json"],
                    "target": "research/revised/agent-a.md",
                },
                {
                    "id": "agent_b",
                    "label": "Agent B revisado",
                    "required": False,
                    "accept": [".md", ".txt", ".json"],
                    "target": "research/revised/agent-b.md",
                },
                {
                    "id": "agent_c",
                    "label": "Agent C revisado",
                    "required": False,
                    "accept": [".md", ".txt", ".json"],
                    "target": "research/revised/agent-c.md",
                },
                {
                    "id": "agent_d",
                    "label": "Agent D revisado",
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
            "title": "Revisão da pesquisa",
            "description": "Aprove os dossiês e suas citações antes da consolidação.",
            "artifacts": ["research/"],
        },
    },
    {
        "id": "research_consolidate",
        "type": "research.consolidate",
        "needs": ["research_review"],
        "params": {"max_cases": 300, "require_sources": True},
    },
    {
        "id": "research_master_review",
        "type": "human.gate",
        "needs": ["research_consolidate"],
        "params": {
            "gate_id": "research_master_review",
            "title": "Revisão do dossiê mestre",
            "description": "Aprove o dossiê consolidado antes do roteiro.",
            "artifacts": ["research/master.md", "research/master.json"],
        },
    },
    {
        "id": "presenter_profile",
        "type": "presenter.profile",
        "needs": ["brief"],
        "params": {"paths": ["$presenter_samples"], "max_chars": 500000},
    },
    {
        "id": "presenter_review",
        "type": "human.gate",
        "needs": ["presenter_profile"],
        "params": {
            "gate_id": "presenter_review",
            "title": "Perfil do apresentador",
            "description": "Aprove vocabulário e cadência antes de gerar o roteiro.",
            "artifacts": [
                "research/presenter-profile.json",
                "research/presenter-profile.md",
            ],
        },
    },
    {
        "id": "script",
        "type": "script.dual_output",
        "needs": ["research_master_review", "presenter_review"],
        "params": {
            "target_words": 11000,
            "max_sections": 314,
            "max_cases_per_call": 8,
            "language": "pt",
        },
    },
    {
        "id": "script_files",
        "type": "human.files",
        "needs": ["script"],
        "params": {
            "gate_id": "script_files",
            "title": "Revisar o roteiro duplo (opcional)",
            "description": (
                "Envie uma narração ou edição revisada; envie sem arquivos para "
                "revisar o que foi gerado."
            ),
            "files": [
                {
                    "id": "narration",
                    "label": "Narração revisada",
                    "required": False,
                    "accept": [".txt", ".md"],
                    "target": "script/narration.txt",
                },
                {
                    "id": "edition",
                    "label": "Edição revisada",
                    "required": False,
                    "accept": [".md", ".txt"],
                    "target": "script/edition.md",
                },
            ],
        },
    },
    {
        "id": "narration_review",
        "type": "human.gate",
        "needs": ["script_files"],
        "params": {
            "gate_id": "narration_review",
            "title": "Narração aprovada",
            "description": "Aprove o texto que irá para o estúdio de voz.",
            "artifacts": ["script/narration.txt", "script/script.json"],
        },
    },
    {
        "id": "edition_review",
        "type": "human.gate",
        "needs": ["script_files"],
        "params": {
            "gate_id": "edition_review",
            "title": "Edição aprovada",
            "description": "Aprove o mapa visual, animações e instruções por seção.",
            "artifacts": ["script/edition.md", "script/script.json"],
        },
    },
    {
        "id": "ingest",
        "type": "ingest",
        "needs": ["narration_review", "edition_review"],
        "params": {"extract_pcm": True},
    },
    {
        "id": "baseline_files",
        "type": "human.files",
        "needs": ["ingest"],
        "params": {
            "gate_id": "baseline_files",
            "title": "Decupagem de referência (opcional)",
            "description": (
                "Envie um XMEML/FCPXML editado no Premiere para calibrar o "
                "decoupage. Envie sem arquivo para usar os defaults."
            ),
            "files": [
                {
                    "id": "baseline",
                    "label": "XML de referência",
                    "required": False,
                    "accept": [".xml", ".fcpxml"],
                    "target": "decoupage/baseline.xml",
                }
            ],
        },
    },
    {
        "id": "decoupage_calibrate",
        "type": "decoupage.calibrate",
        "needs": ["ingest", "baseline_files"],
        "params": {
            "baseline_path": "decoupage/baseline.xml",
            "use_current_timeline": False,
        },
    },
    {
        "id": "face_contact",
        "type": "vision.face_contact",
        "needs": ["ingest"],
        "params": {
            "sample_fps": 1.0,
            "max_frames": 3000,
            "write_markers": True,
        },
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
        "params": {
            "mode": "auto",
            "language": "$language",
            "model_size": "$whisper_model",
        },
    },
    {
        "id": "retakes",
        "type": "retakes.cull",
        "needs": ["vad", "transcribe", "decoupage_calibrate"],
        "params": {"enabled": True, "use_profile": True},
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
            "require_licenses": False,
        },
    },
    {
        "id": "decoupage_files",
        "type": "human.files",
        "needs": ["export_preview"],
        "params": {
            "gate_id": "decoupage_files",
            "title": "XML de decupagem revisado (opcional)",
            "description": (
                "Revise o corte automático. Se corrigiu no NLE, envie o XML "
                "revisado; caso contrário, envie sem arquivo."
            ),
            "files": [
                {
                    "id": "revised_xml",
                    "label": "Timeline XML revisada",
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
            "title": "Auditoria de decupagem",
            "description": (
                "Aprove o corte ou rejeite para revisar. Os clipes com eye-contact "
                "ficam marcados no timeline e no NLE."
            ),
            "artifacts": [
                "exports/",
                "project_state.json",
                "decoupage/",
                "vision/face-contact.json",
            ],
        },
    },
    {
        "id": "transcript_blocks",
        "type": "transcript.blocks",
        "needs": ["transcribe", "retakes"],
        "params": {
            "min_block_words": 100,
            "max_block_words": 300,
            "max_blocks": 300,
        },
    },
    {
        "id": "entities_extract",
        "type": "entities.extract",
        "needs": ["transcript_blocks", "edition_review"],
        "params": {
            "blocks_path": "narrative/blocks.json",
            "script_path": "script/edition.md",
            "max_entities": 300,
            "language": "$language",
        },
    },
    {
        "id": "entities_review",
        "type": "human.input",
        "needs": ["entities_extract"],
        "params": {
            "gate_id": "entities_review",
            "title": "Correções de entidades",
            "description": (
                "Corrija nomes fonéticos, locais, objetos e métricas antes da "
                "direção de arte e dos assets."
            ),
            "save_as": "entities/corrections.json",
            "questions": [
                {
                    "id": "people_corrections",
                    "label": "Nomes e fonética",
                    "type": "textarea",
                    "required": False,
                    "help": "Uma correção por linha: ouvido -> canônico.",
                },
                {
                    "id": "visual_corrections",
                    "label": "Objetos, locais e eventos",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "metric_corrections",
                    "label": "Números, datas e percentuais",
                    "type": "textarea",
                    "required": False,
                },
            ],
        },
    },
    {
        "id": "entities_apply",
        "type": "entities.apply",
        "needs": ["entities_review"],
        "params": {
            "corrections_path": "entities/corrections.json",
            "narrative_path": "narrative/entities.json",
        },
    },
    {
        "id": "entities_gate",
        "type": "human.gate",
        "needs": ["entities_apply"],
        "params": {
            "gate_id": "entities_gate",
            "title": "Manifesto de entidades",
            "description": "Aprove o manifesto corrigido antes das unidades visuais.",
            "artifacts": [
                "narrative/entities-corrected.json",
                "narrative/entities-corrected.md",
            ],
        },
    },
    {
        "id": "style_files",
        "type": "human.files",
        "needs": ["brief"],
        "params": {
            "gate_id": "style_files",
            "title": "Referências de direção de arte",
            "description": (
                "Envie pranchas, referências ou uma nota de estilo. O style guide "
                "registra paleta, tipografia, textura e direção de áudio."
            ),
            "files": [
                {
                    "id": "reference",
                    "label": "Prancha ou nota de estilo",
                    "required": False,
                    "accept": [".png", ".jpg", ".jpeg", ".webp", ".pdf", ".md", ".txt"],
                    "target": "style/references/",
                }
            ],
        },
    },
    {
        "id": "style_guide",
        "type": "style.guide",
        "needs": ["style_files", "entities_apply"],
        "params": {
            "directive": "$visual_style",
            "theme": "dark",
            "palette_colors": 6,
        },
    },
    {
        "id": "style_review",
        "type": "human.gate",
        "needs": ["style_guide"],
        "params": {
            "gate_id": "style_review",
            "title": "Trava de direção de arte",
            "description": "Aprove paleta, tipografia, textura e áudio antes dos assets.",
            "artifacts": [
                "style/style-guide.md",
                "style/style-guide.json",
                "narrative/entities-corrected.json",
            ],
        },
    },
    {
        "id": "storyboard",
        "type": "storyboard.plan",
        "needs": ["timeline", "edition_review"],
        "params": {},
    },
    {
        "id": "storyboard_units",
        "type": "storyboard.units",
        "needs": ["storyboard", "style_guide"],
        "params": {"max_units": 400, "max_unit_seconds": 45},
    },
    {
        "id": "storyboard_preview",
        "type": "storyboard.preview",
        "needs": ["storyboard_units", "style_guide"],
        "params": {
            "duration_sec": 60,
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "render": True,
        },
    },
    {
        "id": "units_review",
        "type": "human.gate",
        "needs": ["storyboard_preview"],
        "params": {
            "gate_id": "units_review",
            "title": "Unidades e placeholders",
            "description": (
                "Revise os quatro previews, a composição e os placeholders antes "
                "de baixar mídia externa."
            ),
            "artifacts": [
                "storyboard/units.json",
                "storyboard/units.md",
                "storyboard/previews.json",
                "exports/previews/",
            ],
        },
    },
    {
        "id": "assets_index",
        "type": "assets.index",
        "needs": ["ingest"],
        "params": {"asset_dir": "$assets_dir"},
    },
    {
        "id": "assets_discover",
        "type": "assets.discover",
        "needs": ["storyboard_units", "style_guide", "units_review"],
        "params": {
            "providers": [
                "pexels",
                "pixabay",
                "openverse",
                "wikimedia",
                "internet_archive",
                "youtube",
            ],
            "media": "all",
            "max_units": 80,
            "max_per_unit": 2,
            "allow_external_services": "$allow_external_services",
        },
    },
    {
        "id": "assets_harvest",
        "type": "assets.harvest",
        "needs": ["assets_discover"],
        "params": {
            "max_assets": 225,
            "clip_seconds": 15,
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
            "title": "Revisão de licenças",
            "description": (
                "Aprove os assets coletados. Excerpts de YouTube em fair use e "
                "itens CC precisam ser revisados aqui antes do export final."
            ),
            "artifacts": [
                "assets/licenses.json",
                "assets/licenses.md",
                "assets/manifest.json",
                "assets/candidates.json",
            ],
        },
    },
    {
        "id": "assets_assign",
        "type": "assets.assign",
        "needs": ["assets_review", "storyboard_units"],
        "params": {},
    },
    {
        "id": "motion_codegen",
        "type": "motion.codegen",
        "needs": ["assets_assign", "style_guide"],
        "params": {"width": 1920, "height": 1080, "fps": 30, "max_scenes": 400},
    },
    {
        "id": "motion_render",
        "type": "motion.render",
        "needs": ["motion_codegen"],
        "params": {
            "engine": "ffmpeg",
            "render": True,
            "max_scenes": 400,
            "draft_scale": 1.0,
        },
    },
    {
        "id": "audio_master",
        "type": "audio.master",
        "needs": ["ingest"],
        "params": {},
    },
    {
        "id": "audio_compose",
        "type": "audio.compose",
        "needs": ["ingest"],
        "params": {"bpm": 90, "root_midi": 45, "seed": 7, "stems": True},
    },
    {
        "id": "sfx_synthesize",
        "type": "sfx.synthesize",
        "needs": ["motion_render"],
        "params": {"max_cues": 120, "use_scenes": True},
    },
    {
        "id": "audio_mix",
        "type": "audio.mix",
        "needs": ["audio_master", "audio_compose", "sfx_synthesize"],
        "params": {
            "music_gain": 0.22,
            "sfx_gain": 0.55,
            "sfx_notch_hz": 3500.0,
            "sfx_notch_db": -4.0,
        },
    },
    {
        "id": "audio_qa",
        "type": "audio.qa",
        "needs": ["audio_mix"],
        "params": {},
    },
    {
        "id": "intro_compile",
        "type": "intro.compile",
        "needs": ["assets_assign", "motion_render"],
        "params": {
            "duration_sec": "$intro_duration",
            "clip_seconds": 1.0,
            "max_assets": "$intro_assets",
            "title": "$topic",
        },
    },
    {
        "id": "intro_review",
        "type": "human.gate",
        "needs": ["intro_compile"],
        "params": {
            "gate_id": "intro_review",
            "title": "Intro de retenção",
            "description": "Aprove o corte rápido e a densidade da intro.",
            "artifacts": ["motion/intro.json", "motion/intro.mp4"],
        },
    },
    {
        "id": "sample_review",
        "type": "human.gate",
        "needs": [
            "decoupage_review",
            "style_review",
            "units_review",
            "assets_assign",
            "motion_render",
            "intro_review",
            "audio_qa",
        ],
        "params": {
            "gate_id": "sample_review",
            "title": "Homologação de amostras",
            "description": (
                "Revise previews, B-roll, áudio e storyboard. Feedback no comentário "
                "é registrado com a aprovação."
            ),
            "artifacts": [
                "exports/",
                "exports/previews/",
                "assets/assignments.json",
                "assets/licenses.json",
                "motion/render-manifest.json",
                "motion/intro.json",
                "motion/intro.mp4",
                "audio/qa.json",
                "storyboard/units.json",
                "storyboard/previews.json",
                "style/",
            ],
        },
    },
    {
        "id": "factcheck_audit",
        "type": "factcheck.audit",
        "needs": ["sample_review", "narration_review", "edition_review"],
        "params": {"max_claims": 120},
    },
    {
        "id": "factcheck_review",
        "type": "human.input",
        "needs": ["factcheck_audit"],
        "params": {
            "gate_id": "factcheck",
            "title": "Fact-check e reparo",
            "description": (
                "Audite fatos e atribuições. Informe o trecho a reparar e o texto "
                "de voz ou envie um clipe no gate seguinte."
            ),
            "save_as": "factcheck/review.json",
            "questions": [
                {
                    "id": "facts_ok",
                    "label": "Fatos e atribuições corretos?",
                    "type": "boolean",
                    "required": True,
                },
                {
                    "id": "corrections",
                    "label": "Correções e observações",
                    "type": "textarea",
                    "required": False,
                },
                {
                    "id": "patch_start_sec",
                    "label": "Início do reparo (segundos)",
                    "type": "number",
                    "required": False,
                },
                {
                    "id": "patch_end_sec",
                    "label": "Fim do reparo (segundos)",
                    "type": "number",
                    "required": False,
                },
                {
                    "id": "voice_text",
                    "label": "Texto para TTS (opcional)",
                    "type": "textarea",
                    "required": False,
                },
            ],
        },
    },
    {
        "id": "voice_files",
        "type": "human.files",
        "needs": ["factcheck_review"],
        "params": {
            "gate_id": "voice_files",
            "title": "Clipe de reparo de voz (opcional)",
            "description": (
                "Envie um clipe substituto para a linha corrigida; se não enviar, "
                "o caminho TTS é usado."
            ),
            "files": [
                {
                    "id": "patch",
                    "label": "Clipe de voz substituto",
                    "required": False,
                    "accept": [".wav", ".mp3", ".m4a", ".aac", ".flac"],
                    "target": "audio/voice-patch.wav",
                }
            ],
        },
    },
    {
        "id": "voice_patch",
        "type": "voice.patch",
        "needs": ["voice_files", "audio_mix"],
        "params": {
            "patch_path": "audio/voice-patch.wav",
            "allow_tts": True,
        },
    },
    {
        "id": "voice_review",
        "type": "human.gate",
        "needs": ["voice_patch"],
        "params": {
            "gate_id": "voice_review",
            "title": "Reparo de voz aprovado",
            "description": "Aprove o áudio reparado e a transição com o master.",
            "artifacts": ["audio/final-repaired.wav", "audio/qa.json"],
        },
    },
    {
        "id": "final_review",
        "type": "human.gate",
        "needs": ["factcheck_review", "voice_review", "sample_review"],
        "params": {
            "gate_id": "final_review",
            "title": "Aprovação final",
            "description": "Aprove a montagem final e o pacote de entrega.",
            "artifacts": [
                "exports/",
                "assets/licenses.json",
                "assets/assignments.json",
                "audio/qa.json",
                "audio/final-repaired.wav",
                "factcheck/",
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
            "require_licenses": True,
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
]


_add_recipe(
    "lamera_video_edit",
    "Lamera Video Edit",
    _STEPS,
    description=(
        "Long-form documentary pipeline with four scoped research agents, a "
        "presenter-matched dual script, human decoupage and entity audits, art "
        "direction, placeholder previews, licensed media, motion and Foley, "
        "fact-check/voice repair, and a final NLE timeline."
    ),
    variables={
        "topic": {
            "type": "string",
            "default": "",
            "description": "Research directive; the brief answer is used when empty.",
        },
        "temporal_scope": {
            "type": "string",
            "default": "",
            "description": "Temporal and thematic boundaries for research.",
        },
        "presenter_samples": {
            "type": "string",
            "default": "",
            "description": "Optional transcript path(s) for the presenter profile.",
        },
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
        "allow_external_services": {
            "type": "boolean",
            "default": False,
            "description": "Allow external search and stock providers.",
        },
        "visual_style": {
            "type": "string",
            "default": "",
            "description": "Visual direction for the style guide.",
        },
        "audio_direction": {
            "type": "string",
            "default": "",
            "description": "Audio direction; recorded for the review gates.",
        },
        "target_words": {
            "type": "number",
            "default": 11000,
            "description": "Target narration length in words.",
        },
        "max_sections": {
            "type": "number",
            "default": 314,
            "description": "Maximum edition-script sections.",
        },
        "whisper_model": {
            "type": "string",
            "default": "small",
            "description": "Faster-Whisper model size for the decoupage pass.",
        },
        "language": {
            "type": "string",
            "default": "pt",
            "description": "Research, script, and transcription language.",
        },
        "intro_duration": {
            "type": "number",
            "default": 112,
            "description": "High-retention intro duration in seconds.",
        },
        "intro_assets": {
            "type": "number",
            "default": 120,
            "description": "Maximum assets used in the intro.",
        },
    },
    ui=_ui(),
    llm={"provider": "auto"},
)
