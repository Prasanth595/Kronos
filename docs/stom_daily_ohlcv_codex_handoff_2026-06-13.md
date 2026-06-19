# Kronos 일봉 OHLCV/RL 대시보드 Codex 핸드오프

**작성일:** 2026-06-13 KST 관측 기준  
**대상 저장소:** `D:/Chanil_Park/Project/Programming/Kronos`  
**주요 화면:** local Flask 실행 후 `/daily-ohlcv`  
**목적:** Codex 또는 다른 작업자가 현재까지 구현된 일봉 OHLCV 연구/대시보드 작업을 재검토·재작업·확장할 수 있도록 현재 상태, 변경 파일, 검증 명령, 다음 작업을 정리한다.

## 1. 핵심 결론

현재 구현은 **수익 보장 모델**이나 **실거래 가능한 강화학습 모델**이 아니다.  
현재 결론은 명확히 다음과 같다.

| 항목 | 현재 상태 |
|---|---|
| Daily OHLCV dashboard | 동작 중, D0~D9 연구 증거와 시각화 표시 |
| D0 DB/price basis | `UNKNOWN_CONFIRMED`, 수익률/라벨 신뢰도 blocker 유지 |
| D1 universe | `WATCH_HEURISTIC_UNIVERSE` / 공식·수동 검증 전 WATCH |
| D2 dataset | `PASS` evidence, 단 D0/D1 상위 blocker 영향 유지 |
| D3 예측/Top-K baseline | `WATCH` |
| D4 포트폴리오 RL | `RESEARCH_ONLY` |
| D5 walk-forward gate | `NO-GO` |
| D6/D7 visualization/research lab | evidence viewer / diagnostics 표시 |
| D8/D9 registry/paper-forward | `RESEARCH_ONLY_BLOCKED` |
| `model_build_allowed` | `false` |
| `go_summary_allowed` | `false` |
| `paper_forward_allowed` | `false` |
| `live_broker_order_allowed` | `false` |
| 실거래/브로커/주문 준비 | 아님 |

현재 모델 빌드가 잠긴 이유:

1. `D0_PRICE_BASIS_NOT_VERIFIED` / `PRICE_BASIS_UNKNOWN`: 일봉 DB의 가격 보정 기준(adjusted/raw, 분할, 배당)이 확정되지 않았다.
2. `D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED` / `UNIVERSE_WATCH_HEURISTIC`: KOSPI/KOSDAQ 보통주 분류는 적용됐지만 공식 KRX/수동 검증 전까지 WATCH다.
3. `D3_BASELINE_NOT_PROMOTABLE`: D3 baseline은 아직 승격 기준선으로 확정되지 않았다.
4. `D4_IMPLEMENTATION_NOT_UNLOCKED`: D4 RL은 연구용 evidence이며 구현/배포 unlock 근거가 아니다.
5. `D5_WALK_FORWARD_NOT_PASS`: D5는 `NO-GO`이며, no-trade/shuffle/D3 기준선·MDD·turnover·fold consistency gate를 통과하지 못했다.
6. 모든 UI/API/문서는 `NO-GO`/`WATCH`/`RESEARCH_ONLY` guardrail을 그대로 표시한다.

## 2. 완료된 큰 작업 축

| 축 | 완료 내용 | 현재 판정 |
|---|---|---|
| RL 모델 팩토리/게이트 P1~P5 | fill-mode evidence, run registry, walk-forward/fresh validation lock, dashboard readiness panel 구축 | fresh validation 전까지 locked |
| Daily OHLCV D0 | `_database/Stock_Database_ohlcv_1day.db` 분석, table/row/price_basis/quality flag/split-like evidence 표시 | PASS, price_basis unknown |
| Daily OHLCV D1 | ETF/ETN/Q상품/스팩/우선주 등 제외 휴리스틱, KOSPI/KOSDAQ 보통주 universe preview, quarantine evidence | WATCH |
| Daily OHLCV D2 | bounded preview dataset, leakage/split chronology/normalization evidence | PASS |
| Daily OHLCV D3 | no-trade/shuffle/Top-K/supervised baseline, calibration/drawdown/turnover samples | WATCH |
| Daily OHLCV D4 | constrained portfolio RL, observation/state manifest, reward/action/NAV/drawdown/turnover visualization | RESEARCH_ONLY |
| Daily OHLCV D5 | state-aware walk-forward fold gate, shuffle/no-trade/cost controls, D4 manifest consumption | NO-GO |
| Daily OHLCV D6 | full dashboard/API/UI evidence surface | visualization only |
| Daily OHLCV D7 | feature/regime/correlation/failure-analysis diagnostics/fallback cards | research diagnostics only |
| Daily OHLCV D8/D9 | reproducible registry and blocked paper-forward ledger with hashes, drift, decision log, unsafe artifact blocking | RESEARCH_ONLY_BLOCKED |

