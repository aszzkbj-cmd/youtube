---
name: remove-silence
description: 영상에서 무음 구간을 감지해 잘라내는 스킬 (ffmpeg silencedetect, video-editor/remove_silence.py 사용). "무음 제거", "무음 잘라줘", "조용한 부분 없애줘", "말 안 하는 구간 삭제", "silence removal" 등 영상의 빈/조용한 구간을 없애달라는 요청에 사용한다. 간투사 제거까지 함께 원하면 edit-video 스킬을 쓴다.
argument-hint: <영상 경로> [옵션]
---

# 영상 무음 구간 제거

`video-editor/remove_silence.py`(SPEC-001)를 실행해 무음 구간을 잘라낸다. 로직을 새로 짜지 말고 이 스크립트를 호출한다.

입력: $ARGUMENTS

## 실행

1. 입력 영상 경로를 **절대 경로**로 바꾼다 (`--directory`가 작업 폴더를 바꾸므로 상대 경로는 깨진다). 경로가 없으면 사용자에게 묻는다.
2. 워크스페이스 루트(`C:\Users\USER\Desktop\클로드`)에서 실행한다:

```powershell
uv run --directory video-editor python remove_silence.py "<절대경로\영상.mp4>" --reencode
```

- `--reencode`를 기본으로 붙인다. 빼면 copy 모드라 키프레임 단위로 잘려 컷 위치가 어긋난다. 사용자가 "빠르게"를 원할 때만 뺀다.
- 결과 기본 경로: `{원본이름}_no_silence.mp4` (원본과 같은 폴더)

## 옵션 (사용자 요청에 맞춰 조정)

| 옵션 | 기본값 | 언제 바꾸나 |
|------|--------|-------------|
| `--output, -o` | `{원본}_no_silence.mp4` | 저장 위치 지정 시 |
| `--threshold` | -35 dB | 잡음이 많아 무음이 안 잡히면 높임(예: -30), 작은 목소리가 잘리면 낮춤(예: -40) |
| `--min-silence` | 0.5 s | 짧은 쉼까지 자르려면 줄이고, 자연스러운 호흡을 남기려면 늘림 |
| `--margin-before` | 0.15 s | 말 시작이 잘리면 늘림 |
| `--margin-after` | 0.3 s | 말끝이 잘리면 늘림 |

## 결과 보고

스크립트 출력에서 원본 길이, 결과 길이, 단축 시간(%), 무음 구간 수, 저장 위치를 요약해 전달한다. `[오류]` 메시지가 나오면 그 내용을 그대로 알리고 안내된 조치를 제안한다 (예: "영상 전체가 무음" → `--threshold` 낮추기).
