# STOM 1초봉 pred60 대형 walk-forward 게이트 검토 보고서

작성일: 2026-05-09

## 1. 이번 단계의 목적

`expand_200k` 또는 그 이상의 학습을 바로 실행하기 전에, 현재 `budget_20k` pred60 checkpoint가 더 큰 holdout walk-forward 구간에서도 실제 매매 후보로 확대할 가치가 있는지 검증했다.

중요한 전제는 다음과 같다.

- 전체 STOM 1초봉 QlibDataset export는 이미 완료되어 있다.
- pred60 기준 가능한 train window는 73,718,875개, val window는 15,938,107개다.
- 그러나 현재 실제 fine-tuning checkpoint는 `budget_20k` 단계, 즉 train 20,000개와 val 4,000개로 학습된 모델이다.
- 이번 단계는 추가 학습이 아니라 **추가 학습을 진행할지 판단하기 위한 대형 검증 게이트**다.

## 2. 사용한 평가 데이터와 산출물

| 항목 | 값 |
| --- | ---: |
| horizon | 60초 |
| checkpoint | `finetune/outputs/stom_1s_grid_pred60_full_budget/finetune_predictor/checkpoints/best_model` |
| dataset | `finetune/qlib_exports/stom_1s_grid_pred60_full/processed_datasets` |
| max sessions | 100 |
| max as-of per session | 5 |
| max symbols | 50 |
| selected windows | 3,080 |
| rebalance periods | 500 |
| symbols | 334 |
| rows per mode | 184,800 |

주요 산출물은 대용량이므로 git commit 대상이 아니며, 로컬 실행 결과로만 보존한다.

```text
webui/stom_predictions/stom_1s_pred60_walkforward100x5x50_eval_comparison.json
webui/stom_predictions/stom_1s_pred60_walkforward100x5x50_eval_kronos.csv
webui/qlib_backtests/stom_1s_pred60_walkforward100x5x50_eval_kronos.qlib_topk5.json
webui/qlib_backtests/stom_1s_pred60_walkforward100x5x50_eval_kronos.filter_search.json
webui/qlib_backtests/stom_1s_pred60_walkforward100x5x50_eval_kronos_rolling100x50.rolling_filter_validation.json
```

## 3. 모델 방향성 평가

| 모델 | 방향 정확도 | Top-K 실제 평균 등락률 | Top-K hit rate | 해석 |
| --- | ---: | ---: | ---: | --- |
| Kronos pred60 | 0.4312 | +0.0554% | 0.4328 | random보다 높지만 매우 강한 신호는 아님 |
| Random baseline | 0.4084 | +0.0513% | 0.4073 | 시장 자체/표본 효과가 포함된 기준선 |
| Persistence baseline | 0.1487 | +0.0601% | 0.1567 | 단순 지속성은 방향성에서 크게 열위 |

해석:

- 이전에 우려했던 `0.4 전후 정확도`는 이번 더 큰 표본에서 Kronos가 random보다 조금 높게 나왔다.
- 다만 차이는 약 +2.27%p 수준이며, 이것만으로 자동매매 수익성을 주장할 수는 없다.
- 따라서 핵심 판단 지표는 방향 정확도 단독이 아니라 **비용 반영 후 Top-K/조건식/rolling 검증 성과**다.

## 4. Qlib-style Top-K 비용 반영 결과

거래 비용은 수수료 15bp + 슬리피지 10bp, 총 25bp로 반영했다.

| 항목 | 값 |
| --- | ---: |
| period count | 500 |
| trade count | 2,470 |
| avg gross return | +0.0547% |
| avg net return | -0.1953% |
| direction hit rate | 0.4328 |
| cumulative return | -62.4982% |
| max drawdown | -62.4982% |
| sharpe per period | -12.2191 |

결론:

- 예측 방향성은 random보다 높지만, 거래 1회당 비용 25bp를 넘지 못했다.
- 현재 Top-K 단독 방식은 실전 매수 조건으로 사용할 수 없다.

## 5. Robust filter search 결과

비용 후 손실을 줄이기 위해 예측 수익률, 예측 경로 일관성, 거래대금 분위수, 변동성 조건을 조합했다.

| 항목 | baseline Top-K | best robust filter |
| --- | ---: | ---: |
| filter | 없음 | `ret>=-0.05|cons>=0.8|range<=none|amt_q>=0.75|vol<=none` |
| period count | 500 | 273 |
| trade count | 2,470 | 417 |
| avg gross return | +0.0554% | +0.1030% |
| avg net return | -0.1953% | -0.1266% |
| direction hit rate | 0.4328 | 0.4772 |
| coverage | 1.0000 | 0.5460 |
| cumulative return | -62.4982% | -29.8892% |

해석:

- 조건식은 baseline 대비 손실을 줄였다.
- 하지만 비용 후 평균 수익률은 여전히 음수다.
- 따라서 이 조건식도 아직 실전 자동매수 조건이 아니라, 다음 실험의 후보 조건일 뿐이다.

## 6. Rolling train/test validation 결과

