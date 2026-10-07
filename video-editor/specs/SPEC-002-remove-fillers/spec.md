# SPEC-002: 간투사 제거 (remove-fillers)

## 개요

입력 영상의 음성을 OpenAI Whisper로 단어 단위 전사한 뒤, 사전에 등록된 간투사 중 단독으로 발화된 것을
찾아 제거하고 남은 구간을 이어 붙인 영상을 만든다. 무음 제거는 하지 않는다 (SPEC-001 담당).

## CLI

```
uv run python remove_fillers.py <input_video> [--output <path>] [--api-key <key>]
    [--fillers-file <txt>] [--margin-before <초>] [--margin-after <초>] [--padding <초>]
    [--dry-run] [--no-reencode] [--no-cache]
```

| 옵션 | 기본값 | 의미 |
|------|--------|------|
| `--output` | `{원본이름}_no_fillers.mp4` | 출력 경로 |
| `--api-key` | 환경변수 / `.env`의 `OPENAI_API_KEY` | OpenAI API 키 |
| `--fillers-file` | 스크립트 옆 `fillers.txt` | 간투사 사전 (한 줄에 하나) |
| `--margin-before` | 0.1 (초) | 간투사 시작 전 함께 제거할 여백 |
| `--margin-after` | 0.15 (초) | 간투사 끝 후 함께 제거할 여백 |
| `--padding` | 0.05 (초) | 이어 붙이는 구간 사이에 넣을 무음 |
| `--dry-run` | 꺼짐 | 편집 없이 감지 결과와 예상 단축 시간만 출력 |
| `--no-reencode` | 꺼짐 | `-c copy`로 자르기 (기본은 재인코딩) |
| `--no-cache` | 꺼짐 | 저장된 전사 결과를 무시하고 다시 전사 |

## 요구사항 (EARS)

### Ubiquitous
- **REQ-U1** 시스템은 영상 처리에 ffmpeg/ffprobe CLI를 subprocess로, 전사에 `openai` 패키지(Whisper API)를 사용해야 한다.
- **REQ-U2** 시스템은 모든 CLI 옵션을 argparse로 관리해야 한다.
- **REQ-U3** 시스템은 Whisper를 `model=whisper-1`, `response_format=verbose_json`, `language=ko`, `timestamp_granularities=["word", "segment"]`로 호출해야 한다.

### Event-driven
- **REQ-E1** WHEN 실행되면, 시스템은 간투사 사전을 읽어 정규화(공백·구두점 제거)한 목록을 만들어야 한다. 빈 줄과 `#` 주석은 무시한다.
- **REQ-E2** WHEN 입력 영상이 주어지면, 시스템은 ffprobe로 duration을 확인하고 오디오만 16kHz 모노 32kbps mp3로 임시 추출해야 한다.
- **REQ-E3** WHEN 오디오가 5분보다 길면, 시스템은 약 5분 단위 청크로 나눠 전사하고 각 타임스탬프에 청크 시작 시각을 더해야 한다 (업로드 크기를 작게 유지해 대용량 TLS 업로드 오류 `SSLV3_ALERT_BAD_RECORD_MAC` 방지).
- **REQ-E3a** WHEN 청크 경계를 정할 때, 시스템은 5분 지점 직전 60초 안에서 0.3초 이상 무음(-35dB)이 있으면 5분 지점에 가장 가까운 무음의 가운데에서 잘라야 한다. 없으면 5분 지점에서 자른다 (문장 중간 분할 방지).
- **REQ-E3b** WHEN 두 번째 이후 청크를 전사할 때, 시스템은 직전 청크 전사 텍스트의 마지막 100자를 `prompt`로 전달해 문맥을 이어야 한다 (whisper-1 prompt 한도 224토큰).
- **REQ-E3c** WHEN Whisper 호출 중 연결 오류·타임아웃·429·5xx가 나면, 시스템은 해당 청크 요청만 최대 4번 재시도해야 한다 (SDK `max_retries`).
- **REQ-E4** WHEN 전사 결과를 받으면, 시스템은 정규화한 단어가 사전에 있고 다음 중 하나를 만족할 때 간투사로 판정해야 한다.
  - 앞 단어 end와의 간격 ≥ 0.3초, 또는 다음 단어 start와의 간격 ≥ 0.3초
  - 문장의 첫 단어 또는 마지막 단어
