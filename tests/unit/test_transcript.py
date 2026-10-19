from pathlib import Path

import pytest

from videoflow.domain.errors import TranscriptError
from videoflow.domain.transcript import parse_srt, parse_srt_file

SAMPLE = """1
00:00:00,500 --> 00:00:01,250
Hello there.

2
00:00:02,000 --> 00:00:03,500
This is the second line.
"""


def test_srt_times_become_samples() -> None:
    sentences = parse_srt(SAMPLE, 48000)
    assert len(sentences) == 2
    assert sentences[0].start_sample == 24000
    assert sentences[0].end_sample == 60000
    assert sentences[1].start_sample == 96000
    assert sentences[1].end_sample == 168000
    assert [item.id for item in sentences] == [0, 1]


def test_crlf_and_utf8_bom_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "subs.srt"
    path.write_text("\ufeff" + SAMPLE.replace("\n", "\r\n"), encoding="utf-8")
    assert len(parse_srt_file(path, 48000)) == 2


def test_empty_file_is_rejected() -> None:
    with pytest.raises(TranscriptError):
        parse_srt("   ", 48000)


def test_sample_rate_must_be_positive() -> None:
    with pytest.raises(TranscriptError, match="sample rate"):
        parse_srt(SAMPLE, 0)


def test_missing_timecode_is_rejected() -> None:
    with pytest.raises(TranscriptError, match="timecode"):
        parse_srt("1\nHello\n", 48000)


def test_empty_cue_text_is_rejected() -> None:
    with pytest.raises(TranscriptError, match="text"):
        parse_srt("1\n00:00:00,000 --> 00:00:01,000\n\n", 48000)


def test_inverted_cue_is_rejected() -> None:
    with pytest.raises(TranscriptError, match="ends before"):
        parse_srt("1\n00:00:02,000 --> 00:00:01,000\nHi\n", 48000)


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(TranscriptError, match="cannot read"):
        parse_srt_file(tmp_path / "missing.srt", 48000)
