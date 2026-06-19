# STOM 강화학습 성과 모델 고도화 페이지 계획

작성일: 2026-05-23 KST
브랜치: `feature/stom-rl-lab`
OMX 계획: `.omx/ultragoal/goals.json`
목표: **STOM tick/back data로 smoke가 아닌 full test split 기준 강화학습 성과를 검증하고, 실제 사용 가능한 모델 후보와 대시보드 비교 체계를 만든다.**

---

## 1. 이번 단계의 핵심 목적

이전 9페이지 작업은 “강화학습 실험실이 가능한가?”를 증명했다. 이번 단계는 한 단계 더 나아가 “실제로 쓸 만한 모델인가?”를 검증한다.

| 구분 | 이전 단계 | 이번 단계 |
|---|---|---|
| 목적 | RL 실험실 구축 | 수익성 검증과 모델 고도화 |
| 데이터 | STOM 2025 1초봉 episode manifest | 동일 데이터의 full test split 중심 |
| 모델 | contextual bandit smoke | contextual bandit full 평가 + DQN/PPO 확장 준비 |
| 검증 | 동작 확인, smoke cost gate | 전체 test split, baseline 대비, 비용 반영, drawdown |
| 대시보드 | run 단위 결과 확인 | 모델별 leaderboard와 smoke/full 구분 |
| 자동매매 판단 | 보류 | 지표 기반 사용/보류 판단 |

---

## 2. 오픈소스 참고 원칙

새 dependency는 바로 추가하지 않는다. 먼저 현재 STOM 전용 구현을 full 검증으로 확장하고, 필요한 경우에만 별도 단계에서 dependency를 검토한다.

| 참고 자료 | 활용 방식 | 현재 적용 방향 |
|---|---|---|
| Gymnasium | `reset/step` 환경 인터페이스 표준 | 기존 `StomTickTradingEnv` 계약 유지 |
| Stable-Baselines3 | DQN/PPO 등 표준 RL 알고리즘 후보 | P006에서 dependency 필요성 판단 |
| FinRL | 금융 RL에서 data split, transaction cost, risk metric 중요 | baseline/cost gate/rolling validation 강화 |
| RLTrader | 주식 매매 action, reward, portfolio 평가 아이디어 | action/reward 확장 후보로 참고 |
| 기존 STOM/Kronos 결과 | 이전 예측·파인튜닝 실험의 실패/한계 | 비교 baseline으로만 사용, Kronos 의존은 제거 |

참고 링크:

- Gymnasium: https://gymnasium.farama.org/
- Stable-Baselines3: https://stable-baselines3.readthedocs.io/
- FinRL: https://github.com/AI4Finance-Foundation/FinRL
- RLTrader: https://github.com/quantylab/rltrader

---

## 3. 현재 데이터 기준

현재 강화학습의 기준 데이터는 이미 생성된 STOM 2025 1초봉 episode manifest다.

| 항목 | 값 |
|---|---:|
| 전체 episode | 18,750 |
| 종목 수 | 1,638 |
| 거래일/session | 240 |
| train episode | 13,256 |
| val episode | 2,764 |
| test episode | 2,730 |
| 원본 export row | 33,360,325 |
| 시간 범위 | 09:00~09:30 |
| lookback | 300초 |
| reward horizon | 300초 |
| split overlap | 0 |
| DB 접근 | read-only |

---

## 4. 성공/실패 판정 기준

이번 단계는 “모델이 좋아 보인다”가 아니라, 아래 기준을 통과해야 성공으로 본다.

| 판정 항목 | 성공 기준 |
|---|---|
| baseline 대비 | no-trade/random/buy-and-hold/momentum 중 핵심 baseline보다 비용 후 우위 |
| 비용 반영 | 25bp 이상 비용에서 평균 episode net return 양수 |
| 거래 안정성 | trade count가 0에 가깝거나 과도하지 않음 |
| 리스크 | max drawdown이 허용 범위 이내 |
| 일반화 | train이 아니라 test split에서 성과 확인 |
| 반복성 | rolling fold에서 positive fold rate 기준 충족 |
| 대시보드 | smoke/full run이 명확히 구분되고 leaderboard에 표시 |

실패 기준도 명확히 둔다.

