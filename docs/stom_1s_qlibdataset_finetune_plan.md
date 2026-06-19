# STOM 1초봉 Kronos QlibDataset 전체 파인튜닝 계획

작성일: 2026-05-08

## 현재 단계 결론

1초봉을 pyqlib provider로 직접 학습하는 경로가 아니라, **STOM 1초봉을 Kronos `QlibDataset` pickle 형식으로 변환한 뒤 `finetune/train_predictor.py`로 파인튜닝**하는 경로가 맞다.

이번 단계에서는 전체 데이터 학습 전에 필요한 데이터 품질 게이트를 추가했다.

- `--regularize-1s`: 1초 grid 보정
- `--split-by session`: 날짜/session 기준 train/val/test split
- `--horizon-seconds`: 30초/60초 후 target을 명시하는 horizon preset
- export report에 `split_sessions`, `grid_summary`, `effective_predict_window` 기록
- `dump_bin` command에 export freq 보존

## 전체 페이지 진행률

| 페이지 | 내용 | 상태 | 완료율 |
| ---: | --- | --- | ---: |
| 1 | STOM DB 구조 분석 | 완료 | 100% |
| 2 | STOM tick 기본 OHLCV 변환 | 완료 | 100% |
| 3 | 기존 all-table bounded 학습 | 완료/품질 낮음 | 60% |
| 4 | 1초봉 QlibDataset 전체 학습 데이터 구축 | 진행 중 | 65% |
| 5 | 30초/60초 모델 파인튜닝 | 남음 | 0% |
| 6 | baseline/walk-forward/Top-K 검증 | 남음 | 0% |
| 7 | 대시보드/추천/?? ?? ?? 적용 | 부분 완료 | 45% |

현재 전체 진행률: 약 **60~65%**.

## 왜 이 단계가 필요한가

기존 모델의 `direction_accuracy=0.40`은 실전 매매 신호로 사용하기 어렵다. 특히 기존 경로에는 다음 문제가 있었다.

1. `predict_window=30/60`이 실제 30초/60초가 아니라 30/60 row일 수 있음.
2. train/val/test가 group 단위라 같은 거래일이 여러 split에 나뉠 수 있음.
3. 전체 universe 대상이라도 모든 가능한 window를 끝까지 학습한 것이 아니라 bounded 학습임.

따라서 재학습 전에 먼저 **정확한 시간 grid와 날짜 기준 split**을 고정해야 한다.

## 파일럿 검증 결과

### 30초 horizon 파일럿

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred30_stage_pilot `
  --max-tables 2 `
  --lookback-window 30 `
  --horizon-seconds 30 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 090200 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --max-groups 6 `
  --train-ratio 0.5 `
  --val-ratio 0.25 `
  --test-ratio 0.25
```

결과:

- exported groups: 4
- exported rows: 435
- grid inserted rows: 239
- train/val/test session 중복 없음
- `QlibDataset` load smoke 성공

### 60초 horizon 파일럿

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred60_stage_pilot `
  --max-tables 2 `
  --lookback-window 60 `
  --horizon-seconds 60 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 090300 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --max-groups 6 `
  --train-ratio 0.5 `
  --val-ratio 0.25 `
  --test-ratio 0.25
```

결과:

- exported groups: 4
- exported rows: 675
- grid inserted rows: 382
- train/val/test session 중복 없음

## 전체 데이터 export 명령

### 30초 후 예측용 전체 데이터

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred30_full `
  --max-tables 0 `
  --lookback-window 300 `
  --horizon-seconds 30 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --test-ratio 0.15
```

### 60초 후 예측용 전체 데이터

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred60_full `
  --max-tables 0 `
  --lookback-window 300 `
  --horizon-seconds 60 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --test-ratio 0.15
```

## 파인튜닝 연결

30초 모델:

```powershell
$env:KRONOS_DATASET_PATH="D:\Chanil_Park\Project\Programming\Kronos\finetune\qlib_exports\stom_1s_grid_pred30_full\processed_datasets"
$env:KRONOS_LOOKBACK_WINDOW="300"
$env:KRONOS_PREDICT_WINDOW="30"
$env:KRONOS_USE_COMET="0"
$env:KRONOS_SAVE_PATH="finetune\outputs\stom_1s_grid_pred30"
python finetune\train_predictor.py
```

60초 모델:

```powershell
$env:KRONOS_DATASET_PATH="D:\Chanil_Park\Project\Programming\Kronos\finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets"
$env:KRONOS_LOOKBACK_WINDOW="300"
$env:KRONOS_PREDICT_WINDOW="60"
$env:KRONOS_USE_COMET="0"
$env:KRONOS_SAVE_PATH="finetune\outputs\stom_1s_grid_pred60"
python finetune\train_predictor.py
```

## 남은 검증

1. 전체 데이터 export를 장시간 실행하고 manifest를 보관한다.
2. 30초/60초 모델을 각각 학습한다.
3. persistence baseline과 같은 holdout 날짜에서 비교한다.
4. `direction_accuracy=0.40` 기존 모델보다 개선되는지 확인한다.
5. 개선되지 않으면 실전 추천에는 계속 사용하지 않는다.

## 2026-05-08 전체 export 완료 결과

`--regularize-1s`, `--split-by session`, `--horizon-seconds`를 적용한 STOM 1초봉 전체 export를 30초/60초 horizon 모두 완료했다. 상세 근거는 `docs/stom_1s_full_export_report.md`에 고정했다.

| 항목 | 30초 horizon | 60초 horizon |
| --- | ---: | ---: |
| 성공 stock table | 2,425 | 2,425 |
| 제외 non-stock table | 2 | 2 |
| export group | 73,900 | 73,900 |
| export row | 131,470,857 | 131,470,857 |
| train sessions | 665 | 665 |
| val sessions | 143 | 143 |
| test sessions | 143 | 143 |
| session overlap | 0 | 0 |

현재 페이지 판단:

```text
Page 1 DB 구조 분석                    [██████████] 100%
Page 2 STOM tick OHLCV 변환            [██████████] 100%
Page 3 bounded/pilot 학습 검증          [██████░░░░] 60%
Page 4 1초봉 전체 QlibDataset 구축      [██████████] 100%
Page 5 30초/60초 Kronos 파인튜닝        [██████░░░░] 60%
Page 6 baseline/walk-forward 검증       [████░░░░░░] 40%
Page 7 웹 대시보드/?? ?? Export 연동          [██████░░░░] 60%
```

전체 진행률은 약 **82%**로 본다. 다음 commit 단위는 평가 표본을 더 넓히고, 60초 모델의 direction accuracy 개선 신호가 반복되는지 walk-forward로 확인하는 것이다.

## 2026-05-08 budgeted 파인튜닝 실행 결과

Windows + RTX 4080 SUPER 환경에서 전체 STOM 1초봉 pred30/pred60 `processed_datasets`를 실제 Kronos predictor 학습 루프에 넣는 데 성공했다. 상세 근거는 `docs/stom_1s_finetune_execution_report.md`에 고정했다.

| 항목 | 30초 | 60초 |
| --- | ---: | ---: |
| train possible samples | 75,277,195 | 73,718,875 |
| val possible samples | 16,275,307 | 15,938,107 |
| budgeted train samples | 20,000 | 20,000 |
| budgeted val samples | 4,000 | 4,000 |
| batch size | 4 | 4 |
| train steps | 5,000 | 5,000 |
| best val loss | 2.1549 | 2.1302 |
| duration | 550.89s | 549.04s |

주의: 위 `best val loss`는 매매 방향 정확도가 아니라 Kronos predictor token loss다. 따라서 기존 `direction_accuracy=0.40`과 직접 비교하지 않는다. 다음 단계에서 checkpoint 기반 prediction CSV를 만들고 실제 등락 방향과 비교해야 한다.

## 2026-05-08 checkpoint 예측/평가 결과

budgeted checkpoint로 test split holdout 예측 CSV를 생성하고 baseline과 비교했다. 상세 근거는 `docs/stom_1s_checkpoint_eval_report.md`에 고정했다.

| horizon | Kronos direction accuracy | persistence | random | 판단 |
| --- | ---: | ---: | ---: | --- |
| 30초 | 0.3704 | 0.2222 | 0.1111 | 0.40 미달 |
| 60초 | 0.4444 | 0.1111 | 0.2963 | 제한 샘플에서 0.40 초과 |

단, Top-K net return은 30초/60초 모두 음수다. 따라서 현재 모델은 실전 매수 추천으로 바로 사용하지 않고, 평가 표본 확대와 조건식 보완 후 다시 판단한다.

## 2026-05-08 pred60 walk-forward 조건식 필터 검증 결과

