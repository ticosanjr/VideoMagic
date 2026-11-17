"""Canonical style catalog: Markdown files, cache, SQLite index, and workspace sync."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any

import yaml

from videoflow.application.clock import now_iso as _now
from videoflow.application.storage import atomic_write_text
from videoflow.domain.errors import StyleError, StyleNotFoundError
from videoflow.domain.headless import (
    ChannelKit,
    PresetHardConstraints,
    PresetRule,
    PresetRulebook,
    StylePreset,
)
from videoflow.domain.styles import STYLE_ID_RE, StyleDefinition
from videoflow.runtime import portable_home

_CACHE: dict[str, tuple[tuple[object, ...], dict[str, StyleDefinition]]] = {}
_LOCK = threading.RLock()
_LEARNED_HEADINGS = {
    "regras aprendidas",
    "learned rules",
    "regras",
    "rules",
}


def styles_dir() -> Path:
    from videoflow.application.settings import load_settings

    configured = load_settings().presets.style_dir.strip()
    return Path(configured).expanduser() if configured else portable_home() / "styles"


def seed_styles_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "styles"


def rule_id(text: str) -> str:
    return "rule-" + hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()[:12]


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def style_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().casefold()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:80]
    return slug or "style"


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        raise StyleError("style markdown requires YAML frontmatter")
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise StyleError("style markdown frontmatter is not closed")
    raw = parts[1]
    body = parts[2].lstrip("\r\n")
    try:
        payload = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise StyleError(f"invalid style frontmatter: {exc}") from exc
    if not isinstance(payload, dict):
        raise StyleError("style frontmatter must be a mapping")
    return dict(payload), body


def _extract_rules(body: str, frontmatter_rules: Any) -> tuple[list[PresetRule], str]:
    rules: list[PresetRule] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, dict):
            text = str(value.get("text") or value.get("rule") or "").strip()
            weight = float(value.get("weight") or 1.0)
            created = str(value.get("created_at") or "")
        else:
            text = str(value or "").strip()
            weight = 1.0
            created = ""
        if not text:
            return
        key = normal(text)
        if key in seen:
            return
        seen.add(key)
        rules.append(
            PresetRule(
                id=rule_id(text),
                text=text,
                scope="learned",
                source="style_markdown",
                weight=max(0.1, min(5.0, weight)),
                created_at=created,
            )
        )

    for item in frontmatter_rules or []:
        add(item)

    lines = body.splitlines()
    kept: list[str] = []
    in_rules = False
    for line in lines:
        heading = re.match(r"^\s*#{1,6}\s+(.*?)\s*$", line)
        if heading:
            title = heading.group(1).strip().casefold()
            in_rules = title in _LEARNED_HEADINGS
            if not in_rules:
                kept.append(line)
            continue
        if in_rules:
            bullet = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.*?)\s*$", line)
            if bullet:
                add(bullet.group(1))
            continue
        kept.append(line)
    return rules[:15], "\n".join(kept).strip()


def parse_style_markdown(text: str, *, fallback_id: str = "") -> StyleDefinition:
    data, body = _frontmatter(text)
    if fallback_id and not data.get("style_id"):
        data["style_id"] = fallback_id
    rules, cleaned = _extract_rules(body, data.pop("learned_rules", None))
    data["body"] = cleaned
    data["learned_rules"] = [rule.model_dump(mode="json") for rule in rules]
    try:
        style = StyleDefinition.model_validate(data)
    except ValueError as exc:
        raise StyleError(f"invalid style definition: {exc}") from exc
    if not STYLE_ID_RE.fullmatch(style.style_id):
        raise StyleError(f"invalid style_id: {style.style_id!r}")
    return style


def render_style_markdown(style: StyleDefinition) -> str:
    known = {
        "schema_version",
        "version",
        "style_id",
        "name",
        "aspect_ratio",
        "target_lufs",
        "max_static_sec",
        "min_silence_ms",
        "layout_mode",
        "caption_preset",
        "motion_engine",
        "export_targets",
        "palette",
        "fonts",
        "cut_rhythm",
        "safe_zones",
        "learned_rules",
        "updated_at",
    }
    frontmatter: dict[str, Any] = {
        "schema_version": style.schema_version,
        "version": style.version,
        "style_id": style.style_id,
        "name": style.name,
        "aspect_ratio": style.aspect_ratio,
        "target_lufs": style.target_lufs,
        "max_static_sec": style.max_static_sec,
        "min_silence_ms": style.min_silence_ms,
        "layout_mode": style.layout_mode,
        "caption_preset": style.caption_preset,
        "motion_engine": style.motion_engine,
        "export_targets": style.export_targets,
        "palette": style.palette,
        "fonts": style.fonts,
        "cut_rhythm": style.cut_rhythm,
        "safe_zones": style.safe_zones,
        "learned_rules": [rule.model_dump(mode="json") for rule in style.learned_rules[:15]],
        "updated_at": style.updated_at or _now(),
    }
    for key, value in (style.model_extra or {}).items():
        if key not in known:
            frontmatter[key] = value
    body = style.body.strip()
    rule_lines = [f"- {rule.text}" for rule in style.learned_rules[:15]]
    if rule_lines:
        body = (body + "\n\n" if body else "") + "## Regras Aprendidas\n\n" + "\n".join(rule_lines)
    header = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return f"---\n{header}\n---\n\n{body.strip()}\n"


def _read_style(path: Path) -> StyleDefinition:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StyleError(f"cannot read style {path.name}: {exc}") from exc
    return parse_style_markdown(text, fallback_id=path.stem)


def _signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            (path.name, path.stat().st_mtime_ns, path.stat().st_size)
            for path in root.glob("*.md")
            if path.is_file()
        )
    )


def _defaults_for(style: StyleDefinition) -> dict[str, dict[str, Any]]:
    nle_targets = [
        target
        for target in style.export_targets
        if target in {"resolve", "premiere", "kdenlive", "edl"}
    ]
    defaults: dict[str, dict[str, Any]] = {
        "audio.master": {"target_lufs": style.target_lufs},
        "audio.qa": {"target_lufs": style.target_lufs},
        "audio.vad": {"min_silence_ms": style.min_silence_ms},
        "style": {
            "preset": {
                "name": style.name,
                "palette": list(style.palette),
                "typography": {"family": style.fonts[0]} if style.fonts else {},
                "cut_rhythm": dict(style.cut_rhythm),
                "safe_zones": dict(style.safe_zones),
                "source": f"style:{style.style_id}",
            },
            "safe_zones": dict(style.safe_zones),
        },
    }
    if style.caption_preset:
        defaults["captions.plan"] = {"preset": style.caption_preset}
        defaults["shorts.captions"] = {"preset": style.caption_preset}
    if style.layout_mode in {
        "auto",
        "callaway",
        "rounded_window",
        "full_screen",
        "cutout",
    }:
        defaults["layout.cutout"] = {"style": style.layout_mode}
    if style.motion_engine in {"auto", "ffmpeg", "remotion", "hyperframes"}:
        defaults["motion.render"] = {"engine": style.motion_engine}
    if nle_targets:
        defaults["export.nle"] = {"targets": nle_targets}
    if style.export_targets:
        defaults["delivery.package"] = {"targets": list(style.export_targets)}
    return defaults


def rulebook_from_style(style: StyleDefinition) -> PresetRulebook:
    median = style.cut_rhythm.get("median_cut_sec") or style.cut_rhythm.get("max_cut_sec")
    hard = PresetHardConstraints(
        palette=style.palette[0] if style.palette else "",
        cut_rhythm_sec=float(median or 0.0),
        aspect_ratio=style.aspect_ratio,
        caption_preset=style.caption_preset,
    )
    kit = ChannelKit(
        fonts=list(style.fonts),
        palette=list(style.palette),
        caption_preset=style.caption_preset,
        defaults=_defaults_for(style),
    )
    return PresetRulebook(
        channel_id=style.style_id,
        version=style.version,
        learned_rules=list(style.learned_rules),
        hard_constraints=hard,
        channel_kit=kit,
    )


def style_from_rulebook(
    book: PresetRulebook,
    *,
    existing: StyleDefinition | None = None,
    style_id: str | None = None,
) -> StyleDefinition:
    identifier = style_id or book.channel_id or "default"
    base = existing or StyleDefinition(style_id=style_slug(identifier), name=identifier or "Style")
    legacy = book.channel_kit.defaults.get("style")
    legacy_preset: dict[str, Any] = legacy if isinstance(legacy, dict) else {}
    palette = book.channel_kit.palette or [str(item) for item in legacy_preset.get("palette") or []]
    if not palette and book.hard_constraints.palette:
        palette = [book.hard_constraints.palette]
    fonts = book.channel_kit.fonts or []
    typography = legacy_preset.get("typography")
    if not fonts and isinstance(typography, dict) and typography.get("family"):
        fonts = [str(typography["family"])]
    cut_rhythm = dict(base.cut_rhythm)
    if isinstance(legacy_preset.get("cut_rhythm"), dict):
        cut_rhythm.update(legacy_preset["cut_rhythm"])
    if book.hard_constraints.cut_rhythm_sec:
        cut_rhythm.setdefault("median_cut_sec", book.hard_constraints.cut_rhythm_sec)
    safe_zones = base.safe_zones
    if isinstance(legacy_preset.get("safe_zones"), dict):
        safe_zones = dict(legacy_preset["safe_zones"])
    return base.model_copy(
        update={
            "version": book.version,
            "palette": palette,
            "fonts": fonts,
            "aspect_ratio": book.hard_constraints.aspect_ratio or base.aspect_ratio,
            "caption_preset": (
                book.hard_constraints.caption_preset
                or book.channel_kit.caption_preset
                or base.caption_preset
            ),
            "cut_rhythm": cut_rhythm,
            "safe_zones": safe_zones,
            "learned_rules": list(book.learned_rules[:15]),
            "updated_at": _now(),
        }
    )


def to_style_preset(style: StyleDefinition) -> StylePreset:
    return StylePreset(
        name=style.name,
        palette=list(style.palette),
        typography={"family": style.fonts[0]} if style.fonts else {},
        cut_rhythm=dict(style.cut_rhythm),
        safe_zones=dict(style.safe_zones),
        source=f"style:{style.style_id}",
    )


class StyleCatalog:
    """Read and write canonical styles, with seeds and a cached index."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        include_seeds: bool = True,
    ) -> None:
        self.root = Path(root).expanduser() if root is not None else styles_dir()
        self.include_seeds = include_seeds

    def _roots(self) -> list[Path]:
        roots = [self.root]
        if self.include_seeds:
            roots.append(seed_styles_dir())
        return roots

    def _styles(self) -> dict[str, StyleDefinition]:
        key = str(self.root.resolve())
        signature: tuple[object, ...] = tuple(
            (str(root), _signature(root)) for root in self._roots()
        )
        with _LOCK:
            cached = _CACHE.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            styles: dict[str, StyleDefinition] = {}
            for root in reversed(self._roots()):
                for path in sorted(root.glob("*.md")):
                    if not path.is_file():
                        continue
                    try:
                        style = _read_style(path)
                    except StyleError:
                        continue
                    styles[style.style_id] = style
            _CACHE[key] = (signature, styles)
            return styles

    def invalidate(self) -> None:
        with _LOCK:
            _CACHE.pop(str(self.root.resolve()), None)

    def list_styles(self) -> list[StyleDefinition]:
        styles = self._styles()
        return [styles[key] for key in sorted(styles)]

    def path_for(self, style_id: str) -> Path:
        user = self.root / f"{style_id}.md"
        if user.is_file():
            return user
        seed = seed_styles_dir() / f"{style_id}.md"
        return seed if seed.is_file() else user

    def list_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "style_id": style.style_id,
                "name": style.name,
                "aspect_ratio": style.aspect_ratio,
                "summary": style.summary,
                "file_path": str(self.path_for(style.style_id)),
                "updated_at": style.updated_at,
            }
            for style in self.list_styles()
        ]

    def get(self, style_id: str) -> StyleDefinition:
        styles = self._styles()
        style = styles.get(style_id)
        if style is None:
            raise StyleNotFoundError(style_id)
        return style

    def save(self, style: StyleDefinition, *, overwrite: bool = True) -> Path:
        if not STYLE_ID_RE.fullmatch(style.style_id):
            raise StyleError(f"invalid style_id: {style.style_id!r}")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{style.style_id}.md"
        if path.exists() and not overwrite:
            raise StyleError(f"style already exists: {style.style_id}")
        style = style.model_copy(update={"updated_at": style.updated_at or _now()})
        atomic_write_text(path, render_style_markdown(style))
        self._index(style, path)
        self.invalidate()
        return path

    def delete(self, style_id: str) -> bool:
        path = self.root / f"{style_id}.md"
        if not path.is_file():
            return False
        path.unlink()
        try:
            from videoflow.application.database import delete_style

            delete_style(style_id)
        except Exception:  # noqa: BLE001 - index is advisory
            pass
        self.invalidate()
        return True

    def _index(self, style: StyleDefinition, path: Path) -> None:
        try:
            from videoflow.application.database import upsert_style

            upsert_style(style.style_id, {**style.model_dump(mode="json"), "path": str(path)})
        except Exception:  # noqa: BLE001 - filesystem remains source of truth
            pass

    def sync(self, workspace_dir: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
        directory = Path(workspace_dir).expanduser() / "presets"
        directory.mkdir(parents=True, exist_ok=True)
        manifest_path = directory / ".videoflow-styles.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        if not isinstance(manifest, dict):
            manifest = {}
        copied: list[str] = []
        skipped: list[str] = []
        unchanged: list[str] = []
        for style in self.list_styles():
            text = render_style_markdown(style)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            target = directory / f"{style.style_id}.md"
            previous = str((manifest.get(style.style_id) or {}).get("sha256") or "")
            if target.is_file():
                local = hashlib.sha256(target.read_bytes()).hexdigest()
                if local == digest:
                    unchanged.append(style.style_id)
                    manifest[style.style_id] = {
                        "sha256": digest,
                        "updated_at": style.updated_at,
                        "synced_at": _now(),
                    }
                    continue
                if not overwrite and (not previous or local != previous):
                    skipped.append(style.style_id)
                    continue
            atomic_write_text(target, text)
            copied.append(style.style_id)
            manifest[style.style_id] = {
                "sha256": digest,
                "updated_at": style.updated_at,
                "synced_at": _now(),
            }
        atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        return {
            "ok": True,
            "directory": str(directory),
            "copied": copied,
            "skipped": skipped,
            "unchanged": unchanged,
            "manifest": str(manifest_path),
        }

    def learn_rule(
        self,
        style_id: str,
        notes: list[str],
        *,
        mode: str = "merge",
        max_rules: int = 15,
    ) -> StyleDefinition:
        style = self.get(style_id)
        rules = [] if mode == "replace" else list(style.learned_rules)
        existing = {normal(rule.text): rule for rule in rules}
        created = _now()
        for note in notes:
            text = str(note).strip()
            if not text:
                continue
            key = normal(text)
            if key in existing:
                existing[key].weight = min(5.0, existing[key].weight + 0.25)
                continue
            tokens = set(key.split())
            similar = next(
                (
                    rule
                    for rule in rules
                    if tokens
                    and len(tokens & set(normal(rule.text).split()))
                    / max(1, len(tokens | set(normal(rule.text).split())))
                    >= 0.8
                ),
                None,
            )
            if similar is not None:
                similar.text = text
                similar.id = rule_id(text)
                similar.weight = min(5.0, similar.weight + 0.1)
                continue
            rule = PresetRule(
                id=rule_id(text),
                text=text,
                scope="learned",
                source="review_notes",
                created_at=created,
            )
            rules.append(rule)
            existing[key] = rule
        rules.sort(key=lambda rule: (-rule.weight, rule.created_at, rule.id))
        updated = style.model_copy(
            update={
                "learned_rules": rules[: max(1, min(15, int(max_rules)))],
                "updated_at": created,
            }
        )
        self.save(updated)
        return updated

    def rulebook(self, style_id: str) -> PresetRulebook:
        return rulebook_from_style(self.get(style_id))


def catalog() -> StyleCatalog:
    return StyleCatalog()


__all__ = [
    "StyleCatalog",
    "catalog",
    "normal",
    "parse_style_markdown",
    "render_style_markdown",
    "rule_id",
    "rulebook_from_style",
    "seed_styles_dir",
    "style_slug",
    "style_from_rulebook",
    "styles_dir",
    "to_style_preset",
]
