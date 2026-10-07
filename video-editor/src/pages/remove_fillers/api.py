"""간투사 제거 전용 외부 호출: 오디오 추출, 청크 단위 전사, 전사 결과 캐시.

음성만 저비트레이트 mp3로 뽑아 약 CHUNK_SECONDS 단위로 나눠 전사한 뒤 타임스탬프에 청크 시작 시각을 더해 합친다.
16kHz 모노 32kbps → 5분 청크 ≈ 1.2MB. Whisper는 내부적으로 16kHz 모노를 쓰므로 인식 품질 손실이 없다.
청크를 작게 두는 이유: 일부 네트워크에서 수 MB 단일 업로드가 SSL 오류(BAD_RECORD_MAC)로 반복 실패한다.
문장 중간에서 자르지 않도록 경계는 목표 지점 직전의 무음 가운데로 잡고, 직전 청크 텍스트를 prompt로 넘긴다.

참고:
- -vn / -ac / -ar / -b:a: https://ffmpeg.org/ffmpeg.html#Audio-Options
- 청크 분할·prompt (2026-10-07 확인): https://developers.openai.com/api/docs/guides/speech-to-text
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from shared.api import TranscriptionError, detect_silences, run, transcribe

AUDIO_ARGS = ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k"]
CHUNK_SECONDS = 300.0
SPLIT_SEARCH_SECONDS = 60.0  # 목표 지점 직전 이 범위 안의 무음에서 자른다
SPLIT_SILENCE_DB = -35.0
SPLIT_MIN_SILENCE = 0.3
PROMPT_CHARS = 100  # whisper-1 prompt 한도 224토큰 안에 드는 한글 길이
CACHE_VERSION = 1


def plan_chunks(
    duration: float,
    silences: Sequence[tuple[float, float]] = (),
    chunk_seconds: float = CHUNK_SECONDS,
    search_seconds: float = SPLIT_SEARCH_SECONDS,
) -> list[tuple[float, float]]:
    """[0, duration]을 약 chunk_seconds 길이의 (start, length)로 나눈다.

    경계는 목표 지점(start + chunk_seconds) 직전 search_seconds 안에서 목표에 가장 가까운 무음의 가운데로 잡고,
    그런 무음이 없으면 목표 지점에서 자른다.
    """
    middles = sorted((s + e) / 2 for s, e in silences)
    chunks = []
    start = 0.0
    while duration - start > chunk_seconds:
        target = start + chunk_seconds
        candidates = [m for m in middles if max(start, target - search_seconds) < m <= target]
        cut = candidates[-1] if candidates else target
        chunks.append((start, cut - start))
        start = cut
    chunks.append((start, duration - start))
    return chunks


def transcript_tail(part: dict, chars: int = PROMPT_CHARS) -> str:
    text = "".join(s["text"] for s in part["segments"]) or " ".join(w["word"] for w in part["words"])
    return text.strip()[-chars:]


def build_audio_extract_command(src: Path, start: float, length: float, out: Path) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(src),
        "-t", f"{length:.3f}",
        *AUDIO_ARGS,
        str(out),
    ]


def offset_transcript(part: dict, offset: float) -> dict:
    return {
        "words": [{**w, "start": w["start"] + offset, "end": w["end"] + offset} for w in part["words"]],
        "segments": [{**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in part["segments"]],
    }


def transcribe_video(
    src: Path,
    duration: float,
    api_key: str,
    workdir: Path,
    progress: Callable[[str], None] = lambda _: None,
) -> dict:
    silences: list[tuple[float, float]] = []
    if duration > CHUNK_SECONDS:
        progress("청크 경계를 정하기 위해 무음 감지 중...")
        silences = detect_silences(src, SPLIT_SILENCE_DB, SPLIT_MIN_SILENCE, duration)
    chunks = plan_chunks(duration, silences)

    words: list[dict] = []
    segments: list[dict] = []
    prompt: str | None = None
    for i, (start, length) in enumerate(chunks):
        label = f" {i + 1}/{len(chunks)}" if len(chunks) > 1 else ""
        audio = workdir / f"audio_{i:03d}.mp3"
        progress(f"오디오 추출 중...{label}")
        run(build_audio_extract_command(src, start, length, audio))
        progress(f"Whisper 전사 중...{label} ({audio.stat().st_size / 1024 / 1024:.1f}MB)")
        try:
            raw = transcribe(audio, api_key, prompt=prompt)
        except TranscriptionError as exc:
            raise TranscriptionError(f"청크{label} 전사 실패 - {exc}") from exc
        part = offset_transcript(raw, start)
        words += part["words"]
        segments += part["segments"]
        prompt = transcript_tail(raw) or None
        audio.unlink()
    return {"words": words, "segments": segments}


# --- 전사 결과 캐시: --dry-run 후 실제 실행할 때 API를 다시 호출하지 않도록 ---

def cache_path(src: Path) -> Path:
    return src.with_name(f"{src.stem}.transcript.json")


def _fingerprint(src: Path) -> dict:
    stat = src.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def load_cached_transcript(src: Path) -> dict | None:
    path = cache_path(src)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") != CACHE_VERSION or data.get("source") != _fingerprint(src):
        return None
    return data.get("transcript")


def save_cached_transcript(src: Path, transcript: dict) -> Path:
    path = cache_path(src)
    data = {"version": CACHE_VERSION, "source": _fingerprint(src), "transcript": transcript}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
