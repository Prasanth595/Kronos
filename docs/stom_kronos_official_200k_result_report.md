# STOM Kronos 공식 200k 학습 성과 보고서

작성일: 2026-05-09
대상 모델: `stom_1s_grid_pred60_official_200k`

## 1. 결론 요약

공식 Kronos 순서인 **STOM tokenizer fine-tuning → STOM predictor fine-tuning → holdout 평가/시각화**는 실제 checkpoint 기준으로 완료됐다.

그러나 현재 200k pilot 결과는 **실매매 확대 승인 수준이 아니다.**

핵심 이유:

1. 방향 정확도는 `0.4188`로 random baseline `0.4084`보다 약간 높지만, 차이가 작다.
2. Top-K 실제 평균 수익은 비용 전 `+0.0511%` 수준인데, 비용/슬리피지 25bp 반영 후 `-0.1989%`로 음수다.
3. rolling validation 8개 fold 모두 비용 반영 후 평균 test net이 음수이며, target 25bp gate가 실패했다.
4. 따라서 1M/5M/full-window 성과 목적 확대는 현재 evidence 기준으로 보류가 맞다.

## 2. 공식 학습 완료 근거

| 단계 | 결과 | 근거 |
| --- | --- | --- |
| tokenizer 20k | 완료 | duration 567.944628초, best val_loss 0.004013419676455669 |
| tokenizer 200k | 완료 | duration 3,211.134006초, best val_loss 0.002904271284851711 |
| predictor 200k | 완료 | duration 4,129.433555초, best val_loss 2.131037336307764 |
| holdout 예측 | 완료 | 184,800 rows, 3,080 windows, 334 symbols |
| 대시보드 그래프 | 완료 | `/api/stom/prediction` status 200, chart JSON 생성 |

학습 checkpoint:

```text
Tokenizer: finetune/outputs/stom_1s_grid_pred60_official_200k/finetune_tokenizer/checkpoints/best_model
Predictor: finetune/outputs/stom_1s_grid_pred60_official_200k/finetune_predictor/checkpoints/best_model
```

## 3. Holdout 실제값 vs 예측값 성과

평가 파일:

```text
webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos.csv
webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_comparison.json
```

| 지표 | Official 200k Kronos | Persistence | Random |
| --- | ---: | ---: | ---: |
| rows | 184,800 | 184,800 | 184,800 |
| windows | 3,080 | 3,080 | 3,080 |
| symbols | 334 | 334 | 334 |
| MAE | 173.0052 | 163.4523 | 167.8729 |
| RMSE | 441.4880 | 400.7079 | 402.1609 |
| MAPE | 0.3382% | 0.3184% | 0.3251% |
| 방향 정확도 | 0.4188 | 0.1487 | 0.4084 |
| Top-K hit rate | 0.4146 | 0.1567 | 0.4073 |
| Top-K avg actual return | 0.0518% | 0.0601% | 0.0513% |

해석:

- 방향 정확도는 random보다 약간 높지만, MAPE/MAE/RMSE는 persistence보다 나쁘다.
- Top-K avg actual return도 persistence baseline보다 낮다.
- 따라서 “예측 그래프는 생성 가능”하지만 “거래 신호로 바로 사용 가능”하다고 보기 어렵다.

## 4. 비용 반영 Qlib-style Top-K 결과

파일:

```text
webui/qlib_backtests/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos.qlib_topk5.json
```

| 항목 | 값 |
| --- | ---: |
| periods | 500 |
| trades | 2,470 |
| gross avg return | 0.051069% |
| net avg return, 25bp cost | -0.198931% |
| hit rate | 0.430364 |
| direction hit rate | 0.414575 |
| cumulative return | -63.178640% |
| max drawdown | -63.178640% |
| sharpe per period | -11.982310 |

결론: 비용 전 수익폭이 너무 작아 25bp 비용/슬리피지 환경에서는 손실 구조다.

## 5. 조건식/필터 보완 결과

파일:

```text
webui/qlib_backtests/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos.filter_search.json
```

Best filter:

```text
ret>=-0.1|cons>=0|range<=0.05|amt_q>=0|vol<=none
```

