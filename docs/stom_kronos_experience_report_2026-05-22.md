# STOM 1초봉 Kronos 파인튜닝 · 평가 · 대시보드 경험치 보고서

작성일: 2026-05-22 KST  
대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`

## 1. 한 줄 결론

STOM 2025년 1초봉 전체 데이터를 Kronos fine-tuning 파이프라인에 연결하고, tokenizer/predictor 학습과 웹 대시보드 시각화까지 구축했다. 파이프라인은 정상 동작하지만, 현재 fine-tuned model은 실전 매매 신호로 바로 쓰기에는 부족하다. 지금까지의 실험에서는 **300초 horizon이 가장 유망**하지만 아직 rolling cost gate를 통과하지 못했다.

## 2. 이번 작업의 목표

처음 목표는 단순 예측 데모가 아니라 다음까지 확인하는 것이었다.

1. STOM tick DB를 Kronos fine-tuning 데이터로 사용할 수 있는지 확인
2. 2025년 STOM 1초봉 데이터를 Qlib/Kronos 형태로 변환
3. tokenizer와 predictor를 실제로 학습
4. 학습 상태를 웹 대시보드에서 실시간 확인
5. 학습된 checkpoint로 실제값과 예측값을 비교
6. 방향 적중률, 비용 반영 수익률, 조건식/필터 성능을 검증
7. 다음 학습 방향을 잃지 않도록 문서와 커밋으로 관리

## 3. 최종 상태 요약

| 영역 | 상태 | 핵심 결과 |
| --- | --- | --- |
| STOM DB 분석 | 완료 | 2025년 1초봉 정규화 학습셋 생성 가능 확인 |
| Qlib/Kronos 변환 | 완료 | `finetune/qlib_exports/stom_1s_grid_pred60_2025` 생성 |
| tokenizer 학습 | 완료 | checkpoint 생성 완료 |
| predictor 학습 | 완료 | best validation loss `2.3711` |
| 학습 모니터 대시보드 | 완료 | 진행률, 손실, GPU/CPU, 로그, ETA 표시 |
| 예측 진단 대시보드 | 완료 | 실제값/예측값, 산점도, Top-K, horizon 비교 표시 |
| 60초 평가 | 완료 | 방향 적중률 44.79%, random 44.93% |
| 조건식/비용 검증 | 완료 | 손실은 감소했지만 rolling gate 실패 |
| 30/60/120/300초 비교 | 완료 | 300초가 가장 유망, rolling net -0.005% |
| 실전 사용 판단 | 보류 | 비용/rolling 안정성 미통과 |

## 4. 사용 데이터와 학습 범위

### 4.1 원본 데이터

| 항목 | 값 |
| --- | --- |
| DB | `_database\stock_tick_back.db` |
| 데이터 형태 | STOM tick DB의 종목별 테이블 |
| 사용 구간 | 2025-01-03 ~ 2025-12-30 |
| 장중 시간 | 09:00:00 ~ 09:30:00 |
| 정규화 주기 | 1초봉 |
| 기본 feature | open, high, low, close, volume, amount |
| 가격 모드 | `close_only`; close가 없으면 현재가를 close로 사용 |

### 4.2 Qlib export 설정

근거 파일:

- `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json`

| 항목 | 값 |
| --- | ---: |
| exported group count | 18,750 |
| exported row count | 33,360,325 |
| train groups | 13,256 |
| validation groups | 2,764 |
| test groups | 2,730 |
| train rows | 23,579,043 |
| validation rows | 4,920,437 |
| test rows | 4,860,845 |
| train sessions | 168 |
| validation sessions | 36 |
| test sessions | 36 |
| lookback window | 300초 |
| 기본 predict window | 60초 |

## 5. 학습 결과

### 5.1 predictor summary

근거 파일:

- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/finetune_predictor/summary.json`

