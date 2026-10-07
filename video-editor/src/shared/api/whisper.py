"""OpenAI Whisper API 래퍼: 단어/세그먼트 타임스탬프가 있는 전사.

참고 (2026-10-06 확인):
- API 레퍼런스: https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create
- 가이드: https://developers.openai.com/api/docs/guides/speech-to-text
  - 업로드 최대 25MB, mp3 지원, 긴 오디오는 25MB 이하 청크로 분할 권장
  - timestamp_granularities[]는 whisper-1 전용이며 response_format=verbose_json 필요
  - word+segment 동시 요청은 문서에 명시가 없다. segments가 비어 와도 호출부는 동작한다
    (문장 경계를 전체 첫/마지막 단어로만 판정).
- SDK 시그니처: openai 3.24.0 `client.audio.transcriptions.create`
- prompt (2026-10-07 확인): 이전 청크 문맥 전달 용도, whisper-1은 224토큰 한도
- 재시도: https://github.com/openai/openai-python#retries
  - `max_retries` 기본 2. 연결 오류·타임아웃·429·5xx를 지수 백오프로 재시도
"""

from __future__ import annotations

from pathlib import Path

WHISPER_MODEL = "whisper-1"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_RETRIES = 4


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio: Path, api_key: str, language: str = "ko", prompt: str | None = None) -> dict:
    """audio를 전사해 {"words": [{word, start, end}], "segments": [{start, end, text}]}를 반환한다.

    문장 경계 판정에 세그먼트 텍스트(구두점)가 필요하므로 word와 segment 타임스탬프를 함께 요청한다.
    prompt가 있으면 함께 보내 직전 청크의 문맥을 잇는다.
    """
    import openai  # 무음 제거 등 Whisper를 쓰지 않는 커맨드는 openai 로딩 비용을 내지 않는다

    size = audio.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise TranscriptionError(f"오디오 파일이 Whisper 업로드 제한(25MB)을 넘습니다: {size / 1024 / 1024:.1f}MB")

    client = openai.OpenAI(api_key=api_key, max_retries=MAX_RETRIES)
    extra = {"prompt": prompt} if prompt else {}
    try:
        with audio.open("rb") as f:
            result = client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language=language,
                **extra,
            )
    except openai.AuthenticationError as exc:
        raise TranscriptionError(f"Whisper API 인증 실패 - API 키를 확인하세요. ({exc})") from exc
    except openai.OpenAIError as exc:
        raise TranscriptionError(f"Whisper API 호출 실패: {exc}") from exc

    return {
        "words": [{"word": w.word, "start": w.start, "end": w.end} for w in result.words or []],
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments or []],
    }
