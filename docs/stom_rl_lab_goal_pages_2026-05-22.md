# STOM 독립 강화학습 실험실 장기 Goal 구현 페이지

작성일: 2026-05-22 KST  
브랜치: `feature/stom-rl-lab`  
목표: **Kronos를 사용하지 않고 STOM tick/back DB 기반 독립 강화학습 대시보드와 모델 생성·사용 흐름을 완성한다.**

---

## 1. 전체 Goal

최종 목표는 다음 한 문장으로 정의한다.

> STOM tick/back DB를 read-only로 사용하여 강화학습 환경, baseline, 비용 검증, 모델 학습, 웹 대시보드, 실제 사용 가능성 평가까지 연결하고, 비용 차감 후 기존 baseline과 Kronos 300초 결과보다 나은지 검증한다.

이 목표는 단일 커밋으로 끝낼 수 없으므로, 페이지 단위로 나눠 각 페이지마다 다음을 반복한다.

1. 구현 범위 고정
2. 코드/문서 수정
3. 테스트/검증
4. 커밋
5. 진행률 업데이트

---

## 2. 장기 페이지 계획

| 페이지 | 이름 | 핵심 산출물 | 완료 기준 | 상태 |
|---:|---|---|---|---|
| 1 | 설계와 기준 고정 | `stom_independent_rl_lab_plan_2026-05-22.md` | 실측 데이터, baseline, reward horizon 문서화 | 완료 |
| 2 | DB loader / episode manifest | `stom_rl.episode_manifest` | read-only DB 검증, train/val/test episode manifest 생성 | 완료 |
| 3 | `StomTickTradingEnv` | RL 환경 skeleton | reset/step/reward/invalid action 단위 테스트 | 완료 |
| 4 | baseline runner | no-trade/random/momentum 등 | baseline report와 trade/equity artifact 생성 | 완료 |
| 5 | reward / cost gate | 5/10/15/25bp 비용 검증 | 25bp cost gate와 rolling validation | 완료 |
| 6 | 1차 RL 모델 | contextual bandit 또는 DQN | 300초 reward horizon 기준 walk-forward 평가 | 완료 |
| 7 | backend API | `/api/rl/*` | manifest/run/metric/trade/equity API smoke | 완료 |
| 8 | 웹 대시보드 | `강화학습 실험실` 탭 | build + browser smoke | 완료 |
| 9 | 통합 QA / 리뷰 | 최종 보고서 | 테스트, 코드리뷰, 확장/보류 결정 | 완료 |

---

## 3. 페이지 2: DB loader / episode manifest 상세

### 3.1 목적

페이지 2의 목적은 모델을 학습하는 것이 아니다. **이후 모든 강화학습 실험이 사용할 episode 계약을 고정**하는 것이다.

### 3.2 입력

| 입력 | 경로/값 |
|---|---|
| 원본 DB | `_database/stock_tick_back.db` |
| 기존 export report | `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json` |
| 기존 1초봉 CSV episode | `finetune/qlib_exports/stom_1s_grid_pred60_2025/qlib_csv/*.csv` |
| 기본 기간 | 2025-01-03 ~ 2025-12-30 |
| 기본 시간 | 09:00~09:30 |
| 기본 reward horizon | 300초 |

### 3.3 출력

| 출력 | 기본 경로 |
|---|---|
| manifest JSON | `webui/rl_runs/stom_1s_2025_episode_manifest/episode_manifest.json` |
| manifest CSV | `webui/rl_runs/stom_1s_2025_episode_manifest/episode_manifest.csv` |
| summary JSON | `webui/rl_runs/stom_1s_2025_episode_manifest/episode_summary.json` |

`webui/rl_runs/`는 런타임 산출물 성격이므로, 대규모 manifest artifact는 원칙적으로 커밋 대상이 아니라 재생성 대상이다.

### 3.4 검증 기준