## 3. 최신 핵심 파일

### 3.1 백엔드/연구 모듈

| 파일 | 역할 |
|---|---|
| `stom_rl/daily_ohlcv_db.py` | D0 DB quality/price-basis/split-like evidence |
| `stom_rl/daily_ohlcv_universe.py` | D1 universe/exclusion/quarantine evidence |
| `stom_rl/daily_ohlcv_dataset.py` | D2 feature/label/split/leakage evidence |
| `stom_rl/daily_prediction.py`, `stom_rl/daily_ranker.py` | D3 baseline/ranker evidence |
| `stom_rl/daily_portfolio_env.py`, `stom_rl/daily_rl_train.py` | D4 constrained portfolio RL research artifacts |
| `stom_rl/daily_walk_forward.py` | D5 state-aware walk-forward gate |
| `stom_rl/daily_registry.py` | D8/D9 registry and blocked paper-forward ledger |
| `webui/daily_ohlcv_dashboard.py` | Daily OHLCV read-only adapter, D0~D9 payloads, effective gate |
| `webui/app.py` | Flask API routes |

### 3.2 주요 API

| API | 역할 |
|---|---|
| `GET /api/daily-ohlcv/progress` | D0~D9 progress/provenance/lock labels/exact verification commands |
| `GET /api/daily-ohlcv/db-summary` | D0 DB summary/price-basis blocker |
| `GET /api/daily-ohlcv/universe/preview` | D1 universe preview/quarantine |
| `GET /api/daily-ohlcv/dataset/latest` | D2 dataset evidence |
| `GET /api/daily-ohlcv/prediction/latest` | D3 baseline/ranker evidence |
| `GET /api/daily-ohlcv/portfolio/latest` | D4 RL state/reward/action/NAV evidence |
| `GET /api/daily-ohlcv/walk-forward/latest` | D5 gate/fold/cost/control evidence |
| `GET /api/daily-ohlcv/registry/latest` | D8/D9 registry/paper-forward ledger evidence |
| `GET /api/daily-ohlcv/charts/decision-cockpit` | model_build_allowed/go_summary_allowed lock decision cockpit |
| `GET /api/daily-ohlcv/charts/flow` | D0→D9 evidence flow |
| `GET /api/daily-ohlcv/charts/research-diagnostics` | D7 feature/regime/correlation/failure diagnostics |
| `GET /api/daily-ohlcv/charts/equity-overlay` | D3/D4/D5 equity comparison evidence |
| `GET /api/daily-ohlcv/charts/walk-forward-heatmap` | fold × metric heatmap + cost sensitivity |
| `GET /api/daily-ohlcv/charts/run-scatter` | return vs MDD scatter payload |
| `GET /api/daily-ohlcv/charts/universe-breakdown` | type/market/exclusion breakdown |
| `GET /api/daily-ohlcv/charts/symbol/<code>` | leading-zero-preserving symbol chart payload |

중요 제약:

- 모두 read-only evidence API다.
- `run=..` 같은 unsafe run id는 400이어야 한다.
- POST/PUT/DELETE는 405여야 한다.
- API가 수익/실거래/브로커/주문 준비를 암시하면 안 된다.

### 3.3 프론트엔드

