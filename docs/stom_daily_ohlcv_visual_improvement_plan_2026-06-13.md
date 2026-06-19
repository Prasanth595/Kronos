# 일봉 OHLCV 대시보드 시각화 개선 연구·적용 계획

**작성일:** 2026-06-13 KST 관측 기준  
**대상:** Kronos `Daily OHLCV` 대시보드 (`http://127.0.0.1:58185/daily-ohlcv`)  
**참고:** STOM 개발 대시보드 (`http://127.0.0.1:8770/ui/`, `C:/System_Trading/STOM/STOM_V.wt-dev`)  
**상태:** 적용 계획 보고서. 아직 수익모델 GO가 아니며, 실거래·브로커·주문 준비 상태가 아니다.

## 1. 결론 요약

현재 Kronos 일봉 대시보드는 D0~D6 증거를 정직하게 노출하지만, 시각화 밀도가 낮다. 표와 KPI 중심이라서 사용자가 다음 질문에 빠르게 답하기 어렵다.

- 어떤 단계가 병목인지?
- 어떤 전략/모델이 왜 탈락했는지?
- RL이 베이스라인보다 얼마나, 어느 구간에서 밀렸는지?
- 워크포워드 fold별 일관성이 있는지?
- 유니버스/가격 보정/누수 위험이 어디에 몰렸는지?
- 다음 실험 우선순위가 무엇인지?

STOM 대시보드는 이 문제를 해결하기 위한 좋은 레퍼런스를 이미 갖고 있다. 특히 **진행도 스트립, 단계 플로우, 적합도/수익/품질 추이, 전 전략 누적곡선, 백테 상세, 세대 이력, Run Compare, Edge/Feature/Correlation 연구랩, Research Wiki, AI Context Pack, 부검/피드백 패널**이 강점이다. Kronos에는 이를 그대로 복사하지 말고, 일봉 연구의 정직성 규칙에 맞게 **검증·실패·잠금 중심 시각화**로 변환해 반영하는 것이 맞다.

최우선 개선 방향은 다음 4개다.

1. **Decision cockpit**: `NO-GO` 이유를 한 화면에서 원인별로 분해한다.
2. **Equity/Drawdown/Benchmark overlay**: D3 baseline, D4 RL, D5 selected strategy를 같은 축에서 비교한다.
3. **Walk-forward matrix**: fold × metric heatmap으로 일관성·불안정 구간을 보여준다.
4. **Research lab tabs**: edge, feature importance, correlation, validation, failed candidates를 분리해 탐색 가능하게 만든다.

## 2. 확인한 현재 상태

### 2.1 Kronos Daily OHLCV 대시보드

관측 URL: `http://127.0.0.1:58185/daily-ohlcv`

현재 화면 섹션:

| 영역 | 현재 제공 | 한계 |
|---|---|---|
| D0-D6 진행 상태 | PASS/WATCH/RESEARCH_ONLY/NO-GO 카드 | 단계별 원인·영향 관계가 약함 |
| DB 분석 | 테이블 수, 행 수, 가격 기준 unknown, 품질 플래그 | 히트맵/분포/기간 커버리지 시각화 부족 |
| 유니버스 | 포함/제외 수, 제외 사유, 미리보기 | market/type/exclusion 관계가 시각적으로 약함 |
| 데이터셋 | split bar, leakage/normalization 상세 | feature/label 품질, split leakage 리스크가 표 중심 |
| D3-D6 모델 증거 | baseline list, RL 비교, gate reasons, fold table | 수익곡선·드로우다운·fold heatmap·원인 분해 부족 |
| 종목 상세 | 선택 시 OHLCV 샘플 | 아직 캔들/수익률/결측/급등락 시각화 없음 |
| artifact registry | 생성 파일 표 | run 비교/계보/검증 패키지화 부족 |

현재 판정은 유지해야 한다.

| 항목 | 현재 판정 |
|---|---|
| overall | `D0_D6_EVIDENCE_VISIBLE_MODEL_BUILD_NO_GO` |
| D3 | `WATCH` |
| D4 | `RESEARCH_ONLY` |
| D5 | `NO-GO` |
| D6 | `PASS` |
| model_build_allowed | `false` |
| go_summary_allowed | `false` |

### 2.2 STOM 대시보드에서 관측한 강점

관측 URL: `http://127.0.0.1:8770/ui/`  
스크린샷: `.omx/artifacts/stom_ui_review_viewport_2026_06_13.png`

STOM 화면/소스에서 확인한 주요 구성:

