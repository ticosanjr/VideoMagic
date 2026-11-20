from __future__ import annotations

import sys
from pathlib import Path

from videoflow.core import nvenc


def _fake_ffmpeg(tmp_path: Path, *, fail_first: bool = True) -> Path:
    marker = tmp_path / "calls.txt"
    script = tmp_path / "fake-ffmpeg"
    script.write_text(
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "args = sys.argv[1:]\n"
        "marker.write_text((marker.read_text() if marker.exists() else '') + "
        "' '.join(args) + '\\n')\n"
        "if '-encoders' in args:\n"
        "    print(' V....D h264_nvenc')\n"
        "    raise SystemExit(0)\n"
        f"fail_first = {fail_first!r}\n"
        "count = len(marker.read_text().splitlines()) - 1\n"
        "if fail_first and count == 1:\n"
        "    print('[h264_nvenc] Invalid argument', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
        "pathlib.Path(args[-1]).write_bytes(b'x' * 2048)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_probe_falls_back_to_compatible_nvenc_options(tmp_path: Path) -> None:
    fake = _fake_ffmpeg(tmp_path)
    probe = nvenc.probe_nvenc(str(fake), force=True)
    assert probe.available is True
    assert probe.args == (
        "-preset",
        "p4",
        "-tune",
        "hq",
        "-rc",
        "constqp",
        "-qp",
        "23",
    )


def test_probe_reports_missing_encoder(tmp_path: Path) -> None:
    script = tmp_path / "no-nvenc"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "print(' V....D libx264')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    probe = nvenc.probe_nvenc(str(script), force=True)
    assert probe.available is False
    assert "h264_nvenc" in probe.reason


def test_probe_classifies_driver_failure(tmp_path: Path) -> None:
    script = tmp_path / "broken-driver"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if '-encoders' in sys.argv:\n"
        "    print(' h264_nvenc')\n"
        "    raise SystemExit(0)\n"
        "print('Cannot load libnvidia-encode.so.1', file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    probe = nvenc.probe_nvenc(str(script), force=True)
    assert probe.available is False
    assert "driver" in probe.advice.casefold()