| 검증 | 기대값 |
|---|---|
| DB 연결 | SQLite `mode=ro` |
| query-only | `PRAGMA query_only=ON` |
| write probe | 차단되어야 함 |
| split overlap | train/val/test session overlap 0 |
| chronological split | train → val → test 시간 순서 |
| manifest count | export report의 group 수와 일치 |
| unknown split | 0 |

---

## 4. 페이지 2 실행 명령

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.episode_manifest `
  --db _database\stock_tick_back.db `
  --export-report finetune\qlib_exports\stom_1s_grid_pred60_2025\stom_qlib_export_report.json `
  --output-dir webui\rl_runs\stom_1s_2025_episode_manifest `
  --reward-horizon-seconds 300 `
  --lookback-window 300
```

행 수까지 검증하려면 시간이 더 걸릴 수 있으므로 필요할 때만 다음 옵션을 추가한다.

```powershell
--count-csv-rows
```

---

## 5. 현재 진행률

| 기준 | 완료 페이지 | 전체 페이지 | 진행률 |
|---|---:|---:|---:|
| 설계 기준 | 1 | 9 | 11.1% |
| 페이지 2 코드/검증 | 2 | 9 | 22.2% |
| 페이지 3 환경 skeleton | 3 | 9 | 33.3% |
| 페이지 4 baseline runner | 4 | 9 | 44.4% |
| 페이지 5 reward / cost gate | 5 | 9 | 55.6% |
| 페이지 6 1차 RL 모델 | 6 | 9 | 66.7% |
| 페이지 7 backend API | 7 | 9 | 77.8% |

---

## 6. 페이지 2 완료 기록

페이지 2에서 다음을 완료했다.

| 항목 | 결과 |
|---|---|
| read-only DB 연결 | `mode=ro`, `PRAGMA query_only=ON` |
| 쓰기 probe | `attempt to write a readonly database`로 차단 |
| episode manifest | 18,750 episodes |
| symbol 수 | 1,638 |
| session 수 | 240 |
| split | train 13,256 / val 2,764 / test 2,730 |
| split overlap | 0 |
| chronological split | true |
| manifest delta | export report 대비 0 |

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_episode_manifest.py tests\test_stom_qlib_pipeline.py -q
```

결과:

```text
9 passed, 1 warning
```

다음 페이지는 **페이지 3: `StomTickTradingEnv`** 이다.

---

## 7. 페이지 3 완료 기록

페이지 3에서 강화학습 모델과 baseline runner가 공통으로 사용할 단일 episode 매매 환경 skeleton을 추가했다.

| 항목 | 결과 |
|---|---|
| 환경 클래스 | `stom_rl.trading_env.StomTickTradingEnv` |
| API 스타일 | Gymnasium 호환 `reset()` / `step()` 반환 형식 |
| action | `0=hold`, `1=buy`, `2=sell` |
| 기본 reward horizon | 300초 |
| 기본 비용 | 25bp |
| observation shape | `[lookback_window, 9]` |
| 기본 feature | OHLCV/amount + position/unrealized_return/time_in_position |
| 누수 방지 | observation 마지막 timestamp < action timestamp |
| invalid action | 보유 중 재매수, 미보유 청산을 penalty와 count로 기록 |
| deterministic replay | 동일 seed/행동열에서 동일 observation/reward |

실제 manifest smoke:

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.trading_env `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --split train `
  --episode-index 0 `
  --lookback-window 300 `
  --reward-horizon-seconds 300
```

대표 결과:

| 항목 | 값 |
|---|---|
| episode | `000100_20250103` |
| observation_shape | `[300, 9]` |
| action_timestamp | `2025-01-03T09:05:18` |
| horizon_timestamp | `2025-01-03T09:10:18` |
| no_future_observation | `true` |

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_trading_env.py tests\test_stom_rl_episode_manifest.py -q
```

다음 페이지는 **페이지 4: baseline runner** 이다.

---

## 8. 페이지 4 완료 기록

페이지 4에서는 강화학습 모델을 만들기 전에 반드시 비교해야 하는 모델 없는 기준선을 구현했다. 이 단계의 목적은 “RL이 아무 전략보다 나은가?”를 검증할 기준표를 먼저 만드는 것이다.

| 항목 | 결과 |
|---|---|
| 구현 모듈 | `stom_rl.baselines` |
| 실행 함수 | `run_baselines(BaselineRunConfig)` |
| CLI | `python -m stom_rl.baselines` |
| 정책 | `no_trade`, `random`, `buy_and_hold`, `momentum`, `mean_reversion`, `volume_filter` |
| 기본 split | `test` |
| 기본 비용 | 25bp |
| 산출물 | `baseline_summary.json`, `baseline_summary.csv`, 정책별 `actions.csv`, `trades.csv`, `equity.csv`, `episodes.csv` |

실제 2025 STOM manifest smoke는 test split 3개 episode로 실행했다.

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.baselines `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --split test `
  --max-episodes 3 `
  --policies no_trade,random,buy_and_hold,momentum,mean_reversion,volume_filter `
  --output-dir webui\rl_runs\stom_1s_2025_baselines_smoke
```

대표 smoke 결과는 다음과 같다.

| 정책 | episode | 거래 수 | 평균 episode net | hit rate | MDD |
|---|---:|---:|---:|---:|---:|
| no_trade | 3 | 0 | 0.0000% | 0.0000 | 0.0000% |
| random | 3 | 885 | -77.2541% | 0.0124 | -98.8246% |
| buy_and_hold | 3 | 3 | +3.3240% | 1.0000 | 0.0000% |
| momentum | 3 | 214 | -34.1359% | 0.0421 | -71.5770% |
| mean_reversion | 3 | 195 | -22.5387% | 0.0359 | -53.5298% |
| volume_filter | 3 | 224 | -31.2288% | 0.0045 | -67.6145% |

주의: 이 표는 전체 성과 확정이 아니라 **코드·artifact·metric 경로가 작동하는지 확인한 smoke**다. 전체 test split 기준의 엄밀한 판단은 페이지 5 cost gate에서 수행한다.

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_baselines.py tests\test_stom_rl_trading_env.py tests\test_stom_rl_episode_manifest.py -q
C:\Python\64\Python3119\python.exe -m py_compile stom_rl\baselines.py stom_rl\trading_env.py stom_rl\episode_manifest.py
```

검증 결과:

```text
10 passed
py_compile OK
```

다음 페이지는 **페이지 5: reward / cost gate** 이다. 페이지 5에서는 5/10/15/25bp 비용 시나리오와 전체 test split 기준으로 baseline이 비용 차감 후 살아남는지 검증한다.

---

## 9. 페이지 5 완료 기록

페이지 5에서는 강화학습 모델 학습 전에 사용할 비용 검증기를 추가했다. 이 단계의 목적은 “수익률이 좋아 보이는 전략이 실제 비용·슬리피지·회전율·MDD 조건에서도 살아남는가?”를 자동 판정하는 것이다.

| 항목 | 결과 |
|---|---|
| 구현 모듈 | `stom_rl.cost_gate` |
| 실행 함수 | `run_cost_gate(CostGateConfig)` |
| CLI | `python -m stom_rl.cost_gate` |
| 비용 시나리오 | 5bp, 10bp, 15bp, 25bp |
| slippage 시나리오 | CLI에서 복수 지정 가능, smoke는 0bp |
| target gate | 기본 25bp |
| gate 조건 | net positive, MDD 한도, trades/episode 한도, 최소 거래 수, rolling positive fold rate |
| 산출물 | `cost_gate_report.json`, `scenario_summary.csv`, `rolling_folds.csv`, `gate_summary.csv` |

실제 2025 STOM manifest smoke는 test split 3개 episode, rolling 2개 fold로 실행했다.

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.cost_gate `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --split test `
  --max-episodes 3 `
  --policies no_trade,random,buy_and_hold,momentum,mean_reversion,volume_filter `
  --cost-bps-values 5,10,15,25 `
  --slippage-bps-values 0 `
  --target-cost-bps 25 `
  --rolling-sessions-per-fold 3 `
  --rolling-max-folds 2 `
  --rolling-max-episodes-per-fold 3 `
  --output-dir webui\rl_runs\stom_1s_2025_cost_gate_smoke
```