상세 보고서는 `docs/stom_1s_walkforward_filter_report.md`에 고정했다. 이번 단계에서는 pred60 budget checkpoint를 더 넓은 holdout 표본으로 평가하고, 예측 시점 feature만 사용하는 조건식 필터를 탐색했다.

핵심 결과:

- 평가 범위: 30개 session × session당 3개 as-of, 546 windows, 146 symbols, 90 rebalance periods
- Kronos direction accuracy: 0.4084
- Persistence direction accuracy: 0.1832
- Random(seed 고정) direction accuracy: 0.4084
- 조건식 없는 Qlib-style Top-K net: -0.2377%
- robust filter net: -0.1008%, coverage 62.22%, direction hit 0.4634
- opportunistic filter net: -0.0089%, coverage 36.67%, direction hit 0.4762

현재 판단:

```text
Page 1 DB 구조 분석                    [█████] 100%
Page 2 STOM tick OHLCV 변환            [█████] 100%
Page 3 bounded/pilot 학습 검증          [███░░] 60%
Page 4 1초봉 전체 QlibDataset 구축      [█████] 100%
Page 5 30초/60초 Kronos 파인튜닝        [████░] 80%
Page 6 baseline/walk-forward 검증       [████░] 80%
Page 7 웹 대시보드/?? ?? Export 연동          [████░] 70%
전체 진행률                             [████░] 85%
```

중요 결론은 `조건식이 손실을 크게 줄였지만 아직 비용 후 양수 전환은 아니다`이다. 따라서 현재 모델은 연구/검증/대시보드 확인용으로 유지하고, 실제 자동 매수 추천에는 바로 연결하지 않는다.

다음 단계는 더 큰 walk-forward 표본과 rolling train/test 방식의 조건식 검증이다.

## 2026-05-08 rolling 조건식 검증 결과

상세 보고서는 `docs/stom_1s_rolling_filter_validation_report.md`에 고정했다. 이번 단계에서는 같은 표본에서 고른 조건식을 같은 표본에서 평가하는 한계를 줄이기 위해, 앞쪽 30 periods에서 best filter를 고르고 뒤쪽 30 periods에 그대로 적용하는 rolling validation을 추가했다.

핵심 결과:

- rolling fold: 2
- train/test period: 30 / 30
- total test trades: 26
- avg train net: +0.0519%
- avg test net: -0.0351%
- avg test baseline net: -0.2438%
- baseline 대비 test 개선폭: +0.2087%p
- weighted test direction hit: 0.4615
- positive test fold rate: 0.5

현재 판단:

```text
Page 1 DB 구조 분석                    [█████] 100%
Page 2 STOM tick OHLCV 변환            [█████] 100%
Page 3 bounded/pilot 학습 검증          [███░░] 60%
Page 4 1초봉 전체 QlibDataset 구축      [█████] 100%
Page 5 30초/60초 Kronos 파인튜닝        [████░] 80%
Page 6 walk-forward/rolling 검증        [████░] 88%
Page 7 웹 대시보드/?? ?? Export 연동          [████░] 78%
전체 진행률                             [████░] 88%
```

rolling 결과는 조건식이 baseline 대비 손실을 줄인다는 근거를 보강했지만, 비용 후 평균 test net이 아직 음수라서 실전 자동 매수 승인에는 부족하다. 다음 단계는 `max_sessions 100`, `max_asofs 5`, `max_symbols 50` 이상 대형 walk-forward를 장시간 실행하고 같은 rolling 검증을 반복하는 것이다.

## 2026-05-09 staged full-training 계획 반영

전체 데이터 학습은 `docs/stom_1s_staged_full_training_plan.md`에 실행 가능한 staged roadmap으로 반영했다. 핵심은 현재 완료된 `20k budgeted` 학습을 전량 학습으로 과장하지 않고, 아래 순서로 확장하는 것이다.

```text
budget_20k 완료
expand_200k 준비
expand_1m 준비
expand_5m 준비
full_window 후보
```

`finetune/run_stom_1s_finetune.py`에는 `--sample-stage` 옵션을 추가했다.

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_200k `
  --output-root finetune\outputs
```

현재 판단:

```text
Page 1 DB 구조 분석                       [█████] 100%
Page 2 STOM tick OHLCV 변환               [█████] 100%
Page 3 bounded/pilot 학습 검증             [███░░] 60%
Page 4 1초봉 전체 QlibDataset 구축         [█████] 100%
Page 5 30초/60초 20k 파인튜닝              [█████] 100%
Page 6 walk-forward/rolling 검증           [████░] 88%
Page 7 웹 대시보드/내부 검증 Export        [████░] 78%
Page 8 staged full-training 확대 계획      [████░] 80%
전체 진행률                                [████░] 89%
```