| 항목 | 값 |
| --- | --- |
| run | `stom_1s_grid_pred60_2025_full_small` |
| predictor 시작 | `2026-05-20T22-28-57` |
| world size | 1 |
| best validation loss | `2.3711213504856223` |
| best checkpoint | `finetune/outputs/stom_1s_grid_pred60_2025_full_small/finetune_predictor/checkpoints/best_model` |
| predictor model size | 약 98.98 MB |
| tokenizer checkpoint | `finetune/outputs/stom_1s_grid_pred60_2025_full_small/finetune_tokenizer/checkpoints/latest_train_model` |
| tokenizer model size | 약 15.84 MB |

### 5.2 학습 중 얻은 운영 노하우

1. 학습은 장시간 실행되므로 절전/재부팅/터미널 종료와 무관하게 프로세스 상태를 별도로 확인해야 한다.
2. 99%대에서 멈춘 것처럼 보여도 checkpoint 저장/validation 단계일 수 있다.
3. GPU 사용률 100%가 항상 목표는 아니다. small model, batch, dataloader, validation, checkpoint I/O 단계에서는 GPU가 낮게 보일 수 있다.
4. 학습 상태는 cmd 로그만으로는 불안하므로 웹 대시보드에 진행률, loss, rolling 평균, GPU/CPU, 로그 tail을 분리해서 보여주는 것이 효과적이었다.
5. 학습 완료 여부는 진행률보다 checkpoint와 summary 파일, best model 존재 여부로 확인하는 것이 안전하다.

## 6. 60초 기본 평가 결과

근거 파일:

- `webui/stom_predictions/stom_1s_pred60_2025_full_small_walkforward36x3x50_eval_comparison.json`
- `webui/qlib_backtests/stom_1s_pred60_2025_full_small_walkforward36x3x50_eval_kronos.qlib_topk5.json`

평가 조건:

| 항목 | 값 |
| --- | --- |
| split | test |
| 기간 | 2025-11-07 ~ 2025-12-30 |
| session | 36 |
| as-of | session당 최대 3개 |
| symbols | as-of당 최대 50개 |
| windows | 681 |
| rows | 40,860 |
| 비용 | 수수료 15bp + 슬리피지 10bp = 25bp |

| 지표 | Kronos | Persistence | Random |
| --- | ---: | ---: | ---: |
| direction accuracy | 44.79% | 12.04% | 44.93% |
| MAPE | 0.8730 | 0.3852 | 0.3906 |
| Top-K hit rate | 46.67% | 12.41% | 43.52% |
| Top-K 평균 실제 등락률 | 0.0459% | 0.0711% | 0.0758% |

비용 반영 Top-K:

| 항목 | 값 |
| --- | ---: |
| period count | 108 |
| trade count | 540 |
| avg gross return | 0.0459% |
| avg net return | -0.2041% |
| cumulative return | -19.8646% |
| max drawdown | -20.4773% |

### 6.1 60초 평가 해석

- Kronos 60초 방향 적중률은 44.79%로 50% 미만이다.
- random baseline 44.93%와 거의 같아 방향성 우위가 없다.
- MAPE는 persistence/random보다 높아 가격 경로 예측도 불리하다.
- 비용 25bp를 반영하면 Top-K 수익률은 명확히 음수다.
- 따라서 60초 모델은 “실전 신호”가 아니라 “연구/시각화/조건식 보완 대상”으로 봐야 한다.

## 7. 조건식 / 비용 필터 실험

근거 파일:

- `webui/qlib_backtests/stom_1s_pred60_2025_full_small_walkforward36x3x50_eval_kronos_cost25.filter_search.json`
- `webui/qlib_backtests/stom_1s_pred60_2025_full_small_walkforward36x3x50_eval_kronos_cost25.rolling_filter_validation.json`
- `webui/qlib_backtests/stom_1s_pred60_2025_full_small_walkforward36x3x50_eval_kronos_cost25.cost_gate.json`

### 7.1 60초 최적 필터

| 항목 | 기본 Top-K | 최적 필터 |
| --- | ---: | ---: |
| 필터 | 없음 | `ret>=0.05`, `cons>=0.5`, `amount q>=0.75` |
| period | 108 | 56 |
| trade 수 | 540 | 87 |
| coverage | 100.00% | 51.85% |
| 평균 gross return | 0.0459% | 0.1590% |
| 평균 net return, 25bp | -0.2041% | -0.0168% |
| direction hit rate | 46.67% | 47.13% |
| 누적수익 | -19.8646% | -1.1639% |