대표 25bp target gate 결과는 다음과 같다.

| 정책 | 평균 episode net | 거래/episode | hit rate | MDD | positive fold rate | gate |
|---|---:|---:|---:|---:|---:|---|
| buy_and_hold | +3.3240% | 1.00 | 1.0000 | 0.0000% | 0.5000 | 통과 |
| no_trade | 0.0000% | 0.00 | 0.0000 | 0.0000% | 0.0000 | 실패 |
| mean_reversion | -22.5387% | 65.00 | 0.0359 | -53.5298% | 0.0000 | 실패 |
| volume_filter | -31.2288% | 74.67 | 0.0045 | -67.6145% | 0.0000 | 실패 |
| momentum | -34.1359% | 71.33 | 0.0421 | -71.5770% | 0.0000 | 실패 |
| random | -77.2541% | 295.00 | 0.0124 | -98.8246% | 0.0000 | 실패 |

주의: 위 표는 smoke 범위다. `buy_and_hold`가 smoke에서 통과했더라도 전체 2,730 test episode 기준 통과를 의미하지 않는다. 다음 모델 단계에 들어가기 전에 필요하면 동일 모듈로 전체 test split 실행을 별도로 수행한다.

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_cost_gate.py tests\test_stom_rl_baselines.py tests\test_stom_rl_trading_env.py tests\test_stom_rl_episode_manifest.py tests\test_stom_qlib_pipeline.py -q
C:\Python\64\Python3119\python.exe -m py_compile stom_rl\cost_gate.py stom_rl\baselines.py stom_rl\trading_env.py stom_rl\episode_manifest.py
```

검증 결과:

```text
18 passed, 1 warning
py_compile OK
```

다음 페이지는 **페이지 6: 1차 RL 모델** 이다. 기본 추천은 바로 복잡한 PPO가 아니라 300초 reward horizon 기준 contextual bandit 또는 단순 DQN prototype으로 시작하는 것이다.

---

## 10. 페이지 6 완료 기록

페이지 6에서는 Kronos를 사용하지 않는 첫 학습 모델을 구현했다. 복잡한 PPO/DQN으로 바로 가지 않고, 먼저 300초 horizon의 “매수할지/관망할지”를 학습하는 fixed-horizon contextual bandit을 만들었다.

| 항목 | 결과 |
|---|---|
| 구현 모듈 | `stom_rl.contextual_bandit` |
| 모델 종류 | ridge regression 기반 fixed-horizon contextual bandit |
| 입력 feature | 과거 OHLCV에서 만든 수익률, range, 이동평균 이격, 거래량/거래대금 ratio |
| action | predicted 300초 net return이 threshold보다 크면 `buy`, 아니면 `hold` |
| reward target | 300초 후 round-trip net return |
| 기본 비용 | 25bp |
| 산출물 | `config.json`, `model.json`, `train_metrics.jsonl`, `eval_summary.json`, `actions.csv`, `trades.csv`, `equity_curve.csv`, `episodes.csv` |

실제 2025 STOM manifest smoke는 train 5 episode, test 3 episode로 실행했다.

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.contextual_bandit `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --train-split train `
  --eval-split test `
  --max-train-episodes 5 `
  --max-eval-episodes 3 `
  --train-sample-stride 20 `
  --eval-sample-stride 1 `
  --lookback-window 300 `
  --reward-horizon-seconds 300 `
  --cost-bps 25 `
  --decision-threshold-bps 0 `
  --output-dir webui\rl_runs\stom_1s_2025_contextual_bandit_smoke