조건식 과최적화를 막기 위해 앞 100 periods에서 조건식을 선택하고 다음 50 periods에 적용하는 rolling validation을 실행했다.

| 항목 | 값 |
| --- | ---: |
| fold count | 8 |
| train periods | 100 |
| test periods | 50 |
| total test trades | 150 |
| avg train net return | +0.0351% |
| avg test net return | -0.1766% |
| avg test baseline net return | -0.1945% |
| test improvement vs baseline | +0.0179%p |
| weighted test direction hit | 0.5200 |
| positive test fold rate | 0.2500 |
| overfit gap | 0.2117%p |
| profitable after cost | false |

해석:

- rolling test에서 baseline보다 손실은 약간 줄었다.
- 하지만 개선폭이 작고, positive fold rate가 25%에 그쳤다.
- train 구간에서는 좋아 보이지만 test 구간에서 무너지는 양상이 있어 조건식 과최적화 위험이 남아 있다.

## 7. 게이트 판단

이번 단계의 결론은 다음과 같다.

```text
expand_200k 실제 학습: 보류
full_window 전량 학습: 보류
현재 budget_20k 모델의 대형 평가 결과: 방향성 신호는 있으나 비용 후 수익성 미달
```

보류 이유:

1. Kronos 방향 정확도는 random보다 높지만 차이가 작다.
2. Qlib-style Top-K의 비용 후 평균 수익률이 -0.1953%다.
3. best robust filter도 비용 후 평균 수익률이 -0.1266%다.
4. rolling validation의 평균 test net이 -0.1766%로 음수다.
5. positive test fold rate가 25%로 낮아 기간 안정성이 부족하다.

따라서 현재 상태에서 학습량만 200k, 1M, 5M으로 키우는 것은 GPU 시간을 많이 쓰면서도 개선 여부가 불확실하다. 다음 단계는 학습량 확대가 아니라 **score/filter 구조 개선과 비용 민감도 분석**이다.

## 8. 다음 권장 작업

다음 작업은 아래 순서가 안전하다.

1. 비용 민감도 분석: 5bp, 10bp, 15bp, 25bp에서 Top-K와 조건식 결과 비교
2. pred30/pred60 ensemble score 후보 생성
3. `pred_return_window`, `pred_path_consistency`, `history_mean_amount`, `history_volatility_pct` 외 추가 후보 feature 검토
4. 조건식 선택 시 rolling test 평균 net이 0 이상인지 확인
5. 이 기준을 만족할 때만 `--sample-stage expand_200k` 실제 학습 실행

## 9. 현재 페이지별 진행률

| 페이지 | 내용 | 완료율 | 상태 |
| --- | --- | ---: | --- |
| Page 1 | STOM tick DB 구조 분석 | 100% | 완료 |
| Page 2 | 전체 주식 테이블 OHLCV 추출/1초봉 QlibDataset export | 100% | 완료 |
| Page 3 | bounded/pilot 학습 가능성 검증 | 70% | 기본 가능성 확인, 수익성 개선 필요 |
| Page 4 | pred30/pred60 전체 dataset 학습 루프 연결 | 100% | 완료 |
| Page 5 | budget_20k fine-tuning | 100% | pred30/pred60 checkpoint 생성 완료 |
| Page 6 | checkpoint 예측/대형 walk-forward/rolling 검증 | 95% | 이번 단계 완료 |
| Page 7 | 웹 대시보드 예측/백테스트/필터 리포트 확인 | 82% | 산출물 표시 가능, 비교 UX 추가 개선 여지 |
| Page 8 | staged full-training 실행 계획 | 88% | 게이트 기준 반영 완료 |
| Page 9 | expand_200k/1M/5M/full-window 실제 확대 학습 | 0% | 게이트 미충족으로 보류 |

전체 진행률은 **91%**로 본다. 단, 이 91%는 “전체 데이터 학습 파이프라인 구축과 검증 체계” 기준이며, “모든 window를 실제로 끝까지 학습한 비율”은 아니다.

## 10. 2026-05-09 cost sensitivity gate 자동화 후속 결과

후속 보고서: `docs/stom_1s_cost_gate_analysis_report.md`

이번 후속 단계에서는 기존 filter-search/rolling-validation artifact를 입력으로 받아 `5bp`, `10bp`, `15bp`, `25bp` 비용 민감도를 자동 계산하는 `--gate-analysis` 모드를 추가했다.

실제 대형 artifact 적용 결과:

| total cost | rolling avg test net | positive fold rate | gate |
| ---: | ---: | ---: | --- |
| 5bp | +0.0234% | 0.500 | PASS |
| 10bp | -0.0266% | 0.375 | FAIL |
| 15bp | -0.0766% | 0.375 | FAIL |
| 25bp | -0.1766% | 0.250 | FAIL |

최종 판단은 변하지 않는다.

```text
target cost 25bp 기준 gate: FAIL
expand_200k 실제 학습: 보류
```

5bp에서는 통과되지만, 실제 판단 비용인 25bp에서 실패하므로 학습량 확대보다 score/filter 리디자인 또는 pred30/pred60 ensemble 후보 검증이 먼저다.
