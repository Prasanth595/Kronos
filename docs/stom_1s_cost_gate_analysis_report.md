# STOM 1초봉 pred60 cost sensitivity gate 자동화 보고서

작성일: 2026-05-09

## 1. 이번 단계의 목표

이전 단계에서 pred60 `budget_20k` checkpoint는 대형 walk-forward 기준으로 방향성 신호는 있었지만 25bp 비용 후 수익성이 부족했다. 이번 단계에서는 같은 판단을 사람이 수동으로 해석하지 않도록, 기존 filter-search/rolling-validation artifact를 입력으로 받아 **비용 민감도와 확대 학습 gate를 자동 계산하는 코드**를 추가했다.

핵심 목적:

```text
rolling gate를 통과하지 못하면 expand_200k 학습을 실행하지 않는다.
```

## 2. 추가된 기능

`finetune/search_stom_1s_filters.py`에 `--gate-analysis` 모드를 추가했다.

```powershell
python finetune\search_stom_1s_filters.py `
  --gate-analysis `
  --filter-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos.filter_search.json `
  --rolling-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos_rolling100x50.rolling_filter_validation.json `
  --output-dir webui\qlib_backtests `
  --prefix stom_1s_pred60_walkforward100x5x50_eval_kronos_cost_gate `
  --total-cost-bps-grid 5,10,15,25 `
  --target-total-cost-bps 25 `
  --min-total-test-trades 100
```

생성되는 산출물:

```text
webui/qlib_backtests/stom_1s_pred60_walkforward100x5x50_eval_kronos_cost_gate.cost_gate.json
webui/qlib_backtests/stom_1s_pred60_walkforward100x5x50_eval_kronos_cost_gate.cost_gate_rolling_sensitivity.csv
```

이 산출물은 대시보드에서 `cost_sensitivity_gate` artifact로 인식된다. 대용량/실험 산출물이므로 git commit에는 포함하지 않는다.

## 3. Gate 기준

기본 gate 기준은 다음과 같다.

| 기준 | 기본값 | 의미 |
| --- | ---: | --- |
| `min_avg_test_net_pct` | 0.0 | rolling 평균 test net이 0 이상이어야 함 |
| `min_positive_test_fold_rate` | 0.5 | fold 절반 이상이 양수여야 함 |
| `min_improvement_net_pct` | 0.0 | baseline 대비 개선이 음수이면 안 됨 |
| `min_total_test_trades` | 100 | 너무 적은 거래 수로 통과하면 안 됨 |
| `target_total_cost_bps` | 25 | 실제 판단 비용 기준 |

## 4. 실제 대형 artifact 적용 결과

| total cost | rolling avg test net | positive fold rate | total test trades | gate |
| ---: | ---: | ---: | ---: | --- |
| 5bp | +0.0234% | 0.500 | 150 | PASS |
| 10bp | -0.0266% | 0.375 | 150 | FAIL |
| 15bp | -0.0766% | 0.375 | 150 | FAIL |
| 25bp | -0.1766% | 0.250 | 150 | FAIL |

해석:

- 5bp처럼 매우 낮은 비용 가정에서는 gate가 통과된다.
- 그러나 실제 판단 기준인 25bp에서는 평균 test net이 -0.1766%이고 positive fold rate가 0.25라서 실패한다.
- 따라서 현재 기준의 결론은 그대로 **`expand_200k` 보류**다.

## 5. Filter sensitivity 결과

동일한 best robust filter의 비용 민감도는 다음과 같다.

| total cost | best filter avg net |
| ---: | ---: |
| 5bp | +0.0734% |
| 10bp | +0.0234% |
| 15bp | -0.0266% |
| 25bp | -0.1266% |

best filter 자체도 10bp 이하에서는 양수 가능성이 있지만, 25bp 기준에서는 여전히 음수다. 따라서 비용 조건을 현실보다 낮게 두고 학습 확대를 승인하면 안 된다.

## 6. 대시보드 반영

`webui/stom_dashboard.py`는 이제 다음 artifact 유형을 구분한다.

```text
filter_search
rolling_filter_validation
cost_sensitivity_gate
```

`webui/templates/stom_dashboard.html`의 filter validation 패널에서도 cost gate artifact를 선택하면 다음을 확인할 수 있다.

- 최종 decision: `ALLOW` 또는 `HOLD`
- target cost bps
- target cost 기준 rolling avg test net
- positive fold rate
- 비용 시나리오별 PASS/FAIL

## 7. 현재 판단

```text
25bp target gate: FAIL
expand_200k 학습: 보류
다음 단계: score/filter 리디자인 또는 pred30/pred60 ensemble 후보 생성 후 같은 gate 재검증
```

## 8. 현재 진행률

| 페이지 | 내용 | 완료율 | 상태 |
| --- | --- | ---: | --- |
| Page 1 | STOM tick DB 구조 분석 | 100% | 완료 |
| Page 2 | 전체 주식 테이블 OHLCV 추출/1초봉 QlibDataset export | 100% | 완료 |
| Page 3 | bounded/pilot 학습 가능성 검증 | 75% | gate 자동화로 검증 강화 |
| Page 4 | pred30/pred60 전체 dataset 학습 루프 연결 | 100% | 완료 |
| Page 5 | budget_20k fine-tuning | 100% | pred30/pred60 checkpoint 생성 완료 |
| Page 6 | checkpoint 예측/대형 walk-forward/rolling 검증 | 96% | 비용 gate 자동화 완료 |
| Page 7 | 웹 대시보드 예측/백테스트/filter/gate 확인 | 88% | cost gate 표시 추가 |
| Page 8 | staged full-training 실행 계획 | 90% | gate 기준 반영 완료 |
| Page 9 | expand_200k/1M/5M/full-window 실제 확대 학습 | 0% | target gate 미충족으로 보류 |

전체 진행률은 **93%**로 본다. 단, 이 수치는 파이프라인과 검증 체계 기준이며, 모든 possible window의 실제 학습 완료율이 아니다.
