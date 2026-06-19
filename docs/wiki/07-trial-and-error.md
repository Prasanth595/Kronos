# 시행착오 기록 (Trial and Error)

> 실패한 시도와 그 원인, 그리고 (있다면) 해결책. 같은 실수 두 번 안 하기 위한 기록.

## 학습 (Finetune)

### TE-01 · validation OOM (2026-05-14, commit 7742cb8)
- **증상**: tokenizer 단계 약 75% 진행 후 validation 진입 시 GPU VRAM 16 GiB 초과 → CUDA OOM crash
- **원인**: validation batch size 가 학습 batch size 와 동일하게 큼
- **해결책 (사용자 채울 자리)**:
  - 시도 1: (사용자 채울 자리)
  - 시도 2: (사용자 채울 자리)
- **교훈**: validation 도 별도 batch size 설정 필요 — 학습보다 작게 (메모리 헤드룸 확보)
- **현재 상태**: tokenizer 49% 시점 결과는 보존됨 (commit `7742cb8`). 재학습 미진행

### TE-02 · (사용자가 다른 시행착오 추가)
- ...

## 데이터

### TE-D1 · (사용자 작성 영역)
- 한국어 컬럼명 처리 관련 경험
- ...

## 대시보드 / 프론트엔드

### TE-F1 · `dist/` 글로벌 .gitignore 충돌
- **증상**: `webui/static/v2/dist/` 디렉토리가 자동으로 git ignore 됨
- **원인**: 프로젝트 루트 `.gitignore` 의 Python 패키징용 `dist/` 패턴이 Vite 빌드 산출물에도 매칭
- **해결**: `.gitignore` 에 `!webui/static/v2/dist/` 와 `!webui/static/v2/dist/**` 명시 예외 추가 (commit `2695151`)
- **교훈**: 다국어 프로젝트 (Python + JS) 의 `.gitignore` 는 충돌 가능성 항상 확인

### TE-F2 · `lib/` 패턴이 Svelte src/lib 충돌
- **증상**: `webui/v2_src/src/lib/*.ts` 가 자동으로 ignore 됨 → 첫 P1.5 commit 에 누락
- **원인**: 동일 — 루트 `.gitignore` 의 Python `lib/` 패턴
- **해결**: `git add -f` 또는 `.gitignore` 에 negation 추가 — 본 프로젝트는 후자 선택
- **교훈**: Svelte/React 등 `src/lib/` 구조의 프론트엔드를 추가할 때 항상 git status 확인

### TE-F3 · Svelte 5 strict HTML 규칙 — `<tr>` 단독 사용 불가
- **증상**: `<table>` 안에 `<tr>` 바로 두면 svelte-check 가 오류 보고
- **원인**: Svelte 5 의 HTML structure 검증이 엄격해짐 — 브라우저가 `<tbody>` 를 자동 삽입하므로 명시 권장
- **해결**: 모든 `<tr>` 을 `<tbody>` 로 감쌈
- **교훈**: Svelte 5 마이그레이션 시 HTML structure 검증 강화 — 명시적 wrapping 필요

### TE-F4 · ECharts theme 전환 시 색상 안 바뀜
- **증상**: light → dark 토글해도 차트 색이 그대로
- **원인**: ECharts 옵션이 한 번 setOption 된 후 CSS 변수 변화를 인지하지 못함
- **해결**: `theme` store 변화 시 `$derived.by(() => { void currentTheme; getComputedStyle(...) })` 패턴으로 palette 재계산 강제
- **교훈**: 차트 라이브러리는 일반적으로 CSS 변수와 무관 — 명시적 setOption 재호출 필요

### TE-F5 · ECharts loss curve x축에 빈 공간이 95%
- **증상**: 데이터가 step 2.4M~2.5M 구간에만 있는데 x축이 0~3M 까지 표시되어 차트 빈 공간만 보임
- **원인**: ECharts xAxis 의 `scale` 옵션 기본값이 `false` 라 0부터 시작
- **해결**: `xAxis: { scale: true, min: 'dataMin', max: 'dataMax' }` 명시
- **교훈**: 학습 곡선처럼 일부 구간만 데이터 있을 때는 자동 스케일 명시 필수

### TE-F6 · KST 표시가 `-` 만 나옴
- **증상**: `/api/training/status` 응답에 `eta_seconds=178976` 있는데 W2/W4 가 `-` 표시
- **원인**: JS 가 `d.eta_seconds` (top-level) 를 읽었는데 실제로는 `d.latest_stage.eta_seconds` (중첩)
- **해결**: `const latest = d.latest_stage || {}` 후 `latest.eta_seconds` 읽음 (commit `4e54f45`)
- **교훈**: API 응답 구조를 정확히 검증 — top-level 가정 금지

## 빌드 / 도구

### TE-B1 · CSS @import 순서 경고
- **증상**: Vite 빌드 시 `@import must precede all other statements` 경고 → CSS 크기가 작아짐 (38KB → 11KB)
- **원인**: `@tailwind` 디렉티브 뒤에 `@import` 작성
- **해결**: `@import` 를 파일 최상단에 위치
- **교훈**: PostCSS/Vite 처리 순서는 @import 가 항상 먼저

### TE-B2 · TypeScript strict 모드와 Svelte 5 reactive 충돌
- **증상**: `$state<any>()` + subscribe 패턴이 `noImplicitAny` 오류
- **해결**: `tsconfig.json` 에 `strict: false`, `noImplicitAny: false` 설정
- **교훈**: 초기 프로토타입은 strict 비활성화 → 안정화 후 점진 활성화

## 라우팅 / 백엔드

### TE-R1 · Flask Blueprint catch-all 라우트 위험
- **증상**: 글로벌 `/<path:p>` catch-all 추가 시 모든 `/api/*` 가 그쪽으로 매칭
- **원인**: Flask 라우트 매칭은 가장 구체적인 것 우선이지만 catch-all 은 만능 매치
- **해결**: catch-all 은 반드시 prefix 내부에만 (`/v2/<path:subpath>` 처럼)
- **교훈**: Plan 의 명시적 금지 사항 §8 [NEW] 두 번째 — 글로벌 catch-all 절대 금지

---

*기여 환영. 시행착오를 만나면 즉시 기록 → 다음 사람(또는 미래의 자신)이 같은 실수 반복 안 함.*
