# STOM Daily OHLCV RL Master Restart Plan (2026-06-13)

## 0. 결론

이 문서는 최근 D0/D1/D3 hardening 결과와 기존 일봉 계획 문서를 합쳐, **일봉 OHLCV 기반으로 전략 후보를 찾는 연구용 모델 시스템 전체를 다시 시작하기 위한 마스터 문서**다.

작성 결론은 명확하다.

- 마스터 문서를 새로 정리하는 것이 맞다. 기존 문서들은 D0~D6 개별 계획/결과가 분산되어 있어, 지금부터 D4 RL 학습·보상·환경·수익률 그래프까지 확장하려면 하나의 기준 문서가 필요하다.
- 단, 이 문서의 목표는 **실거래 모델 출시**가 아니라 **반복 학습/검증 가능한 research candidate model factory** 구축이다.
- `model_build_allowed=false`는 유지한다. D0 가격 기준, D1 공식 유니버스, D5 fresh OOS gate가 통과되기 전에는 어떤 그래프도 수익 증명이 아니다.

## 1. 기준 문서와 최신 상태

| 문서/근거 | 역할 | 현재 반영 상태 |
|---|---|---|
| `docs/stom_daily_ohlcv_codex_handoff_2026-06-13.md` | 현재 Daily OHLCV dashboard/API/UI handoff | D0~D9 반영 |
| `docs/stom_daily_ohlcv_db_analysis_and_page_plan_2026-06-11.md` | D0~D6 원계획 | 반영 |
| `docs/stom_daily_ohlcv_deeprl_plan_2026-06-11.md` | 일봉 DL/RL 방향 | 반영 |
| `docs/stom_daily_ohlcv_price_basis_result_2026-06-13.md` | D0 가격 기준 확인 결과 | `UNKNOWN_CONFIRMED` 반영 |
| `docs/stom_daily_ohlcv_universe_official_validation_result_2026-06-13.md` | D1 공식 유니버스 검증 경로 | `WATCH_HEURISTIC_UNIVERSE` 반영 |
| `docs/stom_daily_ohlcv_d3_baseline_hardening_result_2026-06-13.md` | D3 baseline hardening 결과 | `WATCH`, shuffle/control/delta 반영 |
| `docs/stom_daily_ohlcv_d8d9_registry_paper_forward_result_2026-06-13.md` | D8/D9 registry/paper-forward 결과 | `RESEARCH_ONLY_BLOCKED`, effective gate 반영 |

## 2. 전체 목표 정의

| 구분 | 목표 |
|---|---|
| 최종 연구 목표 | 일봉 OHLCV 기반으로 스윙/종목선별/리스크 필터/포트폴리오 리밸런싱 후보 전략을 찾는다. |
| 모델 목표 | 정확한 가격 예측이 아니라 확률, 순위, 기대수익 bucket, 리스크 bucket, 포트폴리오 action policy를 만든다. |
| RL 목표 | D3 baseline을 넘는 경우에만 daily portfolio rebalance RL 후보를 연구한다. |
| 대시보드 목표 | DB → Universe → Dataset → Baseline → RL → Walk-forward → Decision까지 실패/성공 근거를 그래프로 확인한다. |
| 사용 가능 모델의 의미 | `train/evaluate/infer`가 재현되고, OOS gate를 통과해 research/paper candidate로 쓸 수 있는 모델. 실거래/브로커 주문 모델이 아니다. |
| 금지 | 수익 보장, 실거래 준비, broker/order routing, 긍정 곡선만 보고 GO, `ts_imb`를 RL이라고 부르기. |

## 3. 현재 전체 진행률

