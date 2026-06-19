# STOM 1초봉 pred60 walk-forward 조건식 필터 검증 보고서

작성일: 2026-05-08

## 1. 목적

이 단계의 목적은 이전 제한 샘플 평가에서 `direction_accuracy=0.4444`로 보였던
pred60 checkpoint가 더 넓은 holdout walk-forward 표본에서도 의미가 있는지 확인하고,
Kronos 예측값을 그대로 쓰지 않고 **예측 시점에 이미 알 수 있는 조건식**으로 보완할 수
있는지 검증하는 것이다.

검증 질문은 다음과 같다.

1. 60초 후 방향성 적중률이 작은 표본에서만 우연히 높았는가?
2. Qlib-style Top-K 비용 차감 수익률이 개선되는가?
3. 조건식 필터가 미래 실제값을 보지 않고도 손실을 줄이는가?
4. 대시보드에서 실제값/예측값과 백테스트 artifact를 안전하게 확인할 수 있는가?

## 2. 사용 데이터와 실행 조건

- 데이터: `finetune/qlib_exports/stom_1s_grid_pred60_full/processed_datasets`
- 모델: `finetune/outputs/stom_1s_grid_pred60_full_budget/finetune_predictor/checkpoints/best_model`
- lookback: 300초
- horizon: 60초
- 평가 범위: test split 중 30개 session, session당 3개 as-of 시각
- 평가 window: 546개
- 예측 row: 32,760개
- 종목 수: 146개
- 리밸런싱 period: 90개
- Top-K: 5
- 비용 가정: 수수료 15bp + 슬리피지 10bp = 25bp

실행 명령:

```powershell
python finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred60_full_budget\finetune_predictor\checkpoints\best_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred60_walkforward30x3_eval `
  --lookback-window 300 `
  --predict-window 60 `
  --max-symbols 20 `
  --max-asofs 3 `
  --max-sessions 30 `
  --stride 300 `
  --batch-size 4 `
  --top-k 5 `
  --device cuda:0
```

## 3. 확장 walk-forward 방향성 결과

| 모델 | direction_accuracy | 평균 실제 등락률 | Top-K 평균 실제 등락률 | Top-K hit rate |
| --- | ---: | ---: | ---: | ---: |
| Kronos pred60 | 0.4084 | +0.0378% | +0.0134% | 0.4161 |
| Persistence | 0.1832 | +0.0378% | +0.0463% | 0.1767 |
| Random(seed 고정) | 0.4084 | +0.0378% | +0.0627% | 0.4004 |

해석:

- Kronos는 persistence보다 방향성에서는 크게 낫다.
- 그러나 같은 표본에서 random baseline도 0.4084가 나왔으므로 `0.4084` 자체를 강한 알파로 확정할 수 없다.
- Top-K gross는 플러스지만 1초봉 60초 매매에서 25bp 비용을 차감하면 수익성이 무너진다.

## 4. Qlib-style Top-K 비용 차감 결과

실행 명령:

```powershell
python finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_walkforward30x3_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10
```

결과:

| 항목 | 값 |
| --- | ---: |
| period_count | 90 |
| trade_count | 447 |
| avg_gross_return_pct | +0.0123% |
| avg_net_return_pct | -0.2377% |
| hit_rate | 0.4049 |
| direction_hit_rate | 0.4161 |
| cumulative_return_pct | -19.3225% |
| max_drawdown_pct | -19.3225% |

판단:

- 현재 모델을 조건식 없이 Top-K 매수 추천에 바로 쓰면 비용 후 손실이다.
- 60초 horizon에서 25bp 비용은 매우 큰 허들이므로, 예측 방향성만으로는 부족하다.

## 5. 조건식 필터 탐색 방법

이번 조건식은 실제 미래값을 사용하지 않고, 예측 시점에 알 수 있는 값만 사용했다.

사용한 입력:

- `pred_return_window`: Kronos가 예측한 60초 후 등락률
- `pred_path_consistency`: 예측 경로가 기준가 위/아래에 일관되게 머문 비율
- `pred_range_pct`: 예측 경로의 변동 폭
- `history_mean_amount`: lookback 구간 평균 거래대금
- `history_volatility_pct`: lookback 구간 가격 변동성

탐색 명령:

```powershell
python finetune\search_stom_1s_filters.py `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_walkforward30x3_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --prefix stom_1s_pred60_walkforward30x3_eval_kronos `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10 `
  --min-trades 30 `
  --min-periods 30 `
  --min-coverage 0.5
```

## 6. 조건식 탐색 결과

### 6.1 Robust 조건식