| 실패 유형 | 해석 |
|---|---|
| buy-and-hold보다 낮음 | 모델 사용 보류 |
| 비용 전에는 양수, 비용 후 음수 | 실거래 부적합 |
| 특정 일자/종목에만 편중 | 과최적화 의심 |
| 거래가 너무 많음 | 수수료/슬리피지에 취약 |
| 거래가 거의 없음 | 모델이 실질적으로 no-trade와 유사 |

---

## 5. OMX 페이지 계획

| 페이지 | 이름 | 목표 | 완료 기준 | 상태 |
|---:|---|---|---|---|
| 1 | 성과 기준 재정의 | smoke/full 구분, 성공 기준, 오픈소스 참고 원칙 문서화 | 본 문서 작성, 검증, 커밋 | 완료 |
| 2 | full baseline/cost gate | test split 전체 baseline과 비용 관문 실행 | full artifact 생성, 요약 수치 확보 | 완료 |
| 3 | contextual bandit full eval | train 기반 모델을 test split 대규모로 평가 | baseline 대비 성과 산출 | 완료 |
| 4 | leaderboard artifact | baseline/RL/cost gate 결과 통합 | JSON/CSV leaderboard 생성 | 완료 |
| 5 | dashboard leaderboard | 웹에서 smoke/full 및 모델별 성과 비교 | API/프론트 build 검증 통과 | 완료 |
| 6 | DQN/PPO 확장 설계 | SB3/Gymnasium 확장 여부 판단 | dependency/리스크/구현안 문서화 | 완료 |
| 7 | 최종 리뷰 | QA, code review, 사용/보류 판단 | 최종 보고서와 QA 증거 확보 | 완료 |

현재 진행률: **7 / 7 = 100%**

`███████ 100%`

---

## 6. 바로 다음 실행 후보

페이지 7까지 완료되어 전체 QA와 최종 사용/보류 판단이 문서화되었다. 이번 7페이지 목표는 종료한다.

권장 명령:

```powershell
omx ultragoal complete-goals
```

현재 Codex thread에는 이전 완료 goal이 남아 있어 OMX ultragoal ledger의 `G001-p001` 완료 reconciliation은 blocked 상태로 기록된다. 실제 작업은 이 브랜치의 한국어 Lore 커밋으로 계속 진행한다.

완료 증거:

1. Python 전체 회귀 테스트: `94 passed, 2 skipped`
2. 프론트 빌드: `svelte-check 0 errors`, `vite build completed`
3. Flask API smoke: `/`, `/api/rl/runs`, performance leaderboard detail/table, `/api/training/status` 모두 200
4. 최종 보고서: `docs/stom_rl_final_review_2026-05-23.md`

주의: 현재 플랫폼은 연구/검증용으로 사용할 수 있지만, contextual bandit 모델은 buy-and-hold와 25bp cost gate를 이기지 못해 실거래 후보가 아니다.

---

## 7. 현재 판단

현재 강화학습은 **가능**하다. 그러나 현재 성과 모델은 **아직 실거래 사용 가능 모델로 확정되지 않았다.**

이번 새 goal의 핵심은 다음이다.

1. 전체 test split에서 기준선을 먼저 고정한다.
2. RL 모델이 그 기준선을 이기는지 본다.
3. 비용과 drawdown을 반영한다.
4. 웹 대시보드에서 모델별로 비교한다.
5. 성과가 부족하면 “왜 부족한지”를 지표로 문서화한다.

---

## 8. 페이지 2 완료 기록: full baseline/cost gate

### 8.1 진행 내용

처음에는 기존 dense baseline runner를 full test split에 직접 실행했다.

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.baselines `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --output-dir webui\rl_runs\stom_1s_2025_baselines_full_test `
  --split test `
  --max-episodes 0 `
  --cost-bps 25 `
  --slippage-bps 0
```

하지만 이 runner는 action/equity row를 전부 저장하는 구조라 full test split에서는 30분 이상 지나도 완료되지 않았다. 이는 모델 문제가 아니라 **대규모 검증용 runner 구조 문제**다.

따라서 새 의존성 없이 `stom_rl.leaderboard`를 추가했다. 이 runner는 같은 long-only policy 의미를 유지하되, full test split에서는 summary artifact를 우선 생성한다.

