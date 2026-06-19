# STOM 1초봉 staged full-training 실행 계획

작성일: 2026-05-09

## 1. 목적

STOM tick 전체 데이터는 이미 1초봉 `QlibDataset` pickle로 변환되어 Kronos 학습 루프에 연결되어 있다.
하지만 현재 실제 fine-tuning은 `20,000` train sample budget으로 수행되었고, 가능한 모든 train window를 전량 학습한 것은 아니다.

이 문서는 전체 데이터 학습을 다음처럼 단계형으로 확대하기 위한 실행 계획이다.

```text
20k baseline 완료
→ 200k 확대
→ 1M 확대
→ 5M 장시간 학습
→ full-window 전량 epoch 후보
```

## 2. 현재 완료 상태

| 항목 | pred30 | pred60 |
| --- | ---: | ---: |
| 전체 주식 table | 2,425 | 2,425 |
| export group | 73,900 | 73,900 |
| export row | 131,470,857 | 131,470,857 |
| possible train samples | 75,277,195 | 73,718,875 |
| possible val samples | 16,275,307 | 15,938,107 |
| 현재 실제 train samples | 20,000 | 20,000 |
| 현재 실제 val samples | 4,000 | 4,000 |

따라서 현재 상태는 다음과 같이 정의한다.

```text
전체 데이터셋 구축: 완료
전체 데이터셋 학습 루프 연결: 완료
전체 window 전량 학습: 미완료
```

## 3. staged training budget

| stage | train samples | val samples | 목적 |
| --- | ---: | ---: | --- |
| `budget_20k` | 20,000 | 4,000 | 현재 baseline 재현 |
| `expand_200k` | 200,000 | 40,000 | 학습량 10배 확대 후 방향성/Top-K 변화 확인 |
| `expand_1m` | 1,000,000 | 100,000 | 의미 있는 장시간 학습 후보 |
| `expand_5m` | 5,000,000 | 250,000 | overnight급 장시간 학습 후보 |
| `full_window` | horizon별 possible train 전체 | horizon별 possible val 전체 | 최종 전량 epoch 후보 |

`full_window`는 pred30 기준 75,277,195 train samples, pred60 기준 73,718,875 train samples다.

## 4. 실행 CLI

이번 단계에서 `finetune/run_stom_1s_finetune.py`에 `--sample-stage` 옵션을 추가했다.

### 4.1 pred60 200k 확대 학습 dry-run

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_200k `
  --output-root finetune\outputs `
  --dry-run
```

### 4.2 pred60 200k 실제 학습

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_200k `
  --output-root finetune\outputs
```

### 4.3 pred60 1M 실제 학습

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_1m `
  --output-root finetune\outputs
```

### 4.4 pred60 full-window 전량 후보 dry-run

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage full_window `
  --output-root finetune\outputs `
  --dry-run
```

## 5. 실행 순서

현재 모델의 비용 후 net return이 아직 양수가 아니므로, 바로 full-window 전량 학습으로 가지 않는다.

권장 순서:

1. 기존 pred60 checkpoint로 `max_sessions 100`, `max_asofs 5`, `max_symbols 50` 대형 walk-forward를 먼저 실행한다.
2. rolling filter validation을 다시 실행한다.
3. rolling avg_test_net이 0 이상이거나 baseline 대비 개선폭이 강하면 `expand_200k` 학습을 실행한다.
4. `expand_200k` checkpoint를 같은 방식으로 평가한다.
5. 개선되면 `expand_1m`, 이후 `expand_5m`로 확대한다.
6. `expand_5m`에서도 개선이 반복될 때만 `full_window` 전량 학습을 검토한다.

## 6. 성공/중단 기준

확대 학습 성공 기준:

- rolling avg_test_net_return_pct > 0
- baseline 대비 개선폭이 여러 fold에서 반복
- random baseline 대비 방향성/Top-K 모두 우위
- 거래 수가 너무 적지 않음

중단 기준:

- 학습량을 늘렸는데 direction accuracy와 Top-K net이 개선되지 않음
- 조건식이 특정 기간에서만 작동하고 rolling test에서 무너짐
- 비용 후 net이 계속 음수

## 7. 현재 진행률 반영

```text
전체 데이터셋 구축                      [█████] 100%
학습 루프 연결                          [█████] 100%
20k budgeted 학습                       [█████] 100%
200k 확대 학습 준비                     [████░] 80%
1M/5M/full-window 실행                  [░░░░░] 0%
대형 walk-forward 후 확대 여부 판단      [███░░] 60%
```

전체 프로젝트 진행률은 이번 단계 이후 **89%**로 본다.

## 8. 2026-05-09 pred60 대형 walk-forward 게이트 결과

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

## 9. 2026-05-09 cost sensitivity gate 자동화

상세 보고서: `docs/stom_1s_cost_gate_analysis_report.md`

`expand_200k`를 실행하기 전 확인해야 하는 gate를 코드로 고정했다.

```powershell
python finetune\search_stom_1s_filters.py `
  --gate-analysis `
  --filter-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos.filter_search.json `
  --rolling-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos_rolling100x50.rolling_filter_validation.json `
  --total-cost-bps-grid 5,10,15,25 `
  --target-total-cost-bps 25
```

현재 target 25bp 기준 결과:

```text
rolling avg test net     -0.1766%
positive fold rate        0.25
total test trades         150
gate result               FAIL
decision                  hold_expand_200k
```

따라서 staged training 순서는 다음처럼 갱신한다.

```text
1. score/filter 리디자인
2. cost gate 재검증
3. target 25bp gate 통과 시 expand_200k 실행
4. expand_200k checkpoint 재평가
5. 이후 1M/5M/full-window 확대 검토
```