```

대표 결과는 다음과 같다.

| 항목 | 값 |
|---|---:|
| train episode | 5 |
| train sample | 299 |
| train target positive rate | 27.42% |
| eval episode | 3 |
| eval trade count | 11 |
| trades / episode | 3.67 |
| avg episode net | +1.8960% |
| compounded return | +5.7773% |
| avg trade net | +0.5240% |
| hit rate | 63.64% |
| MDD | -2.6211% |
| 25bp cost gate | 통과 |

단, 같은 3개 episode smoke에서 Page 5의 `buy_and_hold`는 +3.3240%였으므로, 이 모델은 “최종 우위 모델”이 아니라 **학습·저장·사용·평가 흐름이 실제 데이터에서 작동하는 첫 prototype**으로 본다.

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_contextual_bandit.py tests\test_stom_rl_cost_gate.py tests\test_stom_rl_baselines.py tests\test_stom_rl_trading_env.py tests\test_stom_rl_episode_manifest.py tests\test_stom_qlib_pipeline.py -q
C:\Python\64\Python3119\python.exe -m py_compile stom_rl\contextual_bandit.py stom_rl\cost_gate.py stom_rl\baselines.py stom_rl\trading_env.py stom_rl\episode_manifest.py
```

검증 결과:

```text
20 passed, 1 warning
py_compile OK
```

다음 페이지는 **페이지 7: backend API** 이다. 웹 대시보드에서 RL run 목록, model summary, trade/equity/cost gate artifact를 읽으려면 API가 필요하다.

---

## 11. 페이지 7 완료 기록

페이지 7에서는 `webui/rl_runs` 아래의 강화학습 산출물을 웹 대시보드가 읽을 수 있도록 read-only 백엔드 API를 추가했다. 이 단계는 새 학습을 실행하는 API가 아니라, 이미 생성된 manifest/baseline/cost gate/model artifact를 안전하게 조회하는 API다.

| 항목 | 결과 |
|---|---|
| 구현 helper | `webui.rl_dashboard` |
| Flask route | `/api/rl/*` |
| run listing | `GET /api/rl/runs` |
| run detail | `GET /api/rl/runs/<run>` |
| action/trade/equity/episode table | `GET /api/rl/runs/<run>/actions`, `/trades`, `/equity`, `/episodes` |
| generic table | `GET /api/rl/runs/<run>/table/<table>` |
| cost gate compact API | `GET /api/rl/runs/<run>/cost-gate` |
| path safety | run/policy는 direct child name만 허용 |
| table limit | 기본 500, 최대 5,000 row |

실제 `webui/rl_runs` smoke 결과:

| endpoint | 결과 |
|---|---|
| `/api/rl/runs?limit=10` | 200, `contextual_bandit_smoke`, `cost_gate_smoke`, `baselines_smoke`, `episode_manifest` 탐지 |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke` | 200, `artifact_type=contextual_bandit` |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke/trades?limit=3` | 200, 3 rows, truncated=true |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke/equity?limit=3` | 200, 3 rows, truncated=true |
| `/api/rl/runs/stom_1s_2025_cost_gate_smoke/cost-gate?limit=3` | 200, passing policy `buy_and_hold` |

검증 명령:

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_dashboard_api.py tests\test_stom_rl_contextual_bandit.py tests\test_stom_rl_cost_gate.py tests\test_stom_rl_baselines.py tests\test_stom_rl_trading_env.py tests\test_stom_rl_episode_manifest.py tests\test_stom_qlib_pipeline.py tests\test_v2_route.py -q
C:\Python\64\Python3119\python.exe -m py_compile webui\rl_dashboard.py webui\app.py stom_rl\contextual_bandit.py stom_rl\cost_gate.py stom_rl\baselines.py
```

다음 페이지는 **페이지 8: 웹 대시보드** 이다. 이제 API가 있으므로 프론트엔드에서 “강화학습 실험실” 탭을 만들어 run 목록, cost gate, 모델 성과, trade/equity를 시각화할 수 있다.


---

## 12. 페이지 8 완료 기록