| 항목 | baseline top-k | best filter |
| --- | ---: | ---: |
| period_count | 500 | 464 |
| trade_count | 2,470 | 1,320 |
| avg gross return | 0.051799% | 0.063075% |
| avg net return, 25bp | -0.198931% | -0.173905% |
| improvement vs baseline net | - | +0.025026%p |

해석:

- 필터는 손실을 조금 줄였지만 net return을 양수로 바꾸지는 못했다.
- “조건식으로 보완 가능성”은 있으나, 현재 모델/표본에서는 충분하지 않다.

## 6. Rolling validation / cost gate

파일:

```text
webui/qlib_backtests/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos_rolling100x50.rolling_filter_validation.json
webui/qlib_backtests/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos_cost_gate.cost_gate.json
```

Rolling summary:

| 항목 | 값 |
| --- | ---: |
| fold_count | 8 |
| total_test_trade_count | 212 |
| avg_train_net_return_pct | -0.037471 |
| avg_test_net_return_pct | -0.271940 |
| avg_test_baseline_net_return_pct | -0.201852 |
| avg_test_improvement_net_pct | -0.070088 |
| test_direction_hit_rate_weighted | 0.429245 |
| positive_test_fold_rate | 0.0 |
| overfit_gap_pct | 0.234468 |
| is_profitable_after_cost | false |

Cost gate:

```text
decision = hold_expand_200k
expand_training_allowed = false
target_total_cost_bps = 25
passes_gate = false
```

## 7. 이전 pred60 비공식/기존 결과와 비교

기존 `stom_1s_pred60_walkforward100x5x50_eval`은 공식 tokenizer fine-tuning을 거치지 않은 결과다.

| 지표 | 기존 pred60 | 공식 200k |
| --- | ---: | ---: |
| 방향 정확도 | 0.4312 | 0.4188 |
| Top-K hit rate | 0.4328 | 0.4146 |
| MAPE | 0.3334% | 0.3382% |
| MAE | 169.4190 | 173.0052 |

현재 200k 공식 모델은 기존 결과보다 약하다. 가능한 원인은 다음이다.

1. 200k는 전체 73,718,875 train windows 중 극히 일부다.
2. `full_sequential` 200k는 “정확한 순차 coverage 검증용” 성격이 강해, random sample보다 날짜/종목 대표성이 낮을 수 있다.
3. tokenizer와 predictor 모두 1 epoch pilot이라 충분히 수렴했다고 보기 어렵다.
4. 1초봉/60초 뒤 예측은 노이즈가 커서 방향성 edge가 작다.
5. 비용 25bp 대비 60초 평균 기대수익 자체가 너무 작다.

## 8. 판단

- 그래프/대시보드 확인 목적: **성공**
- Kronos 공식 순서 준수: **성공**
- 현재 모델로 실전 매매 사용: **비권장**
- 1M/5M/full-window 성과 목적 확대: **보류**
- 단, 사용자가 “수익성 gate와 무관하게 전체 데이터 공식 학습 자체가 목적”이라고 명시하면 8단계에서 장시간 실행 계획으로 전환 가능하다.

## 9. pred30 진행 판단

현재는 pred30 200k/full-window를 즉시 실행하지 않는다.

판단 근거:

- pred60 official 200k도 cost gate를 통과하지 못했다.
- pred30은 더 짧은 예측 horizon이므로 25bp 비용을 이기려면 더 강한 순간 방향 edge가 필요하다.
- 새 tokenizer/predictor 세트를 다시 학습해야 하므로, 성과 근거 없이 바로 200k 이상으로 확대하는 것은 시간 대비 효율이 낮다.

권장 대안:

1. 대시보드에서 official 200k pred60 그래프를 먼저 확인한다.
2. 실전 목적이면 비용 구조와 조건식/score 개선을 먼저 한다.
3. 연구 비교 목적이면 pred30은 20k tokenizer/predictor quick pilot부터 시작한다.
4. 사용자가 “수익성 gate와 관계없이 pred30 공식 비교도 진행”이라고 명시하면 동일 pipeline으로 pred30을 수행한다.
