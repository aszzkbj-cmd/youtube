# SPEC-001 구현 계획

## 기술 스택
- Python 3.12+ 표준 라이브러리 (`argparse`, `subprocess`, `tempfile`, `shutil`, `re`, `unittest`)
- ffmpeg / ffprobe CLI
- uv (실행 및 가상환경)

## 구조 (FSD, 소규모라 `app + pages + shared`만 사용)

```
remove_silence.py                ← 루트 실행 파일 (CLI 명세 유지용, src를 path에 추가 후 app 호출)
src/
  app/__init__.py                ← 진입점: 커맨드를 pages로 연결
  pages/remove_silence/          ← 슬라이스: 무음 제거 커맨드
    __init__.py                  ← Public API: main
    cli.py                       ← (ui) argparse, 흐름 제어, 결과 출력
    model.py                     ← (model) 기본값, 구간 타입, 로그 파싱, 유지 구간 계산
    api.py                       ← (api) 이 커맨드 전용 ffmpeg 호출: 감지/추출/병합
    test/                        ← 단위 테스트 + 인수 테스트
  shared/api/                    ← ffmpeg/ffprobe 공통 래퍼 (비즈니스 무관)
    __init__.py                  ← Public API
    ffmpeg.py                    ← run, require_tools, probe_duration, has_audio, 예외
  shared/test/
```

> SPEC-002에서 구간 추출/병합(`build_extract_command`, `extract_segment`, `concat_*`)은 `shared/api/segments.py`로,
> `format_time`은 `shared/lib/timefmt.py`로 이동했다.
> 이후 SPEC-002 청크 경계 계산에서 무음 감지를 함께 쓰게 되어 `detect_silences`·`parse_silences`도
> `shared/api/silence.py`로 이동했고, `pages/remove_silence/api.py`는 삭제했다 (동작 변경 없음).

배치 근거 (상향식):
- 구간 계산·감지·추출·병합은 현재 무음 제거에서만 쓰므로 `pages/remove_silence/`에 둔다.
- subprocess 실행, 도구 확인, duration/오디오 확인은 이후 편집 기능에서도 쓸 범용 외부 도구 래퍼이므로 `shared/api/`에 둔다.
- `features/`, `entities/`는 재사용이 생길 때 도입한다.
- 세그먼트가 파일 1개라서 `api.py`, `model.py`, `cli.py`처럼 플랫하게 둔다.

`shared`는 `sys.exit`를 호출하지 않고 예외(`ToolNotFoundError`, `CommandError`)를 던진다.
종료 코드와 메시지 출력은 page(cli)가 결정한다.

## 작업 분해
1. SPEC 3종 작성 (spec / plan / acceptance)
2. PRESERVE: 기존 단일 파일 구현의 동작을 단위 테스트로 고정 (구간 계산, 로그 파싱)
3. `shared/api/ffmpeg.py` 분리 + subprocess 모킹 테스트
4. `pages/remove_silence/{model,api,cli}.py` 분리 + 명령 구성 모킹 테스트
5. 인수 테스트: lavfi로 테스트 영상을 생성해 acceptance 시나리오 검증 (ffmpeg 없으면 skip)
6. 루트 `remove_silence.py`를 진입 shim으로 교체, 전체 테스트 실행

## 위험 분석

| 위험 | 영향 | 대응 |
|------|------|------|
| `-c copy`는 키프레임 단위로만 잘림 | 컷 위치가 GOP 길이만큼 어긋남, 무음이 덜 제거됨 (테스트: 기대 2.75s → 3.87s) | copy 모드 실행 시 안내 출력, 정밀 컷은 `--reencode` |
| 입력 옵션 `-to`의 의미가 버전마다 다름 | 구간 길이 오류 | `-ss`(입력) + `-t`(길이) 사용. 공식 문서: `-t`가 `-to`보다 우선 |
| concat 목록의 경로 이스케이프 | Windows 백슬래시·한글·작은따옴표 경로 실패 | 절대경로를 POSIX 슬래시로 바꾸고 `'` → `'\''`, `-safe 0` |
| Windows cp949 콘솔 | ffmpeg 출력 디코딩 실패 | `encoding="utf-8", errors="replace"` |
| 세그먼트 간 코덱/타임베이스 불일치 | concat 실패 또는 싱크 문제 | `--reencode`로 코덱 통일 |
| 오디오 없는 영상 | silencedetect 실패 | ffprobe로 오디오 스트림을 먼저 확인 |

## 참고 문서
- silencedetect: https://ffmpeg.org/ffmpeg-filters.html#silencedetect
- concat demuxer: https://ffmpeg.org/ffmpeg-formats.html#concat-1
- `-ss` / `-t` / `-to` / `-map`: https://ffmpeg.org/ffmpeg.html#Main-options
- `avoid_negative_ts`: https://ffmpeg.org/ffmpeg-formats.html#Format-Options
- ffprobe `-show_entries`: https://ffmpeg.org/ffprobe.html