페이지 8에서는 Page 7의 `/api/rl/*` read-only API를 받아 v2 웹 대시보드에 연결했다. 사용자는 CMD 로그만 보지 않고 브라우저에서 강화학습 산출물, 비용 관문, 거래 기록, 모델 사용 흐름을 확인할 수 있다.

| 항목 | 결과 |
|---|---|
| 화면 탭 | 사이드바/헤더/App shell에 `rl-lab` 등록 |
| 핵심 컴포넌트 | `webui/v2_src/src/tabs/RLLabTab.svelte` |
| API 연동 | `/api/rl/runs`, run detail, trades, equity, episodes, cost-gate |
| 시각화 | 비용 관문 bar/line chart, equity curve, episode net return chart |
| 표 | 25bp target gate, 거래 내역, artifact 목록 |
| 해석 보조 | smoke 모델이 아직 test split 생산 모델이 아니라는 보수적 안내 |
| 정적 산출물 | `webui/static/v2/dist` 갱신 |

웹 탭 구성은 다음과 같이 정리했다.

| 영역 | 표시 내용 |
|---|---|
| Run selector | contextual bandit, cost gate, baseline, episode manifest 산출물 선택 |
| 핵심 지표 | 평균 episode net, compounded return, MDD, episode/trade/artifact 수 |
| 비용 관문 | 25bp 기준 baseline/policy별 통과 여부, hit rate, MDD, 거래/episode |
| 거래 위치 | 진입/청산 timestamp, gross net, cost net |
| 모델 사용 흐름 | `model.json` feature와 inference 사용 방식 안내 |

검증 명령:

```powershell
npm run build
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_dashboard_tab.py tests\test_stom_rl_dashboard_api.py tests\test_v2_route.py -q
```

검증 결과:

```text
svelte-check 0 errors, 기존 경고 4개
vite build OK
8 passed
```

브라우저 smoke:

```text
Flask test server http://127.0.0.1:5070/
Playwright headless Chromium
- `button[data-tab="rl-lab"]` 클릭 성공
- `[data-rl-lab-tab]` 존재 확인
- `[data-rl-cost-gate-table]` 존재 확인
- run item 4개 확인
- contextual_bandit_smoke 표시 확인
- screenshot: .omx/tmp/rl-lab-page8-smoke.png
```

주의: 페이지 8은 “웹에서 smoke 산출물을 읽고 해석할 수 있음”을 증명한다. 아직 실거래 성과를 보장하지 않는다. 다음 페이지 9에서 전체 회귀 테스트, build, browser smoke, code review, 확장 또는 보류 판단을 완료해야 한다.

다음 목표는 **페이지 9: 통합 QA / 리뷰**다.


---

## 13. 페이지 9 완료 기록

페이지 9에서는 전체 구현을 최종 QA, build, browser smoke, code review, 확장/보류 판단까지 닫았다.

| 항목 | 결과 |
|---|---|
| 최종 보고서 | `docs/stom_rl_lab_final_qa_report_2026-05-23.md` |
| 전체 테스트 | `92 passed, 2 skipped, 2 warnings` |
| Frontend build | `npm run build` 통과, Svelte error 0 |
| Python compile | `stom_rl/*`, `webui/rl_dashboard.py`, `webui/app.py` 통과 |
| Browser smoke | Playwright headless Chromium 통과 |
| API smoke | `/api/rl/*` 주요 endpoint와 traversal probe 통과 |
| AI slop cleaner | production masking fallback 없음, optional Torch test guard 정리 |
| Code review | `APPROVE`, architect status `CLEAR` |

최종 판단:

- **구현 목표 달성**: 독립 RL 실험실, 데이터 적재/분할, 환경, baseline, 비용 관문, 첫 모델, API, 웹 대시보드가 동작한다.
- **실거래 자동화 보류**: 현재 모델은 smoke 성과 기준이며 full test split에서 buy-and-hold 대비 우위가 아직 증명되지 않았다.
- **다음 권장 작업**: full test split baseline/cost gate, contextual bandit 전체 학습·평가, DQN/PPO 후보 추가, transaction model 보강, leaderboard 운영.
