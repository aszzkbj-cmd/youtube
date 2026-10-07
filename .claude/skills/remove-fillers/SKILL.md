---
name: remove-fillers
description: 영상에서 간투사(말버릇, filler words)를 감지해 잘라내는 스킬 (OpenAI Whisper 전사 + video-editor/remove_fillers.py 사용). "간투사 제거", "말버릇 제거", "filler 제거", "음/어/이제/그래서 같은 군더더기 말 빼줘", "불필요한 말 삭제" 등 영상 속 군더더기 말을 없애달라는 요청에 사용한다. 무음 제거까지 함께 원하면 edit-video 스킬을 쓴다.
argument-hint: <영상 경로> [옵션]
---

# 영상 간투사 제거

`video-editor/remove_fillers.py`(SPEC-002)를 실행한다. Whisper로 단어별 타임스탬프를 얻고 `video-editor/fillers.txt`에 있는 단어 가운데 **독립적으로 쓰인 것만** 잘라낸다. 로직을 새로 짜지 말고 이 스크립트를 호출한다.

입력: $ARGUMENTS

## 사전 확인

- **OpenAI API 키**: 환경변수 `OPENAI_API_KEY`, `video-editor/.env`, `--api-key` 중 하나에 있어야 한다. 없으면 `video-editor/.env.example`을 `.env`로 복사해 키를 넣도록 안내하고 멈춘다. 키를 대신 만들거나 추측하지 않는다.
- 같은 영상을 다시 처리하면 `{원본}.transcript.json` 캐시를 재사용하므로 API를 다시 부르지 않는다.

## 전사 방식 (코드에 이미 들어 있음, 따로 조치하지 않는다)

- 오디오를 약 5분(≈1.2MB) 청크로 나눠 올린다. 경계는 5분 지점 직전의 무음 가운데라 문장 중간을 자르지 않는다.
- 직전 청크 텍스트 끝 100자를 `prompt`로 넘겨 문맥을 잇는다.
- 연결 오류·429·5xx는 SDK가 청크마다 최대 4번 재시도한다.
- 그래서 같은 명령을 그대로 다시 실행해도 결과가 달라질 가능성은 낮다. 실패하면 아래 "실패 시"를 따른다.

## 실행

1. 입력 영상 경로를 **절대 경로**로 바꾼다. 경로가 없으면 사용자에게 묻는다.
2. 워크스페이스 루트(`C:\Users\USER\Desktop\클로드`)에서 실행한다:

```powershell
uv run --directory video-editor python remove_fillers.py "<절대경로\영상.mp4>"
```

- 기본이 재인코딩 모드라 컷이 정확하다. `--no-reencode`는 짧은 컷에서 결과가 오히려 길어질 수 있어 권하지 않는다.
- 결과 기본 경로: `{원본이름}_no_fillers.mp4`
- 사용자가 "어떤 게 잘리는지 먼저 보고 싶다"고 하면 `--dry-run`으로 감지 목록과 예상 길이만 보여 준다.

## 옵션

| 옵션 | 기본값 | 용도 |
|------|--------|------|
| `--output, -o` | `{원본}_no_fillers.mp4` | 저장 위치 |
| `--fillers-file` | `video-editor/fillers.txt` | 다른 간투사 사전 사용 |
| `--margin-before` / `--margin-after` | 0.1 / 0.15 s | 간투사 앞뒤로 함께 잘라낼 여백 |
| `--padding` | 0.05 s | 이어 붙이는 구간 사이에 넣을 짧은 무음 |
| `--dry-run` | - | 영상을 만들지 않고 감지 결과만 출력 |
| `--no-cache` | - | 저장된 전사를 무시하고 Whisper를 다시 호출 (API 비용 발생) |

간투사 목록을 바꿔 달라는 요청에는 `video-editor/fillers.txt`(한 줄에 한 단어)를 수정한다.

## 결과 보고

감지된 간투사 수, 단어별 횟수, 원본/결과 길이, 단축 시간, 저장 위치를 요약한다.

## 실패 시

- `[오류]` 메시지(몇 번째 청크에서 실패했는지 포함)를 그대로 전달하고 멈춘다. 다른 작업으로 우회하지 않는다.
- `API 키` 오류 → `video-editor/.env`의 키 확인을 안내한다.
- 연결/SSL 오류(`APIConnectionError`, `SSL`, `BAD_RECORD_MAC`) → 이미 재시도까지 거친 결과다. 같은 명령을 바로 반복하지 말고, VPN·프록시·백신의 HTTPS 검사를 꺼 본 뒤 다시 시도하도록 안내한다.
- 파이썬 traceback이 그대로 나오면 스크립트 버그다. 원인을 찾아 보고하고, 코드를 고치려면 사용자에게 먼저 묻는다.
