"""간투사 제거 도메인 로직: 기본값, 사전 파싱, 문장 경계, 간투사 판정, 유지 구간 계산."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

DEFAULT_MARGIN_BEFORE = 0.1
DEFAULT_MARGIN_AFTER = 0.15
DEFAULT_PADDING = 0.05
ISOLATION_GAP = 0.3  # 앞/뒤 단어와 이 간격(초) 이상 떨어지면 단독 발화로 본다
MIN_SEGMENT_LENGTH = 0.05  # 이보다 짧은 유지 구간은 버린다
SENTENCE_END_CHARS = ".?!…。？！"

Segment = tuple[float, float]


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Filler:
    index: int  # words 리스트에서의 위치
    word: Word
    reasons: tuple[str, ...]


def normalize(text: str) -> str:
    """공백과 구두점을 제거한다 (글자/숫자만 남김)."""
    return "".join(ch for ch in text if ch.isalnum())


def parse_fillers(text: str) -> set[str]:
    """한 줄에 하나씩 적힌 간투사 사전을 정규화된 집합으로 만든다. 빈 줄과 # 주석은 무시."""
    fillers = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if word := normalize(line):
            fillers.add(word)
    return fillers


def parse_transcript(transcript: dict, duration: float) -> tuple[list[Word], list[tuple[float, float, str]]]:
    words = [
        Word(w["word"], max(0.0, float(w["start"])), min(duration, float(w["end"])))
        for w in transcript.get("words", [])
    ]
    segments = [(float(s["start"]), float(s["end"]), s["text"]) for s in transcript.get("segments", [])]
    return words, segments


def sentence_boundaries(
    words: list[Word], segments: list[tuple[float, float, str]]
) -> tuple[list[bool], list[bool]]:
    """각 단어가 문장의 첫 단어/마지막 단어인지 판정한다.

    Whisper의 단어 목록에는 구두점이 없으므로 세그먼트를 이용한다.
    - 세그먼트의 첫/마지막 단어는 문장 경계로 본다.
    - 세그먼트 텍스트를 공백으로 나눈 토큰 수가 그 세그먼트의 단어 수와 같으면,
      토큰 끝의 문장부호(. ? ! 등)로 세그먼트 내부의 문장 경계도 찾는다.
    """
    n = len(words)
    first, last = [False] * n, [False] * n
    if n == 0:
        return first, last

    # 단어 중앙 시각이 속하는 세그먼트로 묶는다
    starts = [s for s, _, _ in segments]
    groups: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        seg = max(0, bisect_right(starts, (w.start + w.end) / 2) - 1) if segments else 0
        groups.setdefault(seg, []).append(i)

    for seg, idxs in groups.items():
        first[idxs[0]] = True
        last[idxs[-1]] = True
        if not segments:
            continue
        tokens = segments[seg][2].split()
        if len(tokens) != len(idxs):
            continue
        for pos, token in enumerate(tokens[:-1]):
            if token.rstrip("\"'”’)」』").endswith(tuple(SENTENCE_END_CHARS)):
                last[idxs[pos]] = True
                first[idxs[pos + 1]] = True
    return first, last


def detect_fillers(words: list[Word], fillers: set[str], segments: list[tuple[float, float, str]]) -> list[Filler]:
    """사전에 있고 단독으로 발화된 단어를 간투사로 판정한다.

    단독 발화: 앞 단어와의 간격 또는 뒤 단어와의 간격이 ISOLATION_GAP 이상이거나,
    문장의 첫 단어 또는 마지막 단어인 경우.
    """
    first, last = sentence_boundaries(words, segments)
    found: list[Filler] = []
    for i, w in enumerate(words):
        if normalize(w.text) not in fillers:
            continue
        reasons = []
        if i > 0 and (gap := w.start - words[i - 1].end) >= ISOLATION_GAP:
            reasons.append(f"앞 간격 {gap:.2f}s")
        if i + 1 < len(words) and (gap := words[i + 1].start - w.end) >= ISOLATION_GAP:
            reasons.append(f"뒤 간격 {gap:.2f}s")
        if first[i]:
            reasons.append("문장 시작")
        if last[i]:
            reasons.append("문장 끝")
        if reasons:
            found.append(Filler(i, w, tuple(reasons)))
    return found


def compute_cuts(
    fillers: list[Filler],
    words: list[Word],
    duration: float,
    margin_before: float,
    margin_after: float,
) -> list[Segment]:
    """간투사마다 (start - margin_before, end + margin_after)를 제거 구간으로 잡고 겹치는 구간을 병합한다.

    margin이 이웃 단어를 잘라먹지 않도록 앞 단어의 end, 뒤 단어의 start에서 멈춘다.
    """
    cuts: list[Segment] = []
    for f in fillers:
        w = f.word
        lower = words[f.index - 1].end if f.index > 0 else 0.0
        upper = words[f.index + 1].start if f.index + 1 < len(words) else duration
        start = max(0.0, w.start - margin_before, min(lower, w.start))
        end = min(duration, w.end + margin_after, max(upper, w.end))
        if end > start:
            cuts.append((start, end))

    merged: list[Segment] = []
    for start, end in sorted(cuts):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def compute_keep_segments(cuts: list[Segment], duration: float) -> list[Segment]:
    """제거 구간(정렬·병합된 상태)의 여집합을 반환한다."""
    keep: list[Segment] = []
    cursor = 0.0
    for start, end in cuts:
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((cursor, duration))
    return [(s, e) for s, e in keep if e - s >= MIN_SEGMENT_LENGTH]


def estimate_result_duration(keep: list[Segment], padding: float) -> float:
    """유지 구간 합 + 구간 사이 padding."""
    return sum(e - s for s, e in keep) + padding * max(0, len(keep) - 1)