| 단계 | 페이지 | 현재 상태 | 진행률 | 완료된 것 | 남은 병목 |
|---|---|---:|---:|---|---|
| D0 | Daily DB Analysis | `PASS` but `price_basis=unknown` | 80% | table/row/date/quality/split-like evidence, `UNKNOWN_CONFIRMED`, blocking implication | adjusted/raw/split/dividend 외부 근거 필요 |
| D1 | Universe Management | `WATCH_HEURISTIC_UNIVERSE` | 70% | stockinfo + heuristic 분류, official CSV ingestion contract, quarantine evidence | 공식 KRX/manual CSV 실제 투입 및 검토 |
| D2 | Dataset Builder | `PASS` | 80% | feature/label/split, leakage/split chronology evidence | 가격 기준 확정 후 label 신뢰도 재검증 |
| D3 | Prediction / Top-K Baseline | `WATCH` | 85% | no-trade, deterministic shuffle, Top-K, vol-adjusted, supervised ranker/classifier, 23bp, MDD/turnover/hit-rate/delta | D0/D1 blocker 해소 후 fresh baseline freeze |
| D4 | Portfolio RL | `RESEARCH_ONLY` | 55% | constrained env, observation/state manifest, reward/action/NAV/drawdown/turnover/action distribution visualization | D3 baseline 초과 reward/action 재설계 필요 |
| D5 | Walk-forward Gate | `NO-GO` | 55% | state-aware D4 artifact consumption, fold gate, shuffle/no-trade/cost controls, no-OOS-retuning evidence | fresh OOS, fold consistency, MDD/turnover/delta 통과 |
| D6 | Dashboard Visualization | evidence viewer | 85% | Decision cockpit, flow, glossary, overlay, heatmap, scatter, symbol preview, D0~D9 timeline | 계속되는 연구 artifact 추가 시 UI 갱신 |
| D7 | Research Lab / Explainability | diagnostics only | 35% | feature/regime/correlation/failure placeholder/fallback cards | 실제 feature/regime/correlation/failure autopsy artifact 필요 |
| D8 | Model Registry / Promotion | `RESEARCH_ONLY_BLOCKED` | 45% | config/data/code/source hashes, source runs, promotion status, effective gate blockers, unsafe artifact blocking | D0/D1/D3/D4/D5 gate 해소 전 승격 금지 |
| D9 | Paper Forward Ledger | `RESEARCH_ONLY_BLOCKED` | 40% | blocked paper-selected row, realized return/drawdown samples, drift, decision log, no-live/broker/order readiness | 실제 paper-only continuation도 D5 PASS 전 금지 |

## 4. 전체 페이지 설계 테이블

| 페이지 | 이름 | 목적 | 핵심 시각화 | 주요 artifact/API | 통과 조건 |
|---|---|---|---|---|---|
| D0 | Daily DB Analysis | DB가 연구 가능한지 확인 | table/date coverage, quality flag, split-like window, price-basis blocker | `daily_ohlcv_db.py`, `/api/daily-ohlcv/db-summary`, `price_basis_audit.json` | 가격 기준이 `VERIFIED` 또는 unknown blocker가 명확히 표시됨 |
| D1 | Universe Management | 학습/평가 universe 정의 | include/exclude breakdown, official metadata status, quarantine table | `daily_ohlcv_universe.py`, `/api/daily-ohlcv/universe/preview`, `universe.json`, `quarantine.csv` | 공식/manual KRX metadata로 common equity 검증 |
| D2 | Dataset Builder | raw DB를 모델용 feature/label/split으로 변환 | split timeline, leakage report, normalization stats, blocked windows | `daily_ohlcv_dataset.py`, `feature_panel.csv`, `label_panel.csv`, `split_assignments.csv` | date split, no leakage, label/feature definitions reproducible |
| D3 | Prediction / Top-K | RL 전 강한 supervised/rule baseline 확립 | baseline table, calibration, Top-K return, hit-rate, MDD, turnover, delta vs shuffle | `daily_prediction.py`, `daily_ranker.py`, `baseline_metrics.json`, `baseline_delta_summary.json` | no-trade/shuffle/rule/supervised 비교 후 WATCH/PASS 판정 |
| D4-A | RL Environment Inspector | RL 환경이 올바른지 확인 | observation shape, action mask, holdings, invalid action, reward components | `daily_portfolio_env.py`, `env_manifest.json`, `reward_breakdown.csv` | reward/action/accounting이 테스트로 검증됨 |
| D4-B | RL Training Monitor | 실제 학습 과정 관찰 | episode reward, NAV, loss, entropy, invalid action rate, turnover, drawdown | `daily_rl_train.py`, `training_manifest.json`, `episode_metrics.csv`, `learning_curve.csv` | 학습이 재현되고 baseline보다 나쁜 경우 명확히 표시 |
| D4-C | RL Policy Evaluation | 학습 policy를 검증 split에서 평가 | equity curve, drawdown, action distribution, holdings concentration, baseline delta | `policy_metrics.json`, `positions.csv`, `baseline_comparison.json` | 23bp 후 D3 best baseline 초과 또는 `RESEARCH_ONLY` 유지 |
| D5 | Walk-forward / Gate | 과최적화 방지 | fold heatmap, cost sensitivity, shuffled control, fold consistency, gate reasons | `daily_walk_forward.py`, `walk_forward_manifest.json`, `fold_metrics.csv`, `cost_sensitivity.csv` | 사전등록 조건으로 `GO/WATCH/NO-GO` 판정 |
| D6 | Decision Cockpit | 전체 상태를 한 화면에서 판단 | D0~D5 flow, blocker list, model_build_allowed, go_summary_allowed | `/api/daily-ohlcv/charts/decision-cockpit` | 왜 모델 빌드가 잠겼는지 즉시 설명 가능 |
| D7 | Research Lab | 실패 원인/feature/regime 분석 | feature importance, regime heatmap, correlation, failure autopsy, symbol drilldown | planned `daily_research_lab.py`, current diagnostics fallback/API | 개선 가설이 사전등록 가능한 형태로 정리됨 |
| D8 | Model Registry | candidate model version 관리 | run list, config hash, data hash, code/source hash, metric summary, promotion status, effective blockers | `stom_rl/daily_registry.py`, `/api/daily-ohlcv/registry/latest`, `candidate_registry.json` | 재현 가능한 model candidate만 registry 등록; 현재는 blocked |
| D9 | Paper Forward Ledger | fresh forward/paper 검증 | blocked daily selected list, realized return, drift, drawdown, decision log | `paper_selected.csv`, `realized_returns.csv`, `drawdown.csv`, `drift.csv`, `decision_log.jsonl` | paper-only forward evidence 누적, live claim 없음 |