- **REQ-E5** WHEN 문장 경계를 판정할 때, 시스템은 Whisper 세그먼트의 첫/마지막 단어를 경계로 보고, 세그먼트 텍스트의 토큰 수가 단어 수와 같으면 토큰 끝 문장부호(`. ? ! …`)로 세그먼트 내부 경계도 찾아야 한다.
- **REQ-E6** WHEN 간투사가 판정되면, 시스템은 `(start - margin_before, end + margin_after)`를 제거 구간으로 잡되 앞 단어 end / 뒤 단어 start를 넘지 않게 하고, 겹치거나 맞닿은 구간을 병합한 뒤 여집합을 유지 구간으로 계산해야 한다.
- **REQ-E7** WHEN 유지 구간이 계산되면, 시스템은 각 구간을 임시 파일로 추출하고 마지막을 제외한 구간 끝에 `padding`만큼 무음(apad)과 마지막 프레임 유지(tpad)를 덧붙인 뒤 concat demuxer로 병합해야 한다.
- **REQ-E8** WHEN 처리가 끝나면, 시스템은 감지된 간투사 목록(시간, 단어, 판정 근거)과 원본 → 결과 길이, 단축 시간을 출력해야 한다.
- **REQ-E9** IF `--dry-run`이면, THEN 시스템은 영상을 만들지 않고 간투사 표와 예상 길이·단축 시간만 출력해야 한다.
- **REQ-E10** IF `--output`이 없으면, THEN 시스템은 입력과 같은 폴더에 `{원본이름}_no_fillers.mp4`로 저장해야 한다.
- **REQ-E11** IF `--no-reencode`이면, THEN 시스템은 `-c copy`로 자르고 padding을 적용하지 않으며, 결과가 길어질 수 있다는 경고를 출력해야 한다. 아니면 libx264/aac로 재인코딩한다.
- **REQ-E12** IF 간투사 사전 파일이 없으면, THEN 시스템은 "fillers.txt를 생성하고 간투사를 한 줄에 하나씩 입력하세요"를 출력하고 종료 코드 1로 끝나야 한다.
- **REQ-E13** IF API 호출이 필요한데 `--api-key`와 `OPENAI_API_KEY`가 모두 없으면, THEN 시스템은 설정 방법을 안내하고 종료 코드 1로 끝나야 한다.
- **REQ-E14** IF Whisper API 호출이 (재시도 후에도) 실패하면, THEN 시스템은 실패한 청크 번호와 오류 내용을 출력하고 종료 코드 1로 끝나야 한다.
- **REQ-E15** IF 간투사가 없으면, THEN 시스템은 "간투사 없음"을 출력하고 원본을 출력 경로로 복사해야 한다 (dry-run에서는 출력만).
- **REQ-E16** IF ffmpeg/ffprobe가 없거나 subprocess가 실패하거나 입력 파일·오디오 트랙이 없으면, THEN 시스템은 SPEC-001과 같은 방식으로 안내하고 종료 코드 1로 끝나야 한다.

### State-driven
- **REQ-S1** WHILE 처리 중인 동안, 시스템은 임시 파일을 `remove_fillers_*` 임시 디렉터리에 두고 종료 시(예외 포함) 삭제해야 한다.
- **REQ-S2** WHILE 입력 파일의 크기·수정 시각이 바뀌지 않은 동안, 시스템은 `{원본이름}.transcript.json`에 저장한 전사 결과를 재사용해야 한다 (`--no-cache`로 무시).

### Unwanted
- **REQ-N1** 시스템은 입력 파일을 덮어쓰면 안 된다.
- **REQ-N2** 시스템은 0.05초 미만의 유지 구간을 추출하면 안 된다.
- **REQ-N3** 시스템은 margin 때문에 이웃 단어를 잘라내면 안 된다.

## 제약 조건
- Python ≥ 3.12, uv로 실행. 외부 패키지는 `openai`만 사용 (`.env`는 자체 로더로 읽음).
- `.env` 탐색 순서: 프로젝트 루트 → 현재 디렉터리. 이미 설정된 환경변수가 우선한다.

## 의존성
- ffmpeg / ffprobe (외부 실행 파일, libmp3lame 포함 빌드)
- OpenAI API 키 (Whisper, 유료)
