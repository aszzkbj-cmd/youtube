# SPEC-001: 무음 구간 제거 (remove-silence)

## 개요

입력 영상에서 오디오 기준 무음 구간을 감지해 제거하고, 남은 구간을 이어 붙인 영상을 만든다.
영상 편집 시스템의 첫 번째 기능이다.

## CLI

```
uv run python remove_silence.py <input_video> [--output <path>] [--threshold <dB>]
    [--min-silence <초>] [--margin-before <초>] [--margin-after <초>] [--reencode]
```

| 옵션 | 기본값 | 의미 |
|------|--------|------|
| `--threshold` | -35 (dB) | 이 값보다 작은 소리를 무음으로 판정 |
| `--min-silence` | 0.5 (초) | 이 길이 이상인 무음만 제거 |
| `--margin-before` | 0.15 (초) | 음성 시작 전에 남길 여백 |
| `--margin-after` | 0.3 (초) | 음성 끝난 뒤 남길 여백 |
| `--output` | `{원본이름}_no_silence.mp4` | 출력 경로 |
| `--reencode` | 꺼짐 | libx264/aac로 재인코딩 |

## 요구사항 (EARS)

### Ubiquitous
- **REQ-U1** 시스템은 영상 처리에 ffmpeg/ffprobe CLI만 subprocess로 사용해야 한다 (외부 Python 라이브러리 없음).
- **REQ-U2** 시스템은 모든 CLI 옵션을 argparse로 관리해야 한다.
- **REQ-U3** 시스템은 ffmpeg 출력을 UTF-8로 디코딩해야 한다 (Windows cp949 환경 대응).

### Event-driven
- **REQ-E1** WHEN 입력 영상이 주어지면, 시스템은 ffprobe로 전체 duration을 확인해야 한다.
- **REQ-E2** WHEN duration을 확인하면, 시스템은 `silencedetect` 필터로 무음 구간(start/end)을 감지해야 한다. 영상이 무음으로 끝나 `silence_end`가 없으면 end는 duration으로 본다.
- **REQ-E3** WHEN 무음 구간이 감지되면, 시스템은 각 무음 구간을 앞쪽은 `margin_after`, 뒤쪽은 `margin_before`만큼 줄이고 그 여집합을 유지 구간으로 계산해야 한다. 영상 맨 앞/뒤에 붙은 무음은 음성이 없는 쪽에 margin을 적용하지 않는다.
- **REQ-E4** WHEN 유지 구간이 계산되면, 시스템은 각 구간을 임시 파일로 추출한 뒤 concat demuxer로 병합해야 한다.
- **REQ-E5** WHEN 처리가 끝나면, 시스템은 원본 길이, 결과 길이, 단축된 시간을 출력해야 한다.
- **REQ-E6** IF `--output`이 없으면, THEN 시스템은 입력과 같은 폴더에 `{원본이름}_no_silence.mp4`로 저장해야 한다.
- **REQ-E7** IF `--reencode`가 지정되면, THEN 시스템은 구간을 libx264/aac로 재인코딩해야 한다. 지정되지 않으면 `-c copy`를 사용한다.
- **REQ-E8** IF ffmpeg 또는 ffprobe가 PATH에 없으면, THEN 시스템은 설치 안내를 출력하고 종료 코드 1로 끝나야 한다.
- **REQ-E9** IF 무음 구간이 없으면, THEN 시스템은 "무음 구간 없음"을 출력하고 원본을 출력 경로로 복사해야 한다.
- **REQ-E10** IF subprocess가 실패하면, THEN 시스템은 실행한 명령과 stderr를 출력하고 종료 코드 1로 끝나야 한다.
- **REQ-E11** IF 입력 파일이 없거나 오디오 트랙이 없으면, THEN 시스템은 이유를 출력하고 종료 코드 1로 끝나야 한다.
- **REQ-E12** IF 유지 구간이 하나도 없으면(전체 무음), THEN 시스템은 threshold 조정 안내를 출력하고 종료 코드 1로 끝나야 한다.

### State-driven
- **REQ-S1** WHILE 처리 중인 동안, 시스템은 임시 파일을 전용 임시 디렉터리에 두고 종료 시(예외 포함) 삭제해야 한다.

### Unwanted
- **REQ-N1** 시스템은 입력 파일을 덮어쓰면 안 된다 (출력 경로 = 입력 경로면 에러).
- **REQ-N2** 시스템은 0.05초 미만의 빈 구간을 추출하면 안 된다.

### Optional
- **REQ-O1** 가능하다면, 시스템은 copy 모드에서 키프레임 단위 컷으로 정확도가 떨어질 수 있음을 안내해야 한다.

## 제약 조건
- Python ≥ 3.12, 표준 라이브러리만 사용, uv로 실행.
- ffmpeg/ffprobe CLI (개발 환경 검증 버전: 9.0.2).

## 의존성
- ffmpeg / ffprobe (외부 실행 파일, 사용자가 설치)
