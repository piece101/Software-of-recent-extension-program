"""자막 읽기/쓰기 (SRT / VTT / TXT / 타임코드 텍스트)."""

from __future__ import annotations

import re
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


def write_txt_timestamped(segments: list[Segment], path: Path) -> None:
    lines = []
    for seg in segments:
        stamp = format_timestamp(seg.start, comma=False)[:-4]  # HH:MM:SS
        lines.append(f"[{stamp}] {seg.text.strip()}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


WRITERS: dict[str, Callable[[list[Segment], Path], None]] = {
    "srt": write_srt,
    "vtt": write_vtt,
    "txt": write_txt,
    "타임코드": write_txt_timestamped,
}

# 형식 키 -> 파일 확장자
EXTS: dict[str, str] = {
    "srt": ".srt",
    "vtt": ".vtt",
    "txt": ".txt",
    "타임코드": ".타임코드.txt",
}


def output_path(out_dir: Path, stem: str, fmt: str) -> Path:
    return out_dir / f"{stem}{EXTS[fmt]}"


# ── 읽기(파싱) ──────────────────────────────────────────────────────
_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")
_TS_SHORT = re.compile(r"^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*(.+)$")


def _to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def _parse_timed(text: str) -> list[Segment]:
    """SRT / VTT 공통 파서."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"^WEBVTT[^\n]*\n", "", text)
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]  # SRT 인덱스 줄
        if not lines or "-->" not in lines[0]:
            continue
        stamps = list(_TS.finditer(lines[0]))
        if len(stamps) < 2:
            continue
        start = _to_sec(*stamps[0].groups())
        end = _to_sec(*stamps[1].groups())
        body = " ".join(lines[1:]).strip()
        if body:
            segments.append(Segment(len(segments) + 1, start, end, body))
    return segments


def parse_subtitle_file(path: str | Path) -> list[Segment]:
    """.srt / .vtt / .txt / 타임코드 텍스트 파일을 세그먼트 목록으로."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() in (".srt", ".vtt"):
        segs = _parse_timed(text)
        if segs:
            return segs

    # 그 외: 줄 단위 텍스트. "[00:12] ..." 형태면 시간도 회수.
    out: list[Segment] = []
    for ln in text.replace("\r", "").split("\n"):
        ln = ln.strip()
        if not ln or ln.upper().startswith("WEBVTT"):
            continue
        m = _TS_SHORT.match(ln)
        if m:
            h, mn, sc, body = m.groups()
            sec = int(h) * 60 + int(mn) if sc is None else int(h) * 3600 + int(mn) * 60 + int(sc)
            out.append(Segment(len(out) + 1, float(sec), float(sec), body))
        else:
            out.append(Segment(len(out) + 1, 0.0, 0.0, ln))
    return out
