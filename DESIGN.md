# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-05-20
- Primary product surfaces:
  - `http://127.0.0.1:5070/`
  - `http://127.0.0.1:5070/training`
  - STOM/Kronos 학습 상태, GPU 상태, 예측/실제값 비교, 데이터 진단 대시보드
- Evidence reviewed:
  - `webui/v2_src/src/styles/core.css`
  - `webui/v2_src/src/styles/components.css`
  - `webui/v2_src/src/tabs/LiveTrainingTab.svelte`
  - `webui/v2_src/src/tabs/StomDiagnosticsTab.svelte`
  - `webui/v2_src/src/layout/HeroStrip.svelte`
  - `webui/training_monitor.py`
  - `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json`

## Brand
- Personality: 차분하고 신뢰 가능한 ML 운영 도구, 숫자 중심이지만 비전문가도 빠르게 이해할 수 있는 설명형 대시보드.
- Trust signals: 실제 데이터 범위, 학습 단계, ETA, GPU, checkpoint, 검증 지표를 숨기지 않고 카드와 표로 노출.
- Avoid: 과장된 수익 표현, “정확도 보장” 같은 단정, 맥락 없는 원시 로그만 던지는 화면, 페이지마다 다른 색/간격/타이포그래피.

## Product goals
- Goals:
  - STOM tick/1초봉 데이터를 Kronos 파인튜닝에 어떤 범위로 사용 중인지 즉시 확인.
  - 장시간 학습 중 현재 단계, 속도, ETA, GPU, 손실 추이를 웹에서 계속 감시.
  - 학습 완료 후 실제값과 예측값을 종목/전체 통계로 비교할 수 있는 흐름을 유지.
- Non-goals:
  - 실거래 자동 주문 판단을 대시보드가 단독으로 보장하지 않는다.
  - 모델 성능을 검증하지 않은 상태에서 투자 의사결정으로 직접 연결하지 않는다.
- Success signals:
  - 사용자가 “지금 무엇을 학습 중인지”, “얼마나 남았는지”, “어떤 데이터 범위인지”를 10초 안에 이해.
  - 모든 주요 수치는 API 근거와 로그 근거로 재현 가능.

## Personas and jobs
- Primary personas:
  - STOM/Kronos 학습을 운영하는 개발자/트레이더.
  - 장시간 GPU 학습을 감시하고 중간 실패를 빠르게 파악해야 하는 사용자.
- User jobs:
  - 데이터 범위와 feature가 의도한 전체 STOM tick 학습과 일치하는지 확인.
  - tokenizer/predictor 진행률, ETA, checkpoint 준비 상태를 추적.
  - 학습 완료 후 예측 품질을 그래프와 통계로 검증.
- Key contexts of use:
  - 로컬 워크스테이션 RTX 4080 SUPER/Threadripper 환경.
  - 장시간 학습 중 브라우저와 Codex 대화에서 병행 모니터링.

## Information architecture
- Primary navigation: 좌측 사이드바 중심의 탭형 구조.
- Core routes/screens:
  - `/`: 개요/홈.
  - `/training`: 실시간 학습 대시보드.
  - STOM 진단/예측 비교 관련 탭: 데이터 품질, 예측 결과, 통계 요약.
- Content hierarchy:
  1. 현재 학습 상태와 핵심 지표.
  2. 학습 데이터 범위/feature/분할 정보.
  3. 손실 곡선, 변동성, ETA, GPU, 로그.
  4. 학습 완료 후 예측-실제 비교와 종목별 통계.

## Design principles
- Principle 1: “근거 먼저” — 각 수치가 어떤 run/report/log에서 나온 것인지 숨기지 않는다.
- Principle 2: “장시간 감시 친화” — 새로고침과 상태 변화가 눈에 잘 보이되 시끄럽지 않게 표현한다.
- Principle 3: “한글 우선, 약어 보조” — 사용자가 보는 UI는 한글 설명을 우선하고, step/GPU/ETA 같은 약어는 보조로 유지한다.
- Tradeoffs:
  - 원시 정보량이 많으므로 첫 화면은 요약 카드, 상세는 표/칩/로그로 분리한다.
  - 모델 성능은 방향성/검증 지표로 표현하고 투자 판단 단정은 피한다.

## Visual language
- Color: 기존 토큰을 그대로 사용한다. 메인 포인트는 민트/틸 `--accent`, 주의/보완 설명은 warm/warn 계열.
- Typography: Pretendard + Malgun Gothic fallback, 숫자는 JetBrains Mono/D2Coding과 tabular number 사용.
- Spacing/layout rhythm: 16px 카드 간격, 20px 카드 padding, 큰 화면은 4열/3:1 grid, 작은 화면은 1열로 축소.
- Shape/radius/elevation: `--r-lg`, `--r-pill`, `--shadow-glow`, `--border` 기반의 부드러운 카드.
- Motion: 실시간 상태는 pulse/soft transition만 사용, 장시간 감시 화면에서 과한 애니메이션 금지.
- Imagery/iconography: 추가 이미지보다 badge, dot, chip, sparkline, chart로 설명.