| 파일 | 역할 |
|---|---|
| `webui/v2_src/src/lib/dailyOhlcvApi.ts` | Daily OHLCV API client/types |
| `webui/v2_src/src/tabs/DailyOhlcvTab.svelte` | Daily 탭 data orchestration |
| `webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte` | D0~D9 progress/provenance/verification matrix |
| `webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte` | D6/D7/D8/D9 visual lab, registry/paper-forward card |
| `webui/static/v2/dist/*` | `npm run build` 결과물 |

주요 UI marker:

- `data-daily-ohlcv-progress`
- `data-daily-d0-d9-provenance-matrix`
- `data-daily-visual-lab-card`
- `data-daily-decision-cockpit`
- `data-daily-flow-map`
- `data-daily-metric-glossary`
- `data-daily-equity-overlay`
- `data-daily-walk-forward-heatmap`
- `data-daily-run-scatter`
- `data-daily-universe-breakdown`
- `data-daily-symbol-chart`
- `data-daily-research-diagnostics`
- `data-daily-registry-paper-forward`

## 4. 주요 산출 문서

| 문서 | 용도 |
|---|---|
| `docs/stom_daily_ohlcv_db_analysis_and_page_plan_2026-06-11.md` | 일봉 DB 분석/페이지 계획 |
| `docs/stom_daily_ohlcv_deeprl_plan_2026-06-11.md` | 일봉 기반 딥러닝/RL 계획 |
| `docs/stom_daily_ohlcv_rl_master_restart_plan_2026-06-13.md` | 일봉 RL 재시작 마스터 문서 |
| `docs/stom_daily_ohlcv_d0_d3_provenance_hardening_result_2026-06-13.md` | D0~D3 provenance/evidence hardening |
| `docs/stom_daily_ohlcv_d4_observation_state_manifest_result_2026-06-13.md` | D4 observation/state manifest gate |
| `docs/stom_daily_ohlcv_d4_training_visualization_result_2026-06-13.md` | D4 training/evaluation visualization |
| `docs/stom_daily_ohlcv_d5_state_aware_walk_forward_result_2026-06-13.md` | D5 state-aware walk-forward gate |
| `docs/stom_daily_ohlcv_d8d9_registry_paper_forward_result_2026-06-13.md` | D8/D9 registry/paper-forward result |

세션/생성 artifact 예:

- `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_g003_state_visualization/`
- `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_13_g004_state_aware_gate/`
- `webui/rl_runs/daily_ohlcv_visual_lab/visual_lab_2026_06_13_g005_d6_d7_progress/`
- `webui/rl_runs/daily_ohlcv_registry/registry_2026_06_13_g006_paper_forward/`

## 5. 검증 명령과 관측 결과

G006 기준 최신 targeted 검증:

```powershell
py -3.11 -m py_compile stom_rl/daily_registry.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_registry.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# passed

py -3.11 -m pytest tests/test_stom_rl_daily_registry.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 26 passed
```

프론트/브라우저/API 검증:

```powershell
cd webui/v2_src
npm run check
# 0 errors, 4 pre-existing warnings in ForecastWorkbenchTab.svelte and DocsTab.svelte

npm run build
# 0 errors, same 4 pre-existing warnings; Vite build passed with bundle-size warning
```

대시보드 확인:

- route: `http://127.0.0.1:58198/daily-ohlcv`
- title: `Kronos 대시보드`
- `data-daily-api-error` 없음
- D0~D9 progress marker 존재
- D7 diagnostics marker 존재
- D8/D9 registry marker 존재
- `NO-GO`, `WATCH`, `RESEARCH_ONLY`, `no live/broker/orders`, `model_build_allowed=false`, `no_live_broker_order_readiness`, D0/D1/D3/D4/D5 effective blocker 문구 표시
- API: registry/progress/decision-cockpit 200, unsafe registry run id 400, registry POST 405

현재 서버 실행 예:

```powershell
py -3.11 -c "from webui.app import app; print('READY http://127.0.0.1:58198/daily-ohlcv', flush=True); app.run(host='127.0.0.1', port=58198, debug=False, use_reloader=False)"
```

## 6. Codex가 재작업할 때 먼저 확인할 것