### 7.2 rolling validation 결과

| 항목 | 값 |
| --- | ---: |
| fold 수 | 7 |
| total test trades | 66 |
| avg train net return | 0.0831% |
| avg test net return | -0.2043% |
| avg test baseline net return | -0.1726% |
| test improvement | -0.0317% |
| weighted test direction hit | 39.39% |
| positive test fold rate | 28.57% |
| overfit gap | 0.2874% |

결론:

- in-sample 최적 필터는 손실을 크게 줄였다.
- 그러나 rolling test에서 다시 무너졌다.
- 즉, “과거 구간에 맞춘 조건식”이 미래 구간에서도 반복될 정도로 안정적이지 않았다.
- `decision = hold_expand_200k`가 타당하다.

## 8. Horizon 30/60/120/300초 비교

근거 파일:

- `webui/qlib_backtests/stom_1s_2025_full_small_horizon_comparison.json`
- 대시보드 API: `GET /api/stom/horizon-comparison`

공통 조건:

| 항목 | 값 |
| --- | --- |
| 동일 checkpoint | `stom_1s_grid_pred60_2025_full_small` |
| lookback | 300초 |
| test 기간 | 2025-11-07 ~ 2025-12-30 |
| as-of | session당 최대 3개 |
| symbols | as-of당 최대 50개 |
| 비용 | 25bp |

| horizon | Kronos 방향 적중률 | random 방향 적중률 | random 대비 | Top-K net | 최적 필터 net | rolling net | rolling 방향 | gate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30초 | 39.21% | 38.77% | +0.44%p | -0.2522% | -0.0465% | -0.2398% | 32.08% | 실패 |
| 60초 | 44.79% | 44.93% | -0.15%p | -0.2041% | -0.0168% | -0.2043% | 39.39% | 실패 |
| 120초 | 45.67% | 42.73% | +2.94%p | -0.1735% | -0.0335% | -0.2903% | 49.35% | 실패 |
| 300초 | 49.19% | 46.26% | +2.94%p | -0.1145% | +0.0922% | -0.0052% | 44.29% | 실패 |

### 8.1 horizon 비교 해석

1. 30초는 너무 짧아 노이즈가 크다.
2. 60초는 기존 기본 horizon이지만 random 대비 edge가 없다.
3. 120초는 방향성 edge가 생기지만 rolling net이 나쁘다.
4. 300초가 가장 유망하다.
5. 300초도 아직 gate는 실패했지만, rolling net이 -0.0052%로 손익분기점에 가장 가깝다.

## 9. 웹 대시보드에 반영된 것

위치:

- `http://127.0.0.1:5070/training`
- 좌측 메뉴: `예측 진단`

### 9.1 학습 모니터

학습 중/완료 상태를 확인하기 위해 다음을 구현했다.

1. 전체 진행률과 단계별 진행률
2. tokenizer/predictor 단계 구분
3. loss, rolling average, 표준편차
4. learning rate, step, samples/sec
5. GPU 사용률, VRAM, GPU 온도
6. CPU 사용률과 CPU 온도 표시 영역
7. 로그 tail
8. 한국 시간 기준 표시
9. 완료 예상 시각과 경과 시간

### 9.2 예측 진단

예측 결과를 사용자가 이해하기 쉽게 보기 위해 다음을 구현했다.

1. model verdict 카드
2. direction accuracy, MAPE, windows/symbols/sessions KPI
3. 실제 종가 vs Kronos 예측 종가 차트
4. 예측 등락률 vs 실제 등락률 산점도
5. Kronos 점수 상위 후보 테이블
6. 조건식/Top-K 필터별 성과
7. horizon 30/60/120/300초 비교표와 차트
8. 백테스트/필터 리포트 산출물 조회

## 10. 주요 커밋 흐름