| STOM 요소 | 관측 내용 | Kronos 적용 방향 |
|---|---|---|
| 상단 상태/진행도 스트립 | run_id, provider, timeframe, progress, start/stop | Daily 연구 run selector + latest artifact selector + progress summary |
| Research Criteria | OOS disabled 등 연구 모드 명시 | `model_build_allowed=false` 사유와 guardrail banner 강화 |
| Metric Glossary | OOS, overfit, MDD, payoff, edge ratio 설명 | D3/D4/D5 지표 glossary를 Daily 탭에 추가 |
| Active Strategy | 현재 전략 source, code/diff 상태 | D3 baseline/D4 policy/D5 selected policy lineage 카드 |
| Process Flow | Generate → Backtest → Score → Autopsy → Iterate | D0 DB → D1 Universe → D2 Dataset → D3 Baseline → D4 RL → D5 Gate → D6 Dashboard flow |
| Fitness Trajectory | score, best-so-far, gate-passed 라인 | baseline score / RL score / gate status trajectory |
| Profit Trajectory | 수익률·수익금 듀얼축 | D3/D4/D5 net return overlay, 단 profit proof 아님 표기 |
| Equity Overlay | 전체 전략 누적곡선 + winner 강조 | D3 baseline curves, D4 RL curve, D5 selected strategy curve 비교 |
| Backtest Detail | 일별손익, 동시보유, 누적수익 | Daily portfolio exposure, turnover, drawdown 상세 |
| Quality Metrics | Calmar, R², MDD, trades, payoff 추이 | drawdown, turnover, hit-rate, fold consistency, calibration 추이 |
| Hall of Fame | 인간/시드/AI 비교 | Daily baseline leaderboard, 단 수익 보장 금지 |
| Generations Table | 세대별 점수, MDD, trades, reasons | experiment/run ledger table with PASS/WATCH/NO-GO reasons |
| Run Compare Console | runs=193, selected=6, normalize compare | Daily artifact compare console |
| Generation Analytics | multi metric, scatter, top table | D3/D4/D5 run scatter: return vs MDD, turnover vs return |
| Edge Ratio 분석 | time×cap heatmap, edge histogram | daily feature segment heatmap: market/cap/volatility/regime |
| Research Wiki | 연구 문서, 실패 후보, 다음 실험 | docs 결과/사전등록/NO-GO 문서 연결 |
| AI State Context | copyable context pack | next experiment context pack, reproduction command pack |
| Autopsy/Feedback | 실패 이유와 다음 세대 전달 | NO-GO root-cause autopsy + next validation checklist |

## 3. 적용 가능한 개선 기능 목록

### 3.1 즉시 반영 가치가 큰 시각화

| 우선순위 | 기능 | 설명 | 필요한 데이터 | 산출 UI |
|---|---|---|---|---|
| P0 | Decision Cockpit | model_build_allowed=false 원인을 가격/유니버스/RL/워크포워드/비용/누수로 분해 | `gate_verdict.json`, D2 manifest, D3/D4/D5 verdict | 원인 카드 + severity 색상 + 해결 조건 |
| P0 | D0-D6 Flow Map | STOM Process Flow처럼 단계 인과를 화살표로 표시 | `/api/daily-ohlcv/progress` | DB→Universe→Dataset→Baseline→RL→Gate→Dashboard |
| P0 | Metric Glossary | NO-GO, WATCH, RESEARCH_ONLY, MDD, turnover, hit-rate, calibration 설명 | 정적 텍스트 + API labels | 접이식 glossary |
| P1 | Baseline/RL Equity Overlay | D3 baseline, D4 RL, D5 selected 전략 누적곡선 비교 | D3 positions/predictions, D4 episode/positions, D5 fold metrics | 누적수익곡선, DD overlay |
| P1 | Walk-forward Heatmap | fold × metric 색상표 | `fold_metrics.csv`, `cost_sensitivity.csv`, `shuffle_control.csv` | fold consistency heatmap |
| P1 | Return/MDD Scatter | 전략/run별 return vs MDD 산점도 | D3 baseline metrics, D4 policy metrics, D5 fold aggregate | 우상향 착시 방지 산점도 |
| P1 | Cost Sensitivity Fan | 0/23/46bp 결과 비교 | D5 cost sensitivity | cost stress line/bar |
| P2 | Universe Treemap/Bar | 포함/제외/미매칭/ETF·ETN 제외 사유 시각화 | universe manifest | stacked bar / treemap |
| P2 | DB Coverage Calendar | 날짜별 테이블 수/결측/급등락 창 | db summary, blocked_windows | calendar heatmap |
| P2 | Feature/Label Quality Lab | feature distribution, forbidden feature, label horizon 분포 | D2 panels/stats | mini histogram/bar |
| P3 | Research Wiki Bridge | 관련 docs 결과/사전등록/NO-GO 문서 노출 | docs index | 문서 카드/검색 |
| P3 | Experiment Context Pack | 다음 실험 복사용 context | artifact manifests + verdicts | copy button |
| P4 | Symbol Drilldown Chart | 선택 종목 OHLCV 캔들, return, volume, anomaly flags | symbol API | lightweight/SVG chart |