다음 실행 단계는 `expand_200k` 학습이 아니라, 먼저 pred60 대형 walk-forward 평가를 실행해 학습량 확대가 가치 있는지 확인하는 것이다.

## 2026-05-09 pred60 대형 walk-forward 게이트 결과

상세 보고서: `docs/stom_1s_large_walkforward_gate_report.md`

이번 단계에서는 `expand_200k` 실제 학습으로 넘어가기 전에, 기존 pred60 `budget_20k` checkpoint를 더 큰 holdout walk-forward 표본으로 검증했다.

핵심 수치:

| 항목 | 값 |
| --- | ---: |
| selected windows | 3,080 |
| rebalance periods | 500 |
| rows per mode | 184,800 |
| Kronos direction accuracy | 0.4312 |
| random direction accuracy | 0.4084 |
| persistence direction accuracy | 0.1487 |
| Qlib Top-K avg net return | -0.1953% |
| best robust filter avg net return | -0.1266% |
| rolling avg test net return | -0.1766% |
| rolling positive test fold rate | 0.25 |

판단:

```text
expand_200k 실제 학습은 이번 단계에서 실행하지 않는다.
방향성 신호는 random보다 높지만, 비용 후 수익성과 rolling 안정성이 아직 기준 미달이다.
```

따라서 다음 단계는 학습량 확대가 아니라 score/filter 구조 개선, 비용 민감도 분석, pred30/pred60 ensemble 후보 검증이다. rolling 평균 test net이 0 이상으로 올라오고 여러 fold에서 반복 개선이 확인될 때만 `--sample-stage expand_200k` 학습으로 넘어간다.

현재 판단:

```text
Page 1 DB 구조 분석                       [█████] 100%
Page 2 STOM tick OHLCV/QlibDataset 구축    [█████] 100%
Page 3 bounded/pilot 학습 검증             [████░] 70%
Page 4 1초봉 전체 학습 루프 연결           [█████] 100%
Page 5 30초/60초 20k 파인튜닝              [█████] 100%
Page 6 대형 walk-forward/rolling 검증      [█████] 95%
Page 7 웹 대시보드/검증 산출물 확인        [████░] 82%
Page 8 staged full-training 계획           [████░] 88%
Page 9 expand/full-window 실제 확대 학습   [░░░░░] 0%
전체 진행률                                [█████░] 91%
```

주의: 여기서 전체 진행률은 “파이프라인 구축과 검증 체계” 기준이다. STOM tick의 모든 possible window를 실제로 끝까지 학습한 것은 아니며, 확대 학습은 게이트 미충족으로 보류한다.

## 2026-05-09 cost sensitivity gate 자동화

상세 보고서: `docs/stom_1s_cost_gate_analysis_report.md`

대형 walk-forward 후속으로 `--gate-analysis` 모드를 추가해 비용 민감도와 expand 학습 승인 여부를 자동 계산하게 했다.

결과:

| total cost | rolling avg test net | positive fold rate | gate |
| ---: | ---: | ---: | --- |
| 5bp | +0.0234% | 0.500 | PASS |
| 10bp | -0.0266% | 0.375 | FAIL |
| 15bp | -0.0766% | 0.375 | FAIL |
| 25bp | -0.1766% | 0.250 | FAIL |

현재 실제 판단 기준인 25bp에서는 gate가 실패하므로 `expand_200k`는 계속 보류한다. 다음 단계는 score/filter 리디자인 또는 pred30/pred60 ensemble 후보를 만든 뒤 같은 gate를 재실행하는 것이다.

```text
Page 1 DB 구조 분석                       [█████] 100%
Page 2 STOM tick OHLCV/QlibDataset 구축    [█████] 100%
Page 3 bounded/pilot 학습 검증             [████░] 75%
Page 4 1초봉 전체 학습 루프 연결           [█████] 100%
Page 5 30초/60초 20k 파인튜닝              [█████] 100%
Page 6 대형 walk-forward/rolling/gate 검증 [█████] 96%
Page 7 웹 대시보드/검증 산출물 확인        [████░] 88%
Page 8 staged full-training 계획           [█████] 90%
Page 9 expand/full-window 실제 확대 학습   [░░░░░] 0%
전체 진행률                                [█████░] 93%
```