## 5. D4 RL을 다시 시작하기 전 필요한 잠금 해제 조건

| Lock | 현재 상태 | D4 RL 진행 가능 조건 |
|---|---|---|
| Price basis lock | `UNKNOWN_CONFIRMED` | adjusted/raw/split/dividend 기준을 외부 근거로 문서화하거나 split-like windows 제외 정책 확정 |
| Universe lock | `WATCH_HEURISTIC_UNIVERSE` | `_database/krx_listed_products.csv` 또는 manual CSV로 common equity universe 검증 |
| Baseline lock | D3 `WATCH` | D3 baseline run을 freeze하고 no-trade/shuffle/rule/supervised deltas를 기준선으로 고정 |
| Walk-forward lock | D5 `NO-GO` | D4 후보가 D5 fresh OOS gate를 통과해야 model candidate로 승격 |
| Model-build lock | `model_build_allowed=false` | D0/D1/D3/D5 조건 통과 후에만 `WATCH` 또는 `GO` 검토 가능 |

## 6. D4 RL 환경/보상/학습 그래프 설계

### 6.1 환경 계약

| 항목 | 설계 |
|---|---|
| 시점 | date-based daily rebalance |
| 후보 | D3 Top-K/ranker candidate panel |
| observation | candidate features + current holdings + cash/exposure/risk state |
| action | constrained hold/buy/add/sell/reduce; free-form continuous allocation 금지 |
| mask | 현금 부족, 보유 없음, concentration 초과, invalid symbol 등 masking |
| fill assumption | daily open/close 등 명시된 basis만 사용; 아직 broker/marketable fill 아님 |
| accounting | NAV, realized/unrealized return, turnover, concentration, MDD |

### 6.2 Reward 공식

기본 reward는 다음을 출발점으로 한다.

```text
reward = daily_nav_return
       - 23bp_turnover_cost
       - drawdown_penalty
       - concentration_penalty
       - invalid_action_penalty
       - churn_penalty
```

| 보상 구성 | 시각화 | 실패 조건 |
|---|---|---|
| `daily_nav_return` | NAV/equity curve, daily return bar | shuffle/no-trade보다 낮음 |
| `turnover_cost` | turnover line, cumulative cost | 과도한 churn으로 수익 잠식 |
| `drawdown_penalty` | drawdown curve, MDD heatmap | MDD gate 초과 |
| `concentration_penalty` | holdings concentration / top exposure | 일부 종목 과집중 |
| `invalid_action_penalty` | invalid action rate | mask 설계 실패 |
| `churn_penalty` | rebalance count, action distribution | 의미 없는 매매 반복 |

### 6.3 학습 그래프

| 그래프 | 의미 | 파일/API |
|---|---|---|
| Episode reward curve | 학습 reward 안정성 | `learning_curve.csv` / planned `/api/daily-ohlcv/rl/training/latest` |
| NAV curve | policy equity 경로 | `positions.csv`, `policy_metrics.json` |
| Drawdown curve | 리스크 누적 | `drawdown.csv` |
| Turnover/cost curve | 비용 민감도 | `turnover.csv`, `reward_breakdown.csv` |
| Action distribution | hold/buy/sell/reduce 비율 | `action_distribution.csv` |
| Invalid action rate | 환경/action mask 품질 | `invalid_actions.csv` |
| Reward component stack | 어떤 penalty가 reward를 깎는지 | `reward_breakdown.csv` |
| Baseline overlay | RL vs D3 rule/supervised/no-trade/shuffle | `baseline_comparison.json` |
| Fold heatmap | OOS stability | `fold_metrics.csv` |
| Cost sensitivity | 23bp 기본 + stress cost | `cost_sensitivity.csv` |

## 7. 모델 후보 승격 기준