최소 coverage 50%, 최소 30 trades, 최소 30 periods 조건을 둔 보수적 탐색 결과다.

| 항목 | 값 |
| --- | ---: |
| filter | `pred_return >= 0.05`, `history_volatility <= 0.2` |
| period_count | 56 |
| trade_count | 82 |
| coverage | 62.22% |
| avg_gross_return_pct | +0.0796% |
| avg_net_return_pct | -0.1008% |
| direction_hit_rate | 0.4634 |
| cumulative_return_pct | -5.5769% |
| baseline 대비 net 개선 | +0.1370%p |

### 6.2 Opportunistic 조건식

coverage 10% 이상으로 더 공격적으로 좁힌 탐색 결과다.

| 항목 | 값 |
| --- | ---: |
| filter | `pred_return >= 0.05`, `pred_range_pct <= 0.1`, `history_volatility <= 0.2` |
| period_count | 33 |
| trade_count | 42 |
| coverage | 36.67% |
| avg_gross_return_pct | +0.1995% |
| avg_net_return_pct | -0.0089% |
| direction_hit_rate | 0.4762 |
| cumulative_return_pct | -0.3629% |
| baseline 대비 net 개선 | +0.2288%p |

해석:

- 조건식은 손실을 확실히 줄였다.
- 예측 등락률이 충분히 양수이고, 예측 경로 폭과 직전 변동성이 낮은 구간만 고르면 비용 후 손실이 거의 0에 가까워진다.
- 그러나 아직 비용 후 양수 전환은 아니다.
- 이번 grid에서는 거래대금 quantile 조건이 최종 best에 선택되지 않았다. 현재 표본에서는 거래대금 조건보다 예측 등락률, 예측 경로 안정성, 직전 변동성이 더 직접적인 필터였다.

## 7. 대시보드 반영 사항

평가 CSV에는 다음 예측 시점 feature가 추가되었다.

- `pred_path_consistency`
- `pred_range_pct`
- `history_volatility_pct`
- `history_return_pct`
- `history_mean_amount`
- `history_last_amount`
- `history_mean_volume`
- `history_last_volume`

또한 `webui/qlib_backtests`에는 일반 Qlib Top-K JSON과 filter-search JSON이 함께 생성된다.
기존 대시보드는 모든 JSON을 Qlib backtest로 표시했기 때문에 filter-search JSON을 선택하면
`metrics`가 없어 오류가 날 수 있었다. 이번 단계에서 `metrics`가 있는 Qlib Top-K artifact만
목록에 표시하도록 안전장치를 추가했다.

## 8. 현재 결론

```text
방향성 신호: 제한적으로 존재
랜덤 대비 우위: 아직 불충분
비용 차감 수익성: 조건식 적용 후 크게 개선되지만 아직 양수 아님
실전 추천 사용: 보류
다음 필요 작업: 더 큰 walk-forward와 rolling train/test 방식의 조건식 과최적화 검증
```

즉, `정확도 0.4라서 완전히 무의미하다`라기보다는
`persistence보다는 낫고 조건식으로 손실을 크게 줄일 수 있으나, 아직 실제 매수 추천 시스템에 투입할 정도는 아니다`가
현재의 정확한 결론이다.

## 9. 다음 권장 검증

1. `max_sessions 100`, `max_asofs 5`, `max_symbols 50` 이상으로 확대 평가한다.
2. 조건식 탐색을 같은 데이터에서 고르고 같은 데이터에서 평가하지 말고, 앞쪽 session에서 조건식을 찾고 뒤쪽 session에서 검증하는 rolling 방식으로 바꾼다.
3. 비용을 25bp, 15bp, 5bp로 나누어 민감도 분석한다.
4. pred30/pred60 ensemble, 1초봉/1분봉 혼합 feature, 거래대금 상위 rank feature를 추가한다.
5. 대시보드에 filter-search 결과 표와 best-filter 적용 equity curve를 별도 패널로 추가한다.

## 10. 후속 rolling 검증 링크

이 보고서 이후 같은 pred60 walk-forward CSV에 대해 rolling train/test 조건식 검증을 추가로 수행했다.

상세 결과는 `docs/stom_1s_rolling_filter_validation_report.md`를 참조한다.

핵심 결론:

- rolling avg_test_net_return_pct: -0.0351%
- rolling avg_test_baseline_net_return_pct: -0.2438%
- baseline 대비 개선폭: +0.2087%p
- 비용 후 양수 전환: 실패

따라서 조건식은 baseline 대비 손실을 줄이지만, 아직 실전 자동 매수 승인 조건은 아니다.
