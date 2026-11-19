"""Local font asset store with minimal TTF/OTF family-name parsing."""

from __future__ import annotations

import hashlib
import re
import shutil
import struct
import subprocess
from functools import lru_cache
from pathlib import Path

from videoflow.domain.errors import AssetNotFoundError, FilesystemError
from videoflow.runtime import portable_home

MAX_FONT_BYTES = 20 * 1024 * 1024
_SFNT_MAGIC = {b"\x00\x01\x00\x00", b"OTTO", b"true"}


def fonts_dir() -> Path:
    directory = portable_home() / "assets" / "fonts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_fonts() -> list[dict[str, object]]:
    fonts: list[dict[str, object]] = []
    for path in sorted(fonts_dir().iterdir()):
        if path.suffix.casefold() not in {".ttf", ".otf"} or not path.is_file():
            continue
        try:
            family = font_family(path.read_bytes())
        except FilesystemError:
            family = path.stem
        fonts.append(
            {
                "file": str(path),
                "name": path.name,
                "family": family,
                "size_bytes": path.stat().st_size,
            }
        )
    return fonts


def system_font_dirs() -> list[Path]:
    candidates = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local" / "share" / "fonts",
        Path("C:/Windows/Fonts"),
        Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
    ]
    return [path for path in candidates if path.is_dir()]


@lru_cache(maxsize=1)
def list_system_fonts() -> list[dict[str, object]]:
    """List installed system fonts, capped to keep startup bounded."""

    fonts: list[dict[str, object]] = []
    seen: set[str] = set()
    for directory in system_font_dirs():
        try:
            paths = sorted(directory.rglob("*"))
        except OSError:
            continue
        for path in paths:
            if len(fonts) >= 500:
                return fonts
            if not path.is_file() or path.suffix.casefold() not in {".ttf", ".otf"}:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                family = font_family(path.read_bytes())
            except (FilesystemError, OSError):
                family = path.stem
            fonts.append(
                {
                    "file": str(path),
                    "name": path.name,
                    "family": family,
                    "size_bytes": path.stat().st_size,
                    "source": "system",
                }
            )
    return fonts


def font_aliases() -> dict[str, str]:
    return dict(_METRIC_ALIASES)


def save_font(filename: str, data: bytes) -> dict[str, object]:
    if not data:
        raise FilesystemError("The font file is empty.")
    if len(data) > MAX_FONT_BYTES:
        raise FilesystemError(f"Font files must be at most {MAX_FONT_BYTES // (1024 * 1024)} MB.")
    suffix = Path(filename).suffix.casefold()
    if suffix not in {".ttf", ".otf"}:
        raise FilesystemError("Only .ttf and .otf fonts are supported.")
    family = font_family(data)
    digest = hashlib.sha256(data).hexdigest()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip("-") or "font"
    target = fonts_dir() / f"{safe_stem}-{digest[:10]}{suffix}"
    target.write_bytes(data)
    return {
        "file": str(target),
        "name": target.name,
        "family": family,
        "size_bytes": len(data),
        "sha256": digest,
    }


def font_family(data: bytes) -> str:
    if len(data) < 12 or data[:4] not in _SFNT_MAGIC:
        raise FilesystemError("The file is not a TrueType or OpenType font.")
    try:
        table_count = struct.unpack(">H", data[4:6])[0]
        name_offset = name_length = 0
        for index in range(table_count):
            record = 12 + index * 16
            if record + 16 > len(data):
                break
            tag, _checksum, offset, length = struct.unpack(">4sIII", data[record : record + 16])
            if tag == b"name":
                name_offset, name_length = offset, length
                break
        if not name_offset or name_offset + name_length > len(data):
            raise FilesystemError("The font has no readable name table.")
        table = data[name_offset : name_offset + name_length]
        count, string_offset = struct.unpack(">HH", table[2:6])
        best_score = -1
        best_text = ""
        for index in range(count):
            record = 6 + index * 12
            if record + 12 > len(table):
                break
            platform, encoding, language, name_id, length, offset = struct.unpack(
                ">HHHHHH", table[record : record + 12]
            )
            if name_id not in {1, 16} or not length:
                continue
            raw = table[string_offset + offset : string_offset + offset + length]
            if not raw:
                continue
            if platform in {0, 3}:
                text = raw.decode("utf-16-be", errors="ignore")
            elif platform == 1 and encoding == 0:
                text = raw.decode("mac_roman", errors="ignore")
            else:
                text = raw.decode("latin-1", errors="ignore")
            text = " ".join(text.split())
            if not text:
                continue
            # Prefer typographic family (16), then Windows Unicode (3/1), then any.
            score = (4 if name_id == 16 else 0) + (
                2 if platform == 3 and encoding == 1 else 0
            )
            if score > best_score:
                best_score = score
                best_text = text
        if not best_text:
            raise FilesystemError("The font name table has no family name.")
        return best_text
    except (struct.error, UnicodeError) as exc:
        raise FilesystemError(f"Cannot read the font family: {exc}") from exc


def delete_fonts(name: str) -> None:
    target = fonts_dir() / Path(name).name
    if target.parent != fonts_dir() or not target.is_file():
        raise AssetNotFoundError(f"Unknown fonts asset: {name}")
    target.unlink()


_METRIC_ALIASES = {
    "arial": "Liberation Sans",
    "helvetica": "Liberation Sans",
    "times new roman": "Liberation Serif",
    "times": "Liberation Serif",
    "courier new": "Liberation Mono",
    "courier": "Liberation Mono",
    "segoe ui": "DejaVu Sans",
}


def resolve_font_family(family: str) -> str | None:
    """Return a registered/system family, including metric-compatible aliases."""

    name = str(family or "").strip()
    if not name:
        return None
    for item in list_fonts():
        candidate = str(item.get("family") or "").strip()
        if candidate.casefold() == name.casefold():
            return candidate
    for item in list_system_fonts():
        candidate = str(item.get("family") or "").strip()
        if candidate.casefold() == name.casefold():
            return candidate
    binary = shutil.which("fc-match")
    if binary is not None:
        try:
            completed = subprocess.run(
                [binary, "-f", "%{family}", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is not None and completed.returncode == 0:
            resolved = (completed.stdout or "").split(",", 1)[0].split(":", 1)[0].strip()
            if resolved and name.casefold() in resolved.casefold():
                return resolved
            alias = _METRIC_ALIASES.get(name.casefold())
            if alias and alias.casefold() in resolved.casefold():
                return alias
    return _METRIC_ALIASES.get(name.casefold())


def font_available(family: str) -> bool:
    """Check a registered font, fontconfig, or a known metric alias."""

    if not str(family or "").strip():
        return True
    return resolve_font_family(family) is not None


def register_font(path: Path, *, name: str = "") -> dict[str, object]:
    """Copy a TTF/OTF into the managed font store and return its record."""

    source = Path(path).expanduser()
    if not source.is_file():
        raise FilesystemError(f"Font does not exist: {source}")
    return save_font(name or source.name, source.read_bytes())
