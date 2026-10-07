# Claude Code 개발 가이드라인 (FSD + SPEC + TDD)

Claude Code가 일관된 구조로 코드를 작성하도록 돕는 **프로젝트 지침 문서(`CLAUDE.md`) 템플릿**입니다.
언어·프레임워크와 상관없이 쓸 수 있도록 다음 네 가지 규칙을 하나로 묶었습니다.

- **아키텍처**: Feature-Sliced Design(FSD)을 일반화해 백엔드, CLI, 프론트엔드 어디에나 적용
- **외부 API 사용 규칙**: 기억에 의존하지 않고 공식 문서를 먼저 확인
- **SPEC 기반 개발**: EARS 요구사항, 구현 계획, 인수 기준을 문서로 남겨 세션이 끊겨도 맥락 유지
- **테스팅**: 신규 기능은 TDD, 기존 코드 수정은 ANALYZE → PRESERVE → IMPROVE 사이클

전체 내용은 [클로드.md](클로드.md)에 있습니다.

---

## 사용 방법

1. [클로드.md](클로드.md)를 프로젝트 루트에 `CLAUDE.md`라는 이름으로 복사합니다.
   ```bash
   cp 클로드.md /path/to/your-project/CLAUDE.md
   ```
2. Claude Code를 프로젝트 디렉토리에서 실행하면 이 지침이 자동으로 적용됩니다.
3. 프로젝트 규모에 맞게 레이어나 세그먼트를 추가하거나 빼서 씁니다.

---

## 핵심 내용 요약

### 1. 아키텍처: Feature-Sliced Design

코드를 **레이어 → 슬라이스 → 세그먼트** 세 단계로 나눕니다.

```
app/        ← 진입점, 전역 설정, 라우팅, DI
pages/      ← 엔드포인트 / CLI 커맨드 / 화면 단위
features/   ← 재사용되는 기능 (생성, 검증, 알림 등)
entities/   ← 비즈니스 도메인 모델 (user, order 등)
shared/     ← 비즈니스와 무관한 공통 코드
```

| 원칙 | 설명 |
|------|------|
| 단방향 의존성 | 위 레이어는 아래 레이어만 참조할 수 있습니다 (`app → pages → features → entities → shared`) |
| 슬라이스 격리 | 같은 레이어에 있는 슬라이스끼리는 서로 import하지 않습니다 |
| 목적 기반 네이밍 | `utils/`, `helpers/` 대신 `api/`, `model/`, `ui/`, `lib/`, `config/`처럼 목적을 드러냅니다 |
| 상향식 배치 | 코드는 가장 좁은 범위(`pages/`)에 먼저 두고, 재사용 범위가 넓어질 때만 아래 레이어로 옮깁니다 |
| Public API | 슬라이스 밖에는 index 파일로 공개한 것만 노출하고, 내부 구현을 직접 import하지 않습니다 |

### 2. 외부 API·라이브러리 참조 규칙

외부 API, SDK, 클라우드 설정, DB 드라이버, 인증 코드를 작성하기 전에 **공식 문서를 웹검색으로 확인**합니다.

- 우선순위: 공식 문서 > GitHub README > 공식 블로그 > 커뮤니티
- 확인할 항목: 최신 시그니처, deprecated 여부, 인증 방식, rate limit
- 참고한 문서 URL은 코드 주석으로 남깁니다
- 표준 라이브러리와 내부 모듈은 검색하지 않아도 됩니다

### 3. SPEC 기반 개발

기능 하나마다 `specs/[SPEC-ID]/` 아래에 파일 3개를 만든 뒤 구현을 시작합니다.

| 파일 | 내용 |
|------|------|
| `spec.md` | EARS 형식 요구사항, 제약 조건, 의존성 |
| `plan.md` | 작업 분해, 기술 스택, 위험 분석 |
| `acceptance.md` | Given/When/Then 시나리오, 엣지 케이스, 품질 게이트 |

EARS 요구사항 유형은 Ubiquitous, Event-driven, State-driven, Unwanted, Optional 다섯 가지입니다.

### 4. 테스팅

| 상황 | 사이클 |
|------|--------|
| 신규 기능 | **RED → GREEN → REFACTOR** (TDD) |
| 기존 코드 수정 | **ANALYZE → PRESERVE → IMPROVE** |

- `acceptance.md`의 인수 기준을 테스트로 구현합니다.
- 테스트는 해당 슬라이스 안의 `test/` 세그먼트에 둡니다.
- DB, 외부 API 같은 외부 의존성은 모킹합니다.

---

## 적용 예시

[video-editor/](video-editor/)는 이 지침에 따라 만든 Python 영상 후처리 도구입니다 (무음 구간 제거, 간투사 제거).

```
video-editor/
  specs/
    SPEC-001-remove-silence/
      spec.md
      acceptance.md
  src/
    pages/
      remove_silence/
        test/
    shared/
      api/ffmpeg.py
      test/
```

---

## 적용 팁

- 모든 레이어를 다 쓸 필요는 없습니다. 작은 프로젝트는 `pages/` + `shared/`만으로 시작해도 충분합니다.
- 같은 도메인의 페이지가 3개 이상이 되면 슬라이스 그룹을 고려합니다.
- 세그먼트에 파일이 1~2개뿐이면 디렉토리 없이 평평하게 둬도 됩니다.
- 의존성 규칙 위반은 린터나 코드 리뷰로 잡아냅니다.