### 3.2 STOM 아이디어를 Kronos에 맞게 변환할 때의 원칙

| STOM 원형 | Kronos 변환 원칙 |
|---|---|
| 수익 추이 | “수익 가능성”이 아니라 “검증 곡선/실패 곡선”으로 표시 |
| Winner / Hall of Fame | “우승” 대신 “현재 best baseline / blocked candidate”로 표시 |
| Start/Stop 버튼 | Daily 대시보드는 read-only 유지. 실행 버튼 금지 |
| Active Strategy | 정책 선택이 아니라 artifact lineage와 사전등록 여부 표시 |
| Run Compare | cherry-pick 방지를 위해 비용·fold·shuffle control 동시 표시 |
| AI State Context | 다음 실험 재현용 command/context pack만 제공, 매수 추천 문구 금지 |

## 4. 적용 설계안

### 4.1 Backend/API 확장

현재 `webui/daily_ohlcv_dashboard.py`는 chart payload를 제공하지만 아직 차트에 충분한 시계열을 주지 않는다. 아래 API를 추가하거나 기존 chart endpoint를 확장한다.

| API | 목적 | 응답 핵심 필드 |
|---|---|---|
| `/api/daily-ohlcv/charts/decision-cockpit` | NO-GO 원인 분해 | blockers, severity, required_fix, evidence_ref |
| `/api/daily-ohlcv/charts/flow` | D0-D6 인과 플로우 | nodes, edges, status, evidence |
| `/api/daily-ohlcv/charts/equity-overlay` | D3/D4/D5 누적곡선 비교 | curves[{name, kind, points}], guardrail |
| `/api/daily-ohlcv/charts/walk-forward-heatmap` | fold × metric matrix | rows, cols, cells, legend |
| `/api/daily-ohlcv/charts/cost-sensitivity` | 0/23/46bp 민감도 | series by strategy/fold |
| `/api/daily-ohlcv/charts/run-scatter` | return/MDD/turnover 산점도 | points[{x_mdd,y_return,size_trades,color_status}] |
| `/api/daily-ohlcv/charts/universe-breakdown` | 유니버스 분해 | include/exclude by reason/market/type |
| `/api/daily-ohlcv/charts/symbol/<code>` | 종목 상세 차트 | ohlcv, returns, volume, flags |

모든 API는 다음을 지켜야 한다.

- GET-only/read-only.
- run id fixed-root 검증 유지.
- sample/point limit bounded.
- `_database` 원본 DB mutation 금지.
- 응답에 `guardrail` 포함.
- 가격 기준 unknown이면 chart title/legend에 `PRICE_BASIS_UNKNOWN` 표시.

### 4.2 Frontend 컴포넌트 확장

현재 `webui/v2_src/src/tabs/dailyOhlcv/` 아래 컴포넌트를 늘리는 방식이 가장 안전하다.

| 신규 컴포넌트 | 역할 | STOM 참고 |
|---|---|---|
| `DailyDecisionCockpitCard.svelte` | NO-GO root cause 및 해결 조건 | Research Criteria, Winner/Best |
| `DailyFlowMap.svelte` | D0-D6 phase graph | ProcessFlowPanel |
| `DailyMetricGlossary.svelte` | 지표/상태 해설 | ResearchGlossaryPanel |
| `DailyEquityOverlayChart.svelte` | D3/D4/D5 곡선 비교 | EquityOverlayChart, ProfitChart |
| `DailyWalkForwardHeatmap.svelte` | fold matrix | EdgeRatio heatmap, BtHeatmap |
| `DailyRunScatter.svelte` | return vs MDD scatter | EaScatterChart |
| `DailyUniverseBreakdownChart.svelte` | universe include/exclude 시각화 | Run Compare/summary bars |
| `DailyResearchWikiCard.svelte` | 관련 docs/결과 연결 | ResearchWikiPanel |
| `DailyContextPackCard.svelte` | 다음 실험 context 복사 | AIContextPanel |

UI 배치는 다음이 좋다.

1. Hero + guardrail banner.
2. Decision Cockpit.
3. D0-D6 Flow Map.
4. Evidence Overview: DB/Universe/Dataset 요약.
5. Model Evidence Lab: Equity overlay, Return/MDD scatter, Walk-forward heatmap.
6. Cost/Shuffle Controls.
7. Universe/Data Quality Lab.
8. Research Wiki + Context Pack.
9. Artifact Registry.

## 5. 적용 단계별 계획