| 파일 | 목적 |
|---|---|
| `stom_rl/leaderboard.py` | full test split 요약 전용 baseline/cost leaderboard |
| `tests/test_stom_rl_leaderboard.py` | compact leaderboard 회귀 테스트 |
| `webui/rl_runs/stom_1s_2025_baseline_leaderboard_full_test/*` | 실행 결과 artifact, gitignore 대상 |

### 8.2 full test 실행 명령

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.leaderboard `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --output-dir webui\rl_runs\stom_1s_2025_baseline_leaderboard_full_test `
  --split test `
  --max-episodes 0 `
  --cost-bps-values 5,10,15,25 `
  --slippage-bps-values 0 `
  --target-cost-bps 25 `
  --sample-trade-limit 1000
```

실행 시간: **약 9분 18초**
대상: **test split 전체 2,730 episodes**
scenario: **6 policies × 4 cost levels = 24 rows**

### 8.3 25bp 기준 결과

| 순위 | policy | 평균 episode net % | 거래 수 | 거래/episode | hit rate | MDD % | positive session rate |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | buy_and_hold | 0.5126 | 2,730 | 1.00 | 0.4934 | -50.7280 | 0.8611 |
| 2 | no_trade | 0.0000 | 0 | 0.00 | 0.0000 | 0.0000 | 0.0000 |
| 3 | mean_reversion | -23.2925 | 170,868 | 62.59 | 0.0287 | -47.7542 | 0.0000 |
| 4 | volume_filter | -26.1600 | 167,923 | 61.51 | 0.0178 | -49.7977 | 0.0000 |
| 5 | momentum | -27.9136 | 164,944 | 60.42 | 0.0337 | -62.5398 | 0.0000 |
| 6 | random | -77.0568 | 806,047 | 295.26 | 0.0107 | -81.8887 | 0.0000 |

### 8.4 해석

현재 full test split 기준으로는 **buy-and-hold가 가장 강한 baseline**이다.
momentum, mean_reversion, volume_filter는 거래 횟수가 너무 많고 25bp 비용에서 크게 무너졌다.
따라서 다음 RL 모델은 단순히 양수 수익을 내는 것이 아니라, **25bp 비용 후 buy-and-hold를 이겨야 한다.**

주의할 점:

- buy-and-hold의 평균 episode net은 양수지만 MDD가 크다.
- no-trade는 수익은 없지만 MDD가 0이라 리스크 기준 baseline으로 중요하다.
- 다음 contextual bandit full eval은 최소한 no-trade보다 낫고, 가능하면 buy-and-hold 대비 우위를 보여야 한다.

### 8.5 검증

```powershell
C:\Python\64\Python3119\python.exe -m pytest `
  tests\test_stom_rl_leaderboard.py `
  tests\test_stom_rl_baselines.py `
  tests\test_stom_rl_cost_gate.py -q
```

결과:

```text
6 passed
```

다음 페이지는 **페이지 3: contextual bandit full eval**이다.

---

## 9. 페이지 3 완료 기록: contextual bandit full eval

### 9.1 진행 내용

페이지 3에서는 1차 강화학습 모델인 contextual bandit을 smoke가 아닌 full test split으로 평가했다.

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.contextual_bandit `
  --manifest webui\rl_runs\stom_1s_2025_episode_manifest\episode_manifest.json `
  --output-dir webui\rl_runs\stom_1s_2025_contextual_bandit_full_test `
  --train-split train `
  --eval-split test `
  --max-train-episodes 0 `
  --max-eval-episodes 0 `
  --train-sample-stride 10 `
  --eval-sample-stride 5 `
  --cost-bps 25 `
  --slippage-bps 0
```

실행 시간: **약 35분 7초**

### 9.2 학습 데이터 규모

| 항목 | 값 |
|---|---:|
| train episode | 13,256 |
| train sample | 1,568,450 |
| skipped episode | 0 |
| target mean % | -0.3280 |
| target median % | -0.4994 |
| target positive rate | 30.84% |
| ridge alpha | 1.0 |
| train RMSE % | 1.6746 |
| predicted positive rate | 1.45% |

해석:

- train target 자체가 평균/중앙값 모두 음수다.
- 25bp 비용 기준에서 양수 target 비율이 30.84%에 불과하다.
- 모델은 보수적으로 1.45% 구간만 매수 후보로 판단했다.

### 9.3 full test 평가 결과

