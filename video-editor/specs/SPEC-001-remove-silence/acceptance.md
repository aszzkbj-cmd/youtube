# SPEC-001 인수 기준

테스트 영상은 ffmpeg lavfi로 생성한다.
- `speech.mp4`: 6초, 오디오 = [톤 1초][무음 2초][톤 1초][무음 2초], 영상 GOP 1초
- `tone.mp4`: 4초, 처음부터 끝까지 톤
- `noaudio.mp4`: 3초, 오디오 트랙 없음

## 시나리오

### AC-1 무음 제거 (재인코딩) — REQ-E1~E5, E7
- **Given** `speech.mp4`와 기본 설정
- **When** `--reencode`로 실행하면
- **Then** 결과 길이는 2.75초 ±0.15초이다 (유지 구간 [0, 1.3] + [2.85, 4.3])
- **And** 원본/결과/단축 시간이 출력된다

### AC-2 무음 제거 (copy 모드) — REQ-E7, REQ-O1
- **Given** `speech.mp4`와 기본 설정
- **When** 옵션 없이 실행하면
- **Then** 출력 파일이 생성되고 결과 길이가 원본보다 짧다
- **And** 키프레임 정확도 안내가 출력된다

### AC-3 기본 출력 파일명 — REQ-E6
- **Given** `--output` 없이
- **When** `speech.mp4`를 처리하면
- **Then** 같은 폴더에 `speech_no_silence.mp4`가 생긴다

### AC-4 무음 없음 — REQ-E9
- **Given** `tone.mp4`
- **When** 실행하면
- **Then** "무음 구간 없음"이 출력되고, 출력 파일은 원본과 바이트 단위로 같다

### AC-5 오디오 없음 — REQ-E11
- **Given** `noaudio.mp4`
- **When** 실행하면
- **Then** 종료 코드 1, "오디오 트랙" 안내가 출력된다

### AC-6 입력 파일 없음 — REQ-E11
- **Given** 존재하지 않는 경로
- **When** 실행하면
- **Then** 종료 코드 1, "찾을 수 없습니다"가 출력된다

### AC-7 전체 무음 — REQ-E12
- **Given** `speech.mp4`와 `--threshold 10`
- **When** 실행하면
- **Then** 종료 코드 1, threshold 조정 안내가 출력되고 출력 파일은 생기지 않는다

### AC-8 ffmpeg 미설치 — REQ-E8
- **Given** PATH에서 ffmpeg를 찾을 수 없을 때 (모킹)
- **When** 실행하면
- **Then** 종료 코드 1, 설치 안내(`winget install Gyan.FFmpeg`)가 출력된다

### AC-9 subprocess 실패 — REQ-E10
- **Given** ffmpeg가 0이 아닌 종료 코드를 반환할 때 (모킹)
- **When** 실행하면
- **Then** 종료 코드 1, 실행한 명령과 stderr가 출력된다

### AC-10 입력 덮어쓰기 방지 — REQ-N1
- **Given** `--output`이 입력과 같은 경로
- **When** 실행하면
- **Then** 종료 코드 1, 입력 파일은 변경되지 않는다

### AC-11 임시 파일 정리 — REQ-S1
- **Given** 정상 실행 또는 실패
- **When** 처리가 끝나면
- **Then** `remove_silence_*` 임시 디렉터리가 남지 않는다

### AC-12 한글/공백 경로 — REQ-E4
- **Given** 경로에 한글과 공백이 있는 입력
- **When** 실행하면
- **Then** 정상 처리된다

## 엣지 케이스 (단위 테스트)
- 영상 시작/끝에 붙은 무음: 음성이 없는 쪽에 margin 미적용
- margin 합보다 짧은 무음: 제거하지 않음
- margin 적용 후 0.05초 미만인 유지 구간: 버림
- `silence_end` 없이 끝나는 로그: end = duration
- 음수 `silence_start`: 0으로 클램핑
- 로그 구분자 `:`와 `=` 모두 지원
- concat 목록: 작은따옴표·백슬래시 경로 이스케이프

## 품질 게이트
- `uv run python -m unittest discover -s src -t src` 전체 통과
- 인수 테스트는 ffmpeg가 있는 환경에서 skip 없이 통과
- `src/shared`는 `src/pages`를 import하지 않는다 (의존성 방향)
