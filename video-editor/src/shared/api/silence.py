"""ffmpeg silencedetect 래퍼: 무음 구간 감지와 로그 파싱.

무음 제거(구간 계산)와 간투사 제거(청크 경계 선택)가 함께 쓴다.

참고:
- silencedetect: https://ffmpeg.org/ffmpeg-filters.html#silencedetect
"""

from __future__ import annotations

import re
from pathlib import Path

from .ffmpeg import run

Segment = tuple[float, float]

# 실제 로그는 "silence_start: 1.5", 문서 표기는 "silence_start=1.5" — 둘 다 허용
_SILENCE_START_RE = re.compile(r"silence_start\s*[:=]\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end\s*[:=]\s*(-?[\d.]+)")


def parse_silences(log: str, duration: float) -> list[Segment]:
    """silencedetect 로그에서 (start, end) 무음 구간을 추출한다."""
    silences: list[Segment] = []
    start: float | None = None
    for line in log.splitlines():
        if (m := _SILENCE_START_RE.search(line)) is not None:
            start = max(0.0, float(m.group(1)))
        elif (m := _SILENCE_END_RE.search(line)) is not None and start is not None:
            silences.append((start, min(duration, float(m.group(1)))))
            start = None
    if start is not None:  # 무음으로 끝나는 영상은 silence_end가 출력되지 않는다
        silences.append((start, duration))
    return silences


def detect_silences(path: Path, threshold_db: float, min_silence: float, duration: float) -> list[Segment]:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(path),
        "-vn", "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])
    return parse_silences(result.stderr, duration)