| 커밋 | 의미 |
| --- | --- |
| `dafc7c5` | horizon 30/60/120/300초 비교와 대시보드 반영 |
| `88eefb1` | 조건식/비용/rolling gate 결과 문서화 |
| `d43e7ca` | 완료 모델 평가 결과를 예측 진단 대시보드에 연결 |
| `5e7763a` | predictor 완료 상태를 성과 확인 가능 상태로 표시 |
| `2d36fd7` | CPU 상태를 GPU 트렌드와 함께 표시 |
| `84e418a` | 학습 상태 정상 범위와 CPU 기준 연결 |
| `0549ac5` | 학습 진행률 중복 제거와 단계 바 정리 |
| `38c3c21` | 학습 대시보드 차트의 실시간 데이터 누락 개선 |
| `1ed31b5` | tokenizer 검증 정체 후 predictor 학습으로 복구 |
| `cc5a7e1` | 중복 원형 그래프 정리 |
| `748246c` | 전체 진행률을 단계별 구간으로 표시 |
| `290ad12` | 학습 대시보드 한글 깨짐 복구 |

## 11. 파인튜닝이 잘 안 된 것처럼 보인 이유

현재 결과는 “파이프라인 실패”가 아니라 “실전 신호력이 부족”한 상태다.

### 11.1 학습 목표와 매매 목표 불일치

Kronos는 미래 가격 경로 예측을 학습한다. 그러나 실제 목표는 다음이다.

1. 상승할 종목 선별
2. 방향 적중
3. 거래비용 초과 수익
4. rolling validation에서 반복되는 안정성

가격 경로 예측 loss가 낮아지는 것과 실전 매매 수익이 양수가 되는 것은 같은 목표가 아니다.

### 11.2 1초봉 초단기 데이터의 노이즈

30초/60초 예측은 다음의 영향을 크게 받는다.

- 순간 체결
- 호가 공백
- 단기 수급
- 유동성 차이
- 거래대금 급변
- 장초반 이벤트성 움직임

OHLCV만으로 이 모든 신호를 안정적으로 잡기는 어렵다.

### 11.3 비용 25bp의 압박

Top-K gross return이 0.05~0.14% 수준이면, 비용 0.25%를 이기기 어렵다. 따라서 예측 방향을 조금 맞혀도 순수익은 음수가 된다.

### 11.4 60초용 모델로 300초를 평가한 한계

300초가 가장 유망했지만, 현재 checkpoint는 기본적으로 60초 dataset/run에서 나온 모델이다. 300초 전용 objective로 학습한 결과는 아직 아니다.

### 11.5 조건식 과최적화

필터 탐색은 in-sample에서 좋아졌지만 rolling validation에서 통과하지 못했다. 이는 “과거에 맞춘 필터”가 미래에도 안정적으로 반복되지 않았다는 의미다.

## 12. 추가 변수를 넣는 방법에 대한 정리

추가 변수를 사용한다고 해서 반드시 모델 구조를 바로 바꿔야 하는 것은 아니다.

| 방법 | 모델 변경 | 추천도 | 설명 |
| --- | --- | --- | --- |
| 예측 후 필터/점수화에 사용 | 불필요 | 높음 | 가장 안전. Kronos 예측 + 거래대금/변동성/체결강도 조건 |
| OHLCV/amount 전처리에 반영 | 거의 불필요 | 높음 | 정규화, 파생값, 스케일링으로 간접 반영 |
| 별도 classifier/regressor 추가 | 일부 필요 | 중간 | Kronos embedding/score와 추가 feature를 결합 |
| Kronos 입력 차원 확장 | 필요 | 낮음, 장기 | tokenizer/model config/inference까지 수정 필요 |

현재 추천은 다음 순서다.

1. 추가 변수는 먼저 **예측 후 조건식/점수화**에 사용한다.
2. 300초 전용 predictor를 따로 학습한다.
3. 성과가 보이면 방향 분류/수익률 회귀 head를 추가한다.
4. 마지막으로 필요할 때만 Kronos 입력 차원 확장을 검토한다.

## 13. 현재 가장 중요한 결론