| 항목 | contextual bandit |
|---|---:|
| eval split | test |
| episode | 2,730 |
| action count | 591,472 |
| trade count | 971 |
| trades/episode | 0.356 |
| avg episode net % | 0.1254 |
| median episode net % | 0.0000 |
| compounded return % | 1,410.0169 |
| avg trade net % | 0.3539 |
| hit rate | 47.99% |
| max drawdown % | -51.5892 |
| 25bp cost gate | false |

### 9.4 baseline 대비

25bp 비용 기준 full test split에서 주요 결과는 다음과 같다.

| 모델/정책 | 평균 episode net % | 거래 수 | 거래/episode | hit rate | MDD % | 판단 |
|---|---:|---:|---:|---:|---:|---|
| buy_and_hold | 0.5126 | 2,730 | 1.000 | 49.34% | -50.7280 | 현재 최강 baseline |
| contextual_bandit | 0.1254 | 971 | 0.356 | 47.99% | -51.5892 | no-trade보다 좋지만 buy-and-hold 미달 |
| no_trade | 0.0000 | 0 | 0.000 | 0.00% | 0.0000 | 리스크 기준선 |
| mean_reversion | -23.2925 | 170,868 | 62.589 | 2.87% | -47.7542 | 부적합 |
| volume_filter | -26.1600 | 167,923 | 61.510 | 1.78% | -49.7977 | 부적합 |
| momentum | -27.9136 | 164,944 | 60.419 | 3.37% | -62.5398 | 부적합 |
| random | -77.0568 | 806,047 | 295.255 | 1.07% | -81.8887 | 부적합 |

### 9.5 결론

contextual bandit full eval은 **학습과 평가가 정상 완료**되었다. 그러나 실사용 후보로는 아직 부족하다.

| 질문 | 답 |
|---|---|
| no-trade보다 좋은가? | 예 |
| 과도한 단순 매매 전략보다 좋은가? | 예 |
| buy-and-hold보다 좋은가? | 아니오 |
| 25bp cost gate를 통과했는가? | 아니오 |
| 바로 실거래 후보인가? | 아니오, 보류 |

핵심 원인:

1. train target 분포가 비용 후 음수로 치우쳐 있다.
2. 단순 ridge contextual bandit은 sequence/position/리스크 상태를 충분히 학습하지 못한다.
3. 평균 수익은 양수지만 MDD가 buy-and-hold보다 더 나쁘다.
4. 25bp 비용 후 buy-and-hold 대비 우위를 만들지 못했다.

### 9.6 다음 단계

다음 페이지는 **페이지 4: leaderboard artifact**다.

목표:

- baseline leaderboard와 contextual bandit 결과를 하나의 JSON/CSV로 통합한다.
- 웹 대시보드에서 smoke/full, baseline/RL, cost gate 통과 여부를 한눈에 비교할 수 있도록 준비한다.

---

## 10. 페이지 4 완료 기록: performance leaderboard artifact

### 10.1 진행 내용

페이지 4에서는 P002의 baseline full leaderboard와 P003의 contextual bandit full eval 결과를 하나의 성과 leaderboard로 통합했다.

| 파일 | 역할 |
|---|---|
| `stom_rl/performance_leaderboard.py` | baseline/RL 결과를 통합한 performance leaderboard 생성 |
| `tests/test_stom_rl_performance_leaderboard.py` | 통합 로직 회귀 테스트 |
| `webui/rl_runs/stom_1s_2025_performance_leaderboard_full_test/performance_leaderboard.json` | 실제 full test 통합 JSON artifact |
| `webui/rl_runs/stom_1s_2025_performance_leaderboard_full_test/performance_leaderboard.csv` | 실제 full test 통합 CSV artifact |

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe -m stom_rl.performance_leaderboard `
  --baseline-report webui\rl_runs\stom_1s_2025_baseline_leaderboard_full_test\leaderboard_report.json `
  --contextual-bandit-report webui\rl_runs\stom_1s_2025_contextual_bandit_full_test\eval_summary.json `
  --output-dir webui\rl_runs\stom_1s_2025_performance_leaderboard_full_test `
  --target-cost-bps 25 `
  --target-slippage-bps 0
```

### 10.2 통합 leaderboard 결과

