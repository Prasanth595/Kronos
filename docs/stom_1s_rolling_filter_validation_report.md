# STOM 1초봉 pred60 rolling 조건식 검증 보고서

작성일: 2026-05-08

## 1. 목적

이전 단계의 filter-search는 같은 표본 안에서 조건식을 고르고 같은 표본에서 성과를 확인했다.
따라서 조건식이 실제로 의미 있는지, 아니면 과최적화인지 분리 검증이 필요했다.

이번 단계에서는 **앞쪽 기간에서 best filter를 선택하고 뒤쪽 기간에 그대로 적용하는 rolling train/test 검증**을 추가했다.

## 2. 구현 내용

`finetune/search_stom_1s_filters.py`에 다음 기능을 추가했다.

- `rolling_validate_filters`
- `write_rolling_filter_report`
- CLI 옵션:
  - `--rolling-validate`
  - `--rolling-train-periods`
  - `--rolling-test-periods`
  - `--rolling-step-periods`

대시보드에는 다음 API/패널을 추가했다.

- `GET /api/stom/filter-reports`
- filter-search JSON 표시
- rolling validation JSON 표시
- fold별 train net, test net, baseline net, 개선폭 표시

## 3. 실행 명령

```powershell
python finetune\search_stom_1s_filters.py `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_walkforward30x3_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --prefix stom_1s_pred60_walkforward30x3_eval_kronos_rolling30x30 `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10 `
  --min-trades 10 `
  --min-periods 10 `
  --min-coverage 0.25 `
  --rolling-validate `
  --rolling-train-periods 30 `
  --rolling-test-periods 30 `
  --rolling-step-periods 30
```

생성 artifact:

- `webui/qlib_backtests/stom_1s_pred60_walkforward30x3_eval_kronos_rolling30x30.rolling_filter_validation.json`
- `webui/qlib_backtests/stom_1s_pred60_walkforward30x3_eval_kronos_rolling30x30.rolling_filter_validation_folds.csv`

## 4. rolling 검증 결과

| 항목 | 값 |
| --- | ---: |
| fold_count | 2 |
| total_period_count | 90 |
| train_periods | 30 |
| test_periods | 30 |
| total_test_trade_count | 26 |
| avg_train_net_return_pct | +0.0519% |
| avg_test_net_return_pct | -0.0351% |
| avg_test_baseline_net_return_pct | -0.2438% |
| avg_test_improvement_net_pct | +0.2087%p |
| test_direction_hit_rate_weighted | 0.4615 |
| positive_test_fold_rate | 0.5 |
| overfit_gap_pct | +0.0870%p |
| is_profitable_after_cost | false |

fold별 결과:

| fold | selected filter | test net | baseline net | 개선폭 |
| ---: | --- | ---: | ---: | ---: |
| 1 | `ret>=0.05`, `range<=0.1`, `vol<=0.2` | +0.0604% | -0.2316% | +0.2921%p |
| 2 | `ret>=0.05`, `range<=0.1`, `vol<=0.2` | -0.1305% | -0.2559% | +0.1253%p |

## 5. 해석

이번 rolling 검증의 핵심은 다음과 같다.

```text
조건식은 baseline 대비 손실을 줄이는 효과가 out-of-sample에서도 유지됨.
하지만 25bp 비용 후 평균 test net은 아직 -0.0351%로 음수임.
따라서 조건식은 의미 있는 후보이지만 실전 승인 조건은 아님.
```

즉, 이전 opportunistic filter의 `net -0.0089%`는 완전히 무의미한 과최적화로 보기는 어렵다.
다만 rolling test에서는 평균 net이 다시 음수이므로, 아직 자동 매수 추천에 연결하면 안 된다.

## 6. 대형 walk-forward 실행 준비 상태

필수 경로 확인:

- pred60 prediction CSV: 존재
- pred60 fine-tuned checkpoint: 존재
- pred60 processed dataset: 존재

다음 대형 평가 예상 규모:

```text
max_sessions 100
max_asofs 5
max_symbols 50
예상 windows: 최대 25,000
예상 rows per mode: 최대 1,500,000
```

이 평가는 GPU 추론 시간이 길 수 있으므로 별도 장시간 실행 단계로 분리한다.

## 7. 다음 판단 기준

다음 대형 walk-forward에서 아래 조건을 동시에 만족해야 실전 후보로 승격할 수 있다.

1. rolling avg_test_net_return_pct가 0보다 커야 한다.
2. baseline 대비 개선폭이 여러 fold에서 반복되어야 한다.
3. positive_test_fold_rate가 0.5를 명확히 넘어야 한다.
4. 거래 수가 너무 적어서는 안 된다.
5. random baseline과 비교해 방향성과 net이 모두 우위여야 한다.
