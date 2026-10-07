---
name: edit-video
description: 영상 통합 후처리 스킬. 간투사 제거 후 무음 제거를 한 번에 실행한다 (video-editor의 remove_fillers.py → remove_silence.py). "영상 편집해줘", "영상 다듬어줘", "강의 영상 정리", "영상 후처리", "쓸데없는 부분 다 잘라줘", "간투사랑 무음 둘 다 제거" 등 영상을 전체적으로 깔끔하게 만들어 달라는 요청에 사용한다. 한 가지만 원하면 remove-fillers 또는 remove-silence를 쓴다.
argument-hint: <영상 경로> [옵션]
---

# 영상 통합 후처리 (간투사 제거 → 무음 제거)

간투사를 먼저 잘라내야 그 자리에 남은 틈과 원래 있던 무음이 2단계에서 함께 정리된다. 그래서 **간투사 제거 → 무음 제거** 순서를 지킨다. 두 스크립트를 순서대로 호출하고, 로직은 새로 짜지 않는다.

입력: $ARGUMENTS

## 사전 확인

- 1단계(간투사)에는 OpenAI API 키가 필요하다 (환경변수 `OPENAI_API_KEY` 또는 `video-editor/.env`). 없으면 `.env.example`을 `.env`로 복사해 키를 넣도록 안내하고 멈춘다.
- 입력 경로를 **절대 경로**로 바꾼다. 경로가 없으면 사용자에게 묻는다.
- 파일을 찾을 수 없다고 나오면 추측하지 말고, 해당 폴더에서 파일 목록을 확인해 실제 이름(특수문자, 공백, 괄호 포함)을 맞춘다.

## 실행 (워크스페이스 루트 `C:\Users\USER\Desktop\클로드`에서)

`<dir>`는 원본 폴더, `<stem>`은 확장자를 뺀 원본 파일 이름이다.

**1단계: 간투사 제거**
```powershell
uv run --directory video-editor python remove_fillers.py "<dir>\<stem>.mp4" -o "<dir>\<stem>_no_fillers.mp4"
```

**2단계: 무음 제거** (1단계가 성공했을 때만)
```powershell
uv run --directory video-editor python remove_silence.py "<dir>\<stem>_no_fillers.mp4" -o "<dir>\<stem>_edited.mp4" --reencode
```

- **순서를 바꾸지 않는다.** 1단계가 실패했다고 무음 제거를 먼저 돌리지 않는다. 무음 제거 결과에 간투사 제거를 하면 간투사를 잘라낸 자리의 틈이 정리되지 않고 그대로 남는다.
- 1단계가 `[오류]`로 끝나면 2단계를 실행하지 말고 멈춘다. 대응은 remove-fillers 스킬의 "실패 시"를 따른다. 사용자가 "무음 제거만이라도 해 줘"라고 하면 그때만 2단계를 원본에 단독으로 실행한다.
- 전사가 모두 끝나면 `{원본}.transcript.json`에 캐시되어, 다시 실행해도 과금되지 않는다. 단, 중간 청크에서 실패하면 캐시가 남지 않아 다음 실행 때 처음부터 다시 전사한다.
- 1단계에서 간투사가 0개면 스크립트가 원본을 복사하므로 그대로 2단계로 넘어간다.
- 사용자가 무음만 또는 간투사만 원한다고 하면 해당 단계만 실행한다.
- 단계별 옵션(threshold, margin 등)은 remove-silence, remove-fillers 스킬의 옵션표를 따른다.

## 결과 보고

| 단계 | 길이 | 단축 |
|------|------|------|
| 원본 | … | - |
| 간투사 제거 후 | … | … (간투사 N개) |
| 무음 제거 후 (최종) | … | … (무음 구간 M개) |

마지막에 총 단축 시간(%)과 최종 파일 `<stem>_edited.mp4`의 경로를 알린다. 중간 파일 `<stem>_no_fillers.mp4`는 남겨 두었다고 알리고, 사용자가 원하면 지운다.