| 단계 | 이름 | 승격 조건 | 실패 시 |
|---|---|---|---|
| M0 | 구현 smoke | env step/reset/accounting test 통과 | env 수정 |
| M1 | train reproducible | seed/config/data hash가 같으면 주요 metrics 유사 | artifact invalid |
| M2 | baseline comparable | no-trade/shuffle/D3 best rule/supervised와 비교 가능 | D4 `RESEARCH_ONLY` 유지 |
| M3 | OOS candidate | val/test에서 D3 best baseline 초과, MDD/turnover 과도하지 않음 | reward/action 재설계 |
| M4 | walk-forward candidate | 5+ folds, fresh OOS, no retuning, cost sensitivity 통과 | D5 `NO-GO` |
| M5 | paper candidate | forward ledger에서 drift/실패 원인 추적 가능 | research-only 유지 |
| M6 | production consideration | 별도 broker/execution/latency/risk/compliance 계획 필요 | 현재 범위 밖 |

## 8. 다음 실행 순서

| 순서 | 작업 | 산출물 | 권장 검증 |
|---:|---|---|---|
| 1 | 공식 가격 기준/보정 정책 확정 | updated D0 doc + `price_basis_audit.json` | `tests/test_stom_rl_daily_ohlcv_db.py` |
| 2 | 공식 KRX/manual universe CSV 투입 | `krx_listed_products.csv`, updated universe manifest | `tests/test_stom_rl_daily_ohlcv_universe.py` |
| 3 | D3 frozen baseline 재생성 | frozen `prediction_manifest.json`, checksum doc | `tests/test_stom_rl_daily_prediction.py` |
| 4 | D4 env inspector 강화 | `env_manifest.json`, `reward_breakdown.csv`, env tests | `tests/test_stom_rl_daily_portfolio_env.py` |
| 5 | D4 training monitor 구축 | `learning_curve.csv`, `episode_metrics.csv`, UI graph | 신규 training monitor tests |
| 6 | D4 policy evaluation | `policy_metrics.json`, `positions.csv`, `baseline_comparison.json` | RL gate tests |
| 7 | D5 fresh walk-forward | `fold_metrics.csv`, `cost_sensitivity.csv`, gate verdict | `tests/test_stom_rl_daily_walk_forward.py` |
| 8 | D6/D7 visualization 확장 | reward/action/env/failure-analysis cards | dashboard API/tab tests + browser check |
| 9 | D8 registry/promotion hardening | model registry row + promotion/effective gate reason + source hashes | `tests/test_stom_rl_daily_registry.py` |
| 10 | D9 paper-forward ledger hardening | blocked paper candidate ledger + drift/drawdown/decision log | registry tests + dashboard API/tab tests |

## 9. 권장 GJC 시작 명령

작업을 바로 실행하기보다, 이 마스터 문서를 기준으로 새 실행 계획을 끊어 진행하는 것이 안전하다.

```powershell
gjc ultragoal status --json
```

새 실행을 시작할 때 권장 brief:

```powershell
gjc ultragoal create-goals --brief "D4 Daily Portfolio RL environment/training visualization restart based on docs/stom_daily_ohlcv_rl_master_restart_plan_2026-06-13.md. Preserve guardrails: no live/broker/orders, no profit claims, 23bp default cost, no _database mutation, model_build_allowed=false until D0/D1/D5 gates pass. Start with D4-A environment inspector, D4-B learning/reward graph artifacts, and D4-C policy evaluation against frozen D3 baselines."
```

개별 검증 명령:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_walk_forward.py -q
```

```powershell
py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py tests/test_stom_rl_daily_prediction.py -q
```

```powershell
cd webui/v2_src
npm run check
npm run build
```

## 10. 지금부터의 개발 원칙

| 원칙 | 내용 |
|---|---|
| Baseline-first | RL은 D3 baseline보다 강해야 의미가 있다. |
| Evidence-first | 그래프는 설명 자료일 뿐, 수익 증명이 아니다. |
| Gate-first | D5 fresh OOS 통과 전 모델 빌드 금지. |
| Cost-first | 모든 return/delta는 23bp 비용 후 기준. |
| Read-only dashboard | dashboard/API에서 DB, broker, order side effect 금지. |
| Reproducibility | 모든 run은 config/data/code hash와 artifact 경로를 남긴다. |
| Failure visibility | NO-GO, WATCH, failed fold, drawdown, turnover를 숨기지 않는다. |

## 11. 한 줄 마스터 방향

**일봉 RL은 지금 바로 “수익 모델”을 만드는 작업이 아니라, D0/D1/D3 기준선을 고정한 뒤 D4 환경·보상·학습 그래프·정책 평가를 투명하게 만들고, D5 fresh OOS gate를 통과한 후보만 research/paper candidate로 승격하는 작업이다.**