| rank | source | model/policy | avg episode net % | trade count | MDD % | cost gate | 사용 판단 |
|---:|---|---|---:|---:|---:|---|---|
| 1 | baseline | buy_and_hold | 0.5126 | 2,730 | -50.7280 | false | baseline |
| 2 | rl_model | contextual_bandit | 0.1254 | 971 | -51.5892 | false | watch |
| 3 | baseline | no_trade | 0.0000 | 0 | 0.0000 | false | baseline |
| 4 | baseline | mean_reversion | -23.2925 | 170,868 | -47.7542 | false | baseline |
| 5 | baseline | volume_filter | -26.1600 | 167,923 | -49.7977 | false | baseline |
| 6 | baseline | momentum | -27.9136 | 164,944 | -62.5398 | false | baseline |
| 7 | baseline | random | -77.0568 | 806,047 | -81.8887 | false | baseline |

요약:

| 항목 | 값 |
|---|---|
| best policy | buy_and_hold |
| best RL model | contextual_bandit |
| best RL usability | watch |
| RL models beating buy-and-hold | 없음 |
| RL models passing cost gate | 없음 |

### 10.3 해석

통합 leaderboard 기준으로 contextual bandit은 no-trade보다 낫지만 buy-and-hold보다 낮다. 또한 25bp cost gate를 통과하지 못했으므로 실거래 후보가 아니라 **관찰 대상(watch)** 으로 분류했다.

### 10.4 검증

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_performance_leaderboard.py -q
C:\Python\64\Python3119\python.exe -m py_compile stom_rl\performance_leaderboard.py
```

결과:

```text
1 passed
py_compile 통과
```

다음 페이지는 **페이지 5: dashboard leaderboard**다. 이제 `performance_leaderboard.json/csv`를 웹 강화학습 실험실에서 보여주면 사용자가 모델별 성과와 실사용 판단을 한눈에 볼 수 있다.

---

## 11. 페이지 5 완료 기록: dashboard leaderboard

### 11.1 진행 내용

페이지 5에서는 페이지 4에서 생성한 `performance_leaderboard.json/csv`를 웹 강화학습 실험실에서 직접 비교할 수 있도록 연결했다.

| 파일 | 변경 내용 |
|---|---|
| `webui/rl_dashboard.py` | `performance_leaderboard` artifact 감지, summary/detail 로딩, `leaderboard` CSV table alias 추가 |
| `webui/v2_src/src/lib/api.ts` | `/api/rl/runs/{run}/table/{table}` generic table helper 추가 |
| `webui/v2_src/src/tabs/RLLabTab.svelte` | 성과 리더보드 우선 선택, 리더보드 탭/차트/표 추가, performance run의 trades/equity 미존재 상황 안전 처리 |
| `tests/test_stom_rl_dashboard_api.py` | performance leaderboard fixture와 Flask API smoke 추가 |
| `tests/test_stom_rl_dashboard_tab.py` | 프론트 API/리더보드 마커 회귀 테스트 추가 |

### 11.2 웹에서 보이는 핵심 정보

| 화면 요소 | 목적 |
|---|---|
| 성과 리더보드 run 우선 선택 | 사용자가 가장 중요한 전체 비교 결과를 먼저 보도록 함 |
| 리더보드 차트 | 평균 episode net, MDD, 거래/episode를 동시에 비교 |
| 리더보드 표 | rank, source, model/policy, buy-and-hold 우위 여부, cost gate 통과 여부, usability, 판단 근거 표시 |
| 선택 모델 KPI | performance run에서는 best policy와 RL usability를 함께 표시 |

### 11.3 현재 full test leaderboard 결론

| 항목 | 결과 |
|---|---|
| best policy | buy_and_hold |
| best RL model | contextual_bandit |
| best RL usability | watch |
| RL이 buy-and-hold를 이겼는가 | 아니오 |
| RL이 25bp cost gate를 통과했는가 | 아니오 |

따라서 현재 모델은 “학습/평가/대시보드 비교는 정상 작동”하지만, “실거래 후보”가 아니라 **추가 연구/개선 대상**이다.

### 11.4 검증

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_rl_dashboard_api.py tests\test_stom_rl_dashboard_tab.py tests\test_stom_rl_performance_leaderboard.py -q
npm run build
```

결과:

```text
7 passed
svelte-check 0 errors, 4 existing warnings
vite build completed
```

추가 API smoke:

```text
GET /api/rl/runs/stom_1s_2025_performance_leaderboard_full_test -> 200
GET /api/rl/runs/stom_1s_2025_performance_leaderboard_full_test/table/leaderboard?limit=3 -> 200
```

### 11.5 다음 단계

다음 페이지는 **페이지 6: DQN/PPO 확장 설계**다. 지금까지의 지표상 contextual bandit은 no-trade보다 낫지만 buy-and-hold를 이기지 못했다. 그러므로 다음 단계에서는 단순 회귀형 bandit보다 position 상태, sequence, 리스크 제어, 거래비용을 더 잘 다룰 수 있는 DQN/PPO 계열이 필요한지 판단한다.

---

## 12. 페이지 6 완료 기록: DQN/PPO 확장 설계

### 12.1 진행 내용

페이지 6에서는 현재 STOM 강화학습 환경이 DQN/PPO로 확장 가능한지 검토하고, 새 dependency 추가 전 필요한 계약과 리스크를 문서화했다.

상세 문서:

- `docs/stom_rl_dqn_ppo_extension_design_2026-05-23.md`

### 12.2 공식 가이드 기준

| 자료 | 반영 내용 |
|---|---|
| Gymnasium Env API | `reset`, `step`, `terminated`, `truncated`, `observation_space`, `action_space` 계약 확인 |
| Stable-Baselines3 custom env | custom env는 Gymnasium interface와 `check_env` 검증 필요 |
| Stable-Baselines3 DQN/PPO 정책 문서 | DQN/PPO smoke에는 우선 `MlpPolicy`와 flatten observation을 검토 |

### 12.3 판단 결과

| 항목 | 판단 |
|---|---|
| DQN 적용 | 가능. action이 `hold/buy/sell` discrete 구조다. |
| PPO 적용 | 가능. 다만 sample 비용이 커서 DQN 이후 후순위다. |
| 현재 env 그대로 SB3 사용 | 불완전. 실제 `gymnasium.Env` 상속과 `gymnasium.spaces` adapter가 필요하다. |
| 새 dependency 추가 | 사용자 명시 승인 전까지 보류한다. |
| 다음 구현 후보 | `stom_rl/gym_adapter.py` + `check_env` + DQN smoke |

### 12.4 핵심 결론

현재 contextual bandit은 full test split에서 no-trade보다 낫지만 buy-and-hold를 이기지 못했다. DQN/PPO는 이 한계를 개선할 수 있는 후보지만, 실거래 성과를 보장하지 않는다. 다음 구현 단계는 무작정 장시간 학습이 아니라 **Gymnasium adapter와 DQN smoke 검증**이어야 한다.

### 12.5 검증

```powershell
C:\Python\64\Python3119\python.exe -m py_compile stom_rl\trading_env.py stom_rl\contextual_bandit.py stom_rl\performance_leaderboard.py
```

결과: py_compile 통과.

다음 페이지는 **페이지 7: 최종 리뷰/QA/사용 판단**이다.

---

## 13. 페이지 7 완료 기록: 최종 리뷰/QA/사용 판단

### 13.1 진행 내용

페이지 7에서는 지금까지 구축한 강화학습 성과 모델 고도화 흐름을 전체 검증하고, 현재 모델을 실제 사용할 수 있는지 최종 판단했다.

상세 문서:

- `docs/stom_rl_final_review_2026-05-23.md`

### 13.2 검증 결과

| 검증 | 결과 |
|---|---|
| Python 전체 테스트 | `94 passed, 2 skipped, 2 warnings` |
| 프론트 빌드 | `svelte-check 0 errors`, `vite build completed` |
| Flask API smoke | 핵심 endpoint 모두 200 |
| 최종 성과 판단 | contextual bandit은 watch, 실거래 보류 |

### 13.3 최종 판단

| 용도 | 판단 |
|---|---|
| 연구/검증 플랫폼 | 사용 가능 |
| STOM 2025 1초봉 RL 실험 | 사용 가능 |
| 웹 대시보드 성과 비교 | 사용 가능 |
| 현재 contextual bandit 실거래 | 보류 |
| 다음 모델 개발 기반 | 사용 가능 |

최종 결론:

**플랫폼 구축 목표는 달성했다. 모델 수익성 목표는 아직 달성하지 못했다.**

다음 목표를 새로 잡는다면 `Gymnasium adapter + check_env + DQN smoke`부터 시작한다.
