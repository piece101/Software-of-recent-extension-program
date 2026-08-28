"""자막 문자열 생성 (SRT / VTT / TXT)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str


def format_timestamp(seconds: float, *, comma: bool = True) -> str:
    """초 -> 'HH:MM:SS,mmm'(SRT) 또는 'HH:MM:SS.mmm'(VTT)."""
    if seconds is None or seconds < 0:
        seconds = 0.0
    millis = int(round(seconds * 1000.0))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def write_srt(segments: list[Segment], path: Path) -> None:
    lines: list[str] = []
    for seg in segments:
        lines.append(str(seg.index))
        lines.append(f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_vtt(segments: list[Segment], path: Path) -> None:
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        start = format_timestamp(seg.start, comma=False)
        end = format_timestamp(seg.end, comma=False)
        lines.append(f"{start} --> {end}")
        lines.append(seg.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_txt(segments: list[Segment], path: Path) -> None:
    text = " ".join(seg.text.strip() for seg in segments).strip()
    path.write_text(text + "\n", encoding="utf-8")


WRITERS: dict[str, Callable[[list[Segment], Path], None]] = {
    "srt": write_srt,
    "vtt": write_vtt,
    "txt": write_txt,
}