1. `docs/AGENTS.md`, `stom_rl/AGENTS.md`, `webui/AGENTS.md`, `webui/v2_src/AGENTS.md`, `tests/AGENTS.md`를 먼저 읽는다.
2. 기존 미커밋/생성 변경이 많으므로 임의 revert하지 않는다.
3. `webui/daily_ohlcv_dashboard.py`가 import 실패하면 Daily API가 500으로 떨어지므로 `py_compile`부터 확인한다.
4. Daily chart/registry API는 반드시 read-only/GET-only/unsafe path 방어를 유지한다.
5. 프론트 변경 후에는 `npm run check`와 `npm run build`를 모두 실행한다.
6. 대시보드 확인은 API 응답만 보지 말고 실제 `/daily-ohlcv`에서 marker와 API error 부재를 확인한다.

## 7. 현재 남은 개발 과제

| 우선순위 | 작업 | 이유 | 완료 기준 |
|---:|---|---|---|
| 1 | 가격 보정 기준 확정 | `price_basis=unknown`이 가장 큰 연구 신뢰도 리스크 | adjusted/raw, split/dividend 정책 문서화 + DB quality PASS |
| 2 | 공식 유니버스 검증 | 현재 KOSPI/KOSDAQ 보통주 분류는 휴리스틱 WATCH | KRX/공식 메타데이터 기반 include/exclude 재검증 |
| 3 | D3 baseline freeze/강화 | RL은 강한 baseline을 넘어야 의미 있음 | no-trade/shuffle/Top-K/ranker baseline 고정 및 D0/D1 blocker 해소 후 재검증 |
| 4 | D4 RL reward/action 재설계 | 현재 RL 후보가 baseline보다 약함 | 비용 23bp 후 D3 baseline 초과 후보 생성, state manifest 유지 |
| 5 | D5 fresh OOS/forward 재검증 | 선택 후 재검증 없이는 과최적화 가능 | 사전등록 조건으로 fresh validation PASS |
| 6 | Research Lab 확장 | feature/regime 분석은 아직 연구 보조 수준 | feature heatmap, regime/correlation, failed candidate autopsy 추가 |
| 7 | Symbol chart 고도화 | 현재는 OHLCV preview 수준 | candlestick, return, volume, gap, missing/adjustment overlay 추가 |

## 8. 작업 설명 요약

이번 업데이트는 Kronos의 일봉 연구 상태에 맞게 **실패/검증/잠금 중심 UI**와 registry evidence를 확장한 작업이다.

구현한 핵심은 다음이다.

- 사용자가 대시보드를 봤을 때 “왜 지금 수익모델 생성이 안 되는지”를 바로 알 수 있도록 effective D0/D1/D3/D4/D5 gate를 만들었다.
- D0 DB → D1 Universe → D2 Dataset → D3 Baseline → D4 RL → D5 Gate → D6 Visualization → D7 Diagnostics → D8 Registry → D9 Paper-forward 흐름을 시각화했다.
- D4는 observation/state contract, reward stack, learning/reward/return/drawdown, action distribution, invalid action, turnover, concentration, portfolio trajectory, frozen D3 comparison을 노출한다.
- D5는 D4 state-aware artifact를 소비하고, fold/purge/embargo/no-OOS-retuning/control/cost sensitivity를 표시한다.
- D8/D9는 config/data/code/source hash, lock reasons, drift, drawdown, decision log, blocked paper-selected rows, `no_live_broker_order_readiness`를 보존한다.
- 모든 API와 UI는 `no profit claim`, `no live/broker/orders`, `RESEARCH_ONLY`, `NO-GO` guardrail을 유지한다.

## 9. 금지 사항

Codex가 이어서 작업할 때 다음을 하지 않는다.

- D4 RL 또는 D5 fold 일부가 좋아 보인다는 이유로 수익모델 GO라고 쓰지 않는다.
- dashboard visual을 profitability proof로 취급하지 않는다.
- `ts_imb`/rule baseline을 RL이라고 부르지 않는다.
- `_database` 원본 DB를 dashboard/API에서 mutate하지 않는다.
- `model_build_allowed=false`를 UI에서 숨기거나 약하게 표현하지 않는다.
- 23bp 비용, no-trade/shuffle/baseline 비교 없이 우상향/수익 가능성을 주장하지 않는다.
