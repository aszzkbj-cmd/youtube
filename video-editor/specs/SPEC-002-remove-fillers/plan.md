# SPEC-002 구현 계획

## 기술 스택
- Python 3.12+ 표준 라이브러리 + `openai` (Whisper API)
- ffmpeg / ffprobe CLI
- uv

## 구조

```
remove_fillers.py                ← 루트 실행 파일 (src를 path에 추가 후 app 호출)
fillers.txt                      ← 기본 간투사 사전
.env.example                     ← OPENAI_API_KEY 설정 예시
src/
  app/__init__.py                ← remove_fillers / remove_silence 커맨드 연결
  pages/remove_fillers/
    cli.py                       ← (ui) argparse, 흐름 제어, 표/결과 출력, API 키·사전 로드
    model.py                     ← (model) 기본값, 사전 파싱, 문장 경계, 간투사 판정, 제거/유지 구간
    api.py                       ← (api) 무음 기준 청크 경계, 오디오 청크 추출, 청크별 전사·오프셋·prompt, 전사 캐시
    test/
  shared/api/
    ffmpeg.py                    ← (기존) run, require_tools, probe_duration, has_audio
    segments.py                  ← (SPEC-001에서 이동) 구간 추출(+pad), concat
    silence.py                   ← (SPEC-001에서 이동) silencedetect 실행·로그 파싱
    whisper.py                   ← Whisper 호출(prompt, 재시도), 25MB 확인, openai 예외 → TranscriptionError
  shared/lib/
    timefmt.py                   ← format_time (SPEC-001 cli에서 이동)
    text.py                      ← 전각 문자 폭 계산 (표 정렬)
  shared/config/
    dotenv.py                    ← 최소 .env 로더 (환경변수 설정)
```

배치 근거:
- 구간 추출/병합과 `format_time`은 두 커맨드가 함께 쓰게 되어 `shared`로 올렸다 (SPEC-001 plan의 "재사용이 생길 때 도입" 원칙).
- 무음 감지도 청크 경계 계산에 쓰게 되어 `pages/remove_silence`에서 `shared/api/silence.py`로 올렸다 (슬라이스 간 import 금지).
- Whisper 호출은 비즈니스 무관 외부 API 래퍼라 `shared/api`. 청크 분할·캐시는 이 커맨드 흐름에 묶여 있어 page에 둔다.
- `openai`는 `whisper.py` 함수 안에서 import해 무음 제거 실행 시 로딩 비용이 없다.

## 명세 대비 설계 결정

| 명세 | 구현 | 이유 |
|------|------|------|
| `timestamp_granularities=["word"]` | `["word", "segment"]` | word만 요청하면 세그먼트가 오지 않고, Whisper 단어에는 구두점이 없어 "문장 첫/마지막 단어"를 판정할 수 없다. segment 추가는 비용·지연 증가 없음 |
| padding 무음은 `anullsrc`로 생성 | 구간 추출 시 `apad`(무음) + `tpad`(마지막 프레임 유지) | anullsrc로 만든 클립은 영상 트랙이 없어 concat 시 A/V 싱크가 어긋나거나 코덱 파라미터 불일치로 실패한다. 생성되는 소리는 같은 디지털 무음 |
| 오디오를 mp3로 추출 | 16kHz 모노 32kbps mp3, 약 5분 청크 (≈1.2MB) | 25MB 제한과 별개로, 다른 환경(macOS)에서 ~6MB 단일 업로드가 `SSLV3_ALERT_BAD_RECORD_MAC`으로 반복 실패했고 60초 청크로는 성공했다. 재시도로는 해결되지 않는 네트워크 경로 문제라 업로드 크기 자체를 줄인다. 60초는 경계(=가짜 문장 경계)가 너무 많아 5분으로 절충. Whisper는 16kHz 모노로 처리하므로 품질 손실 없음 |
| (명세 없음) | 청크 경계를 5분 지점 직전 60초 안의 무음 가운데로 | 공식 가이드 "문장 중간에서 자르지 말 것". 경계 단어 누락과, 경계가 "문장 첫/마지막 단어"로 잘못 판정되는 것을 줄인다. 5분 이하 영상은 무음 감지를 하지 않는다 |
| (명세 없음) | 직전 청크 텍스트 마지막 100자를 `prompt`로 | 공식 가이드의 "이전 청크 문맥 전달". whisper-1 prompt 한도 224토큰 안에 들도록 한글 100자 |
| (명세 없음) | `OpenAI(max_retries=4)` | SDK가 연결 오류·429·5xx를 지수 백오프로 재시도(기본 2). 청크가 작아 재시도 비용이 낮다 |
| margin 적용 | 이웃 단어 경계에서 멈춤 | 단어 사이 간격이 margin보다 짧을 때 앞/뒤 단어 끝이 잘리는 것을 방지 |
| (명세 없음) | 전사 캐시 `{원본이름}.transcript.json` | `--dry-run`으로 확인 후 실제 실행하는 흐름에서 같은 영상을 두 번 유료 전사하지 않도록. 입력 파일 크기·mtime이 바뀌면 무효 |
| API 키 미설정 시 종료 | API 호출이 필요할 때만 확인 | 캐시가 있으면 키 없이도 재실행 가능 |

## 위험 분석

| 위험 | 영향 | 대응 |
|------|------|------|
| `-c copy`는 직전 키프레임부터 잘림 | 각 구간 앞부분이 중복됨. 짧은 간투사 컷에서는 결과가 원본보다 길어짐 (테스트: 6s → 7.3s, GOP 1s) | 기본은 재인코딩. `--no-reencode` 시 경고 출력 |
| Whisper 단어 타임스탬프 오차 | 컷이 약간 이르거나 늦음 | margin, `--dry-run`으로 사전 확인 |
| "이제/그래서/지금" 등은 실제 의미로도 쓰임 | 문장 첫머리의 정상 접속사도 제거될 수 있음 | 명세대로 판정, 표의 판정 근거로 확인 후 사전 조정 |
| 청크 경계에서 단어가 잘림 | 경계 단어 1개 인식 누락 가능 | 무음 지점에서 자름. 근처에 무음이 없을 때만 5분 지점에서 강제 분할 |
| 청크 경계가 문장 경계로 판정됨 | 경계 옆 간투사가 "문장 첫/마지막 단어"로 제거될 수 있음 | 무음에서 자르므로 대개 실제 문장 경계와 일치. `--dry-run` 표의 판정 근거로 확인 |
| 중간 청크에서 실패 | 앞 청크 전사 결과가 버려져 재실행 시 다시 과금 | 재시도 4회. 실패 시 몇 번째 청크인지 출력 |
| 세그먼트 텍스트와 단어 수 불일치 | 세그먼트 내부 문장 경계 누락 | 세그먼트 양끝 경계로 대체 |
| API 비용 | 재실행마다 과금 | 전사 캐시 |

## 참고 문서
- Whisper API: https://platform.openai.com/docs/api-reference/audio/createTranscription
- 청크 분할·prompt 가이드 (2026-10-07 확인): https://developers.openai.com/api/docs/guides/speech-to-text
  - "Avoid splitting in the middle of a sentence", "Carrying context from a previous chunk", whisper-1 prompt 224토큰 한도
- SDK 재시도 (`max_retries`, 기본 2, 연결 오류·429·5xx 대상): https://github.com/openai/openai-python#retries
- tpad / apad: https://ffmpeg.org/ffmpeg-filters.html#tpad , https://ffmpeg.org/ffmpeg-filters.html#apad
- concat demuxer: https://ffmpeg.org/ffmpeg-formats.html#concat-1
