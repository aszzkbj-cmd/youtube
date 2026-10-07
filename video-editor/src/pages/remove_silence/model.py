"""무음 제거 도메인 로직: 기본값, 유지 구간 계산.

무음 감지(silencedetect 실행·파싱)는 shared.api.silence에 있다.
"""

from __future__ import annotations

DEFAULT_THRESHOLD_DB = -35.0
DEFAULT_MIN_SILENCE = 0.5
DEFAULT_MARGIN_BEFORE = 0.15
DEFAULT_MARGIN_AFTER = 0.3
MIN_SEGMENT_LENGTH = 0.05  # 이보다 짧은 유지 구간은 버린다

Segment = tuple[float, float]


def compute_keep_segments(
    silences: list[Segment],
    duration: float,
    margin_before: float,
    margin_after: float,
) -> list[Segment]:
    """무음 구간을 margin만큼 줄인 뒤, 그 여집합(유지할 구간)을 반환한다.

    무음 [s, e]의 앞쪽은 직전 음성의 끝이므로 margin_after만큼, 뒤쪽은 다음 음성의
    시작이므로 margin_before만큼 남긴다. 영상 맨 앞/뒤에 붙은 무음은 반대편에 음성이
    없으므로 해당 쪽 margin을 적용하지 않는다.
    """
    cuts: list[Segment] = []
    for s, e in sorted(silences):
        cut_start = s + margin_after if s > 0 else 0.0
        cut_end = e - margin_before if e < duration else duration
        if cut_end - cut_start > 0:
            cuts.append((cut_start, cut_end))

    keep: list[Segment] = []
    cursor = 0.0
    for cut_start, cut_end in cuts:
        if cut_start > cursor:
            keep.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if cursor < duration:
        keep.append((cursor, duration))

    return [(s, e) for s, e in keep if e - s >= MIN_SEGMENT_LENGTH]