1. STOM 1초봉 → Kronos fine-tuning → 예측 → 대시보드까지 end-to-end 파이프라인은 구축됐다.
2. 현재 모델은 학습이 완료됐고 정상적으로 예측한다.
3. 그러나 30/60/120초는 비용과 random baseline을 충분히 이기지 못했다.
4. 300초가 가장 유망하다.
5. 300초도 아직 rolling cost gate는 통과하지 못했다.
6. 다음 실험은 “전체 확장 학습”보다 **300초 전용 학습 + 목적함수 개선 + 고확신 필터**가 먼저다.

## 14. 다음 권장 작업

### 14.1 바로 할 작업

```text
300초 horizon 전용 predictor를 학습하고, 기존 pred60 checkpoint 기반 300초 평가와 비교한다.
```

### 14.2 동시에 개선할 것

1. 방향 분류 지표를 학습/검증에 포함
2. 예상 등락률 회귀 지표 추가
3. 비용 초과 수익 여부를 별도 평가 지표로 추가
4. 거래대금, 변동성, 장초반 위치, 체결강도 유사 변수 기반 필터 강화
5. rolling validation을 gate로 유지

### 14.3 성공 기준

| 기준 | 목표 |
| --- | --- |
| direction accuracy | 50% 이상 |
| random 대비 edge | +3%p 이상 |
| rolling net return | 0% 이상 |
| positive fold rate | 50% 이상 |
| cost gate | 통과 |
| dashboard | horizon/조건식/실제-예측 비교 표시 |

## 15. 재현용 주요 명령

### 15.1 horizon 평가

```powershell
C:\Python\64\Python3119\python.exe finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred60_2025_full_small\finetune_predictor\checkpoints\best_model `
  --tokenizer-path finetune\outputs\stom_1s_grid_pred60_2025_full_small\finetune_tokenizer\checkpoints\latest_train_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred300_2025_full_small_walkforward36x3x50_eval `
  --lookback-window 300 `
  --predict-window 300 `
  --max-symbols 50 `
  --max-asofs 3 `
  --max-sessions 36 `
  --stride 300 `
  --batch-size 8 `
  --top-k 5 `
  --device cuda:0
```

### 15.2 비용 반영 Top-K

```powershell
C:\Python\64\Python3119\python.exe finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\stom_1s_pred300_2025_full_small_walkforward36x3x50_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10
```

### 15.3 조건식 / rolling validation / cost gate

```powershell
$pred = 'webui\stom_predictions\stom_1s_pred300_2025_full_small_walkforward36x3x50_eval_kronos.csv'
$prefix = 'stom_1s_pred300_2025_full_small_walkforward36x3x50_eval_kronos_cost25'

C:\Python\64\Python3119\python.exe finetune\search_stom_1s_filters.py `
  --prediction-csv $pred `
  --output-dir webui\qlib_backtests `
  --prefix $prefix `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10 `
  --min-trades 10 `
  --min-periods 3 `
  --min-coverage 0.5 `
  --rolling-validate `
  --rolling-train-periods 30 `
  --rolling-test-periods 10 `
  --rolling-step-periods 10
```

### 15.4 대시보드 검증

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_dashboard_helpers.py tests\test_training_monitor.py -q
cd webui\v2_src
npm run build
```

웹 확인:

```text
http://127.0.0.1:5070/training
```

## 16. 남은 위험

1. 현재 결과는 `max-asofs=3`, `max-symbols=50`, `max-sessions=36` 평가다. 완전 exhaustive 평가는 아직 아니다.
2. 300초는 pred60 checkpoint로 평가한 것이므로, 300초 전용 학습 결과와 다를 수 있다.
3. 비용 25bp 가정이 실제 체결 환경과 다르면 결론이 달라질 수 있다.
4. 추가 feature를 모델 입력에 직접 넣는 것은 공식 Kronos 호환성과 pretrained weight 활용성에 영향을 줄 수 있다.
5. 대용량 런타임 산출물은 git에 포함하지 않았으므로 재현 시 로컬 산출물 경로가 필요하다.