| 단계 | 목표 | 파일/영역 | 완료 조건 |
|---|---|---|---|
| V1 | Decision/Flow/Glossary 추가 | `daily_ohlcv_dashboard.py`, `DailyOhlcvTab.svelte`, 신규 Svelte 3개 | NO-GO 원인, D0-D6 flow, 지표 설명이 한 화면에 보임 |
| V2 | Equity overlay + scatter | 신규 chart API, `DailyEquityOverlayChart.svelte`, `DailyRunScatter.svelte` | D3 baseline/D4 RL/D5 selected 비교가 시각화됨 |
| V3 | Walk-forward heatmap + cost sensitivity | D5 chart endpoint 확장, `DailyWalkForwardHeatmap.svelte` | fold별 약점과 23bp 비용 압력이 한눈에 보임 |
| V4 | Universe/DB quality visual lab | universe/db chart endpoint 확장 | ETF/ETN 제외, 미매칭, 가격 unknown 리스크가 그래프로 보임 |
| V5 | Research Wiki + Context Pack | docs index API 또는 정적 mapping, context card | 다음 실험 계획을 복사 가능한 형태로 제공 |
| V6 | Symbol drilldown candle/return chart | symbol chart API + chart component | 000250 등 개별 종목 OHLCV/volume/anomaly 시각화 |

## 6. 우선 개발 권장안

가장 먼저 V1~V3를 개발하는 것이 맞다. 이유는 현재 사용자가 가장 크게 느끼는 문제인 “시각화 요소가 너무 없음”을 직접 해결하면서도, 수익 과장 위험을 낮추기 때문이다.

### 권장 1차 개발 묶음

| 개발 묶음 | 포함 기능 | 이유 |
|---|---|---|
| V1 Decision Pack | Decision Cockpit, Flow Map, Glossary | 지금 NO-GO 이유를 가장 빠르게 이해 가능 |
| V2 Comparison Pack | Equity Overlay, Return/MDD Scatter | RL이 baseline보다 왜 약한지 시각적으로 확인 |
| V3 Gate Pack | Walk-forward Heatmap, Cost Sensitivity | 실제 모델 빌드 잠금 해제 전 필요한 증거 확인 |

### 1차 개발 완료 후 기대 화면

- 상단에서 `NO-GO` 원인 5개가 severity와 해결조건으로 보인다.
- D0→D6 pipeline이 STOM처럼 흐름도로 표시된다.
- baseline/RL/gate 결과가 한 곡선·산점도·히트맵에서 비교된다.
- “우상향처럼 보이는지”가 아니라 “비용/드로우다운/fold에서 살아남는지”를 보게 된다.
- dashboard는 여전히 read-only이며 실행/주문 버튼은 없다.

## 7. 검증 계획

| 검증 | 명령/방법 |
|---|---|
| API 단위 | `py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py -q` |
| 탭/마커 | `py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_tab.py tests/test_v2_route.py -q` |
| 전체 daily 회귀 | 기존 D0-D6 daily test bundle |
| frontend check | `cd webui/v2_src && npm run check` |
| frontend build | `cd webui/v2_src && npm run build` |
| 브라우저 QA | `/daily-ohlcv`에서 Decision/Flow/Equity/Heatmap marker와 NO-GO guardrail 확인 |

브라우저 QA에서 반드시 확인할 문구:

- `model_build_allowed=false`
- `go_summary_allowed=false`
- `RESEARCH_ONLY`
- `NO-GO`
- `PRICE_BASIS_UNKNOWN`
- `UNIVERSE_WATCH_HEURISTIC`
- `no live/broker/orders`

## 8. 하지 말아야 할 것

- STOM의 “Winner/Hall of Fame” 표현을 Kronos에 그대로 가져와 수익모델처럼 보이게 만들면 안 된다.
- Daily OHLCV 화면에서 학습 실행, 주문, 브로커 연결 버튼을 만들면 안 된다.
- D4 RL 결과를 baseline보다 좋게 포장하면 안 된다. 현재 D4는 `RESEARCH_ONLY`이고 D5는 `NO-GO`다.
- price_basis unknown과 universe WATCH를 작은 글씨로 숨기면 안 된다.
- dashboard visual을 수익성 증거로 쓰면 안 된다.

## 9. 적용 후 전체 방향

이번 개선은 “수익 모델 생성”이 아니라 “수익 모델 후보를 만들기 전에 실패 원인과 검증 조건을 빠르게 보는 시각화 플랫폼”을 강화하는 일이다. 성공 조건은 화려한 그래프가 아니라 다음이다.

1. 실패가 더 빨리 보인다.
2. 원인과 다음 실험이 더 명확하다.
3. baseline 대비 RL의 약점이 숨겨지지 않는다.
4. fresh OOS/forward 검증 전에는 절대 GO로 보이지 않는다.
5. 사용자가 다음 개발 우선순위를 대시보드만 보고 결정할 수 있다.

이 기준으로 보면 STOM의 시각화 철학은 Kronos에 충분히 반영할 가치가 있다. 단, Kronos에서는 “성과 전시”가 아니라 “검증·잠금·부검” 중심으로 바꿔 적용해야 한다.