## Components
- Existing components to reuse:
  - `.card`, `.metric`, `.pill`, `.text-eyebrow`, `.text-caption`, `.text-mono`, `.tnum`
  - `W3LossCurve`, `W4EtaTimeline`, `W5GpuSparkline`, `W6LossVolatility`, `W9LogTail`
- New/changed components:
  - `/training` 상단 데이터 범위 요약 카드: STOM 2025, 1초봉, 09:00~09:30, lookback/pred, split, feature를 표시.
- Variants and states:
  - 데이터 요약 사용 가능: accent 카드.
  - report 미탐지/불완전: warn pill과 간단한 안내.
  - 진행 중: live badge와 ETA/step 유지.
- Token/component ownership:
  - 전역 토큰은 `core.css`, 공통 컴포넌트 스타일은 `components.css`.
  - 탭 단위 특수 레이아웃은 해당 Svelte 파일의 scoped style에 둔다.

## Accessibility
- Target standard: WCAG 2.1 AA 수준의 대비와 키보드 포커스 유지.
- Keyboard/focus behavior: 탭/버튼은 `:focus-visible`을 유지하고 포커스 outline을 제거하지 않는다.
- Contrast/readability: dark/light theme 모두 `--fg`, `--muted`, `--accent` 토큰만 사용.
- Screen-reader semantics: section, table, header, caption성 텍스트를 의미 있게 사용.
- Reduced motion and sensory considerations: 핵심 정보 이해가 animation에 의존하지 않도록 한다.

## Responsive behavior
- Supported breakpoints/devices: 데스크톱 우선, 1200px 이하 2열, 720px/560px 이하 1열.
- Layout adaptations: 요약 카드는 grid에서 stack으로 자연스럽게 변경.
- Touch/hover differences: hover에만 의존하지 않고 모든 상태를 텍스트/색/숫자로 함께 표시.

## Interaction states
- Loading: 수치가 없을 때 `-` 또는 “확인 중”으로 표시.
- Empty: report/API 없음은 경고 카드로 원인과 다음 확인 항목 표시.
- Error: 원시 오류 대신 “데이터 요약을 읽지 못했습니다” + path/근거 일부 표시.
- Success: checkpoint/데이터 요약/실시간 상태는 success 또는 accent pill 사용.
- Disabled: 실행 불가 버튼은 낮은 대비와 설명 텍스트를 함께 제공.
- Offline/slow network, if applicable: 마지막 갱신 시각과 seconds since update를 함께 표시.

## Content voice
- Tone: 짧고 직접적인 한국어, 중요한 숫자는 표기 단위를 붙인다.
- Terminology:
  - “전체 진행률”은 tokenizer+predictor 전체 run 기준.
  - “단계 진행률”은 현재 tokenizer 또는 predictor 내부 기준.
  - “samples”는 sliding window 학습 샘플 수.
  - “rows”는 1초봉으로 정규화된 행 수.
- Microcopy rules:
  - 예측 성능은 “검증 필요”, “비교 가능”, “개선 후보”처럼 보수적으로 표현.
  - 사용자가 혼동한 용어는 한글 설명과 영문 약어를 병기.

## Implementation constraints
- Framework/styling system: Svelte 5 + Vite + repo CSS design tokens.
- Design-token constraints: 새 색상/새 폰트/새 디자인 시스템을 추가하지 않는다.
- Performance constraints: `/training`은 주기 갱신되므로 API 응답은 요약만 반환하고 대형 report 원문은 보내지 않는다.
- Compatibility constraints: Windows 로컬 경로, 한국 시간 표시, 장시간 학습 중 웹 재시작 가능성을 고려.
- Test/screenshot expectations:
  - `npm run build`
  - `python -m py_compile webui/training_monitor.py`
  - `/api/training/status`와 `/training` HTTP 200 확인
  - 가능하면 브라우저에서 `/training` 직접 확인

## Open questions
- [ ] 학습 완료 후 예측-실제 비교 대시보드에서 기본 정렬 기준을 loss/방향정확도/종목별 MAE 중 무엇으로 둘지 결정 필요.
- [ ] 1초봉 pred30/pred60/pred120 비교를 같은 화면에서 토글할지, 별도 실험 페이지로 분리할지 결정 필요.
