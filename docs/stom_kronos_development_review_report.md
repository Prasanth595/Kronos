# STOM Kronos 개발/학습/예측 검토 보고서

작성 기준: 2026-05-07 KST  
대상 branch: `master`  
비교 기준: `origin/master..HEAD`  
검토 목적: 영어 commit 메시지 한글화, 초기 계획 대비 개발 품질 검토, 현재 단계 확인, 추가 개발 여부 확인, Kronos/STOM 학습·예측 과정 검증

---

## 1. 결론 요약

### 1-1. 전체 결론

현재 fork repository의 STOM/Kronos 작업은 **초기 목표였던 1~5단계**를 넘어서, 실제 STOM 1tick DB 분석 → OHLCV 변환 → CUDA/GPU 학습 → Kronos 예측 CSV 생성 → 웹 대시보드 검증 → score/ranking → 조건식 backtest → 외부 score export까지 진행되어 있다.

검토 결과:

```text
학습 인프라: 완료, 100%
실전 활용 확장: 3 / 5 완료, 60%
현재 단계: 활용 3단계 완료 — STOM ?? ??용 CSV/JSON score export
다음 단계: 외부 추천 프로그램 import 예시 또는 실전 조건식 강화
```

가장 중요한 판단:

```text
1. STOM tick DB를 Kronos 입력 형식으로 변환하는 구조는 코드와 테스트 기준으로 타당하다.
2. 실제 RTX 4080 SUPER + CUDA 환경에서 fine-tuning checkpoint가 생성되었다.
3. 생성 checkpoint를 사용한 Kronos 예측 CSV도 생성되었고 dashboard/API로 확인되었다.
4. 다만 예측 성능은 아직 “자동 매매 신호로 충분하다”고 볼 수준은 아니다.
5. 특히 all-table bounded 모델의 direction_accuracy는 0.40으로 낮다.
6. 따라서 현재 결과는 실전 매수/매도 신호가 아니라 “조건식·score·추가 필터와 결합할 후보 생성기”로 보는 것이 정확하다.
```

---

## 2. Commit 메시지 한글화 검토

### 2-1. 안전 조치

영어 commit 메시지를 한글로 바꾸는 작업은 git history rewrite에 해당하므로, 작업 전 복구용 backup branch를 만들었다.

```text
backup branch: backup/pre-korean-commit-messages-20260507-103421
rewrite 범위: origin/master..HEAD
remote push: 수행하지 않음
DB/대용량 산출물 수정: 없음
```

### 2-2. 한글화 후 commit 목록

```text
3e8508d Kronos가 STOM tick 데이터를 누수 없이 학습할 수 있게 준비하다
54ba6f9 STOM 예측 결과를 눈으로 검증할 수 있게 하다
afaa267 STOM 파이프라인에서 불필요한 셸 실행 위험을 줄이다
ebc0a34 STOM 파일럿 export 진행 상태를 재현 가능하게 남기다
a30b414 RTX 4080 SUPER에서 STOM GPU 파일럿 학습 경로를 입증하다
3908ba9 GPU 파일럿 checkpoint가 예측 산출물을 만들 수 있음을 기록하다
e9b4f3b STOM 대시보드가 실제 예측 CSV를 표시함을 검증하다
37c51cd STOM 학습 확대를 300개 테이블에서 먼저 검증하다
0d73b40 STOM 학습 확대를 1000개 테이블까지 검증하다
e6d935b 전체 STOM universe를 bounded 방식으로 학습 가능하게 만들다
19e6842 낮은 raw 방향정확도를 보완할 score 추천층을 만들다
74266b5 Score 연결 전 score 필터의 검증 근거를 분해하다
8b8cfde Kronos 추천 결과를 외부 프로그램이 읽을 수 있게 내보내다
```

### 2-3. old hash → new hash 대응

| 기존 영어 commit | 변경 후 한글 commit | 의미 |
|---|---|---|
| `f2a02cd` | `3e8508d` | STOM OHLCV fine-tuning 준비 |
| `4ef5987` | `54ba6f9` | 예측 검증 dashboard 추가 |
| `052a10e` | `afaa267` | 미사용 shell helper 제거 |
| `b833d48` | `ebc0a34` | 파일럿 export 진행 ledger |
| `4a6ba7d` | `a30b414` | GPU 파일럿 학습 검증 |
| `22595a4` | `3908ba9` | pilot checkpoint 예측 산출물 |
| `8771b58` | `e9b4f3b` | dashboard 실제 표시 검증 |
| `4fbfb15` | `37c51cd` | 300개 table 확대 |
| `aa0ee7e` | `0d73b40` | 1,000개 table 확대 |
| `850adf2` | `e6d935b` | 전체 table bounded 학습 |
| `6dc8dc3` | `19e6842` | score/ranking 추천층 |
| `c2f14ef` | `74266b5` | score filter backtest |
| `2bc6390` | `8b8cfde` | CSV/JSON score export |

주의:

```text
commit hash는 history rewrite 때문에 바뀌었다.
원래 hash로 돌아가야 하면 backup/pre-korean-commit-messages-20260507-103421 branch를 사용하면 된다.
```

---

## 3. 초기 계획 대비 개발 진행 검토

### 3-1. 초기 계획

초기 계획은 다음 5개 축이었다.

```text
1. STOM DB 구조 분석
2. STOM tick DB를 Kronos OHLCV 학습 데이터로 변환
3. GPU/CUDA 환경 확인 및 학습 준비
4. 학습 모델로 예측 CSV 생성
5. 웹 대시보드에서 실제값과 예측값 시각화
```

### 3-2. 실제 완료된 내용

초기 계획 대비 실제 결과는 다음과 같다.

| 구분 | 초기 계획 | 현재 결과 | 판단 |
|---|---|---|---|
| DB 분석 | STOM tick DB 구조 파악 | 2,427개 table scan, 2,425개 stock table 학습 가능 확인 | 완료 |
| 데이터 변환 | OHLCV CSV 생성 | `close_only`, grouped symbol/session, lookback 300, predict 60 변환 구현 | 완료 |
| GPU 학습 | CUDA 환경 학습 | torch `2.9.0+cu128`, RTX 4080 SUPER, cuda:0 학습 완료 | 완료 |
| 예측 | checkpoint 기반 예측 | pilot/300/1000/all bounded prediction CSV 및 metrics 생성 | 완료 |
| 시각화 | dashboard actual vs predicted | `/stom`, prediction API, headless screenshot 검증 | 완료 |
| 추가 활용 | 초기 계획 밖 | score/ranking, backtest report, score export | 후속 요청에 의해 진행됨 |

판단:

```text
초기 1~5 목표는 충족했다.
초기 계획보다 더 진행된 부분은 있지만, 이전 대화에서 사용자가 score화, 조건식 보완, 외부 프로그램 적용 가능성을 계속 요청했기 때문에 무단 개발로 보기는 어렵다.
```

---

## 4. 현재 페이지/단계 위치

현재 dashboard page는 다음 URL이다.

```text
http://localhost:7070/stom
또는 포트 충돌 시
http://localhost:7071/stom
```

현재 문서상 단계:

```text
학습 인프라: 9C / 9 완료, 100%
실전 활용 확장: 3 / 5 완료, 60%
현재 완료 단계: 활용 3단계 — CSV/JSON score export
```

현재 `/stom` dashboard 구성:

```text
Page 1. 목표/상태
Page 2~5 진행 계획
예측 파일 선택
Kronos Score Export
Page 5. 실제값 vs 예측값 chart
Top-K 예상등락률 검증
Kronos Score Top-K 추천
조건식 필터 백테스트 리포트
```

현재 다음 단계 후보:

```text
1. D:\Chanil_Park\Project\Programming\?? ?? ?? 쪽에서 score export CSV/JSON을 읽는 import 예시 구현
2. 거래대금/거래량/변동성/가격대 조건식 추가
3. 수수료/슬리피지 반영
4. 실시간/종가 추천 workflow 연결
```

---

## 5. 추가로 시키지 않은 개발이 있었는지 검토

### 5-1. 명확히 요청된 범위

다음은 사용자가 명시적으로 요청했거나 이전 요청의 자연스러운 후속이다.

```text
- STOM 1tick DB 분석
- OHLCV만 사용한 학습 가능성 검토
- 파인튜닝 가능 여부 및 직접 학습 준비
- GPU/CUDA 세팅 및 RTX 4080 SUPER 사용 검증
- 실제값/예측값 dashboard 시각화
- 여러 종목 학습 및 매일 다른 종목 universe 대응
- score 또는 예상 등락률 점수화
- 조건식/다른 프로그램 보완 가능성
- ?? ?? ?? 같은 외부 프로그램 적용 예시 검토
```

### 5-2. 초기 계획보다 확장된 개발

초기 1~5 이후 다음 기능이 추가되었다.

```text
- Kronos score/ranking 추천 API
- 조건식 필터 backtest report
- score band / 종목 / 시간대 segment 성과
- CSV/JSON score export
```

판단:

```text
초기 계획 밖 기능이지만, 이후 사용자가 score화, 조건식 보완, 다른 프로그램 적용을 반복 요청했기 때문에 “시키지 않은 개발”이라기보다 “후속 요구사항 반영”으로 보는 것이 맞다.
```

### 5-3. 하지 않은 것

```text
- ?? ?? ?? repository에 직접 파일을 쓰지 않았다.
- live trading/order 실행을 하지 않았다.
- 원본 STOM DB를 수정하지 않았다.
- 대용량 CSV/checkpoint/prediction output을 commit하지 않았다.
- fee/slippage를 반영한 실전 수익률 확정 판단을 하지 않았다.
```

---

## 6. Kronos 시스템 이해 검토

### 6-1. 이 repository에서 사용한 Kronos 이해

이 작업에서 Kronos는 다음 방식으로 이해하고 사용되었다.

```text
Kronos는 OHLCV + time feature sequence를 입력으로 받아 미래 close path를 예측하는 time-series model이다.
STOM tick DB는 그대로 모델에 넣지 않고, symbol/session별로 시간 순서를 유지한 OHLCV sequence로 변환했다.
lookback_window=300, predict_window=60 구조를 사용했다.
학습은 NeoQuasar/Kronos-small predictor와 NeoQuasar/Kronos-Tokenizer-base tokenizer를 기반으로 했다.
```

구현상 핵심 파일:

```text
finetune_csv/stom_tick_dataset.py
finetune_csv/prepare_stom_1tick.py
finetune_csv/configs/config_stom_1tick*.yaml
finetune_csv/train_sequential.py
finetune_csv/finetune_base_model.py
finetune_csv/stom_prediction_eval.py
webui/stom_dashboard.py
```

### 6-2. STOM tick DB → Kronos OHLCV 변환 이해

STOM DB는 종목별 table 구조다. 전체 scan 근거는 다음과 같다.

```text
DB: _database\stock_tick_back.db
DB size: 29,727,162,368 bytes
전체 table: 2,427개
학습 가능 stock table: 2,425개
비학습 table: moneytop, stockinfo
전체 stock rows: 122,522,300
전체 symbol/session group: 73,968
lookback 300 + predict 60 기준 eligible group: 73,650
예상 training window: 95,946,764
```

중요한 선택:

```text
price_mode=close_only
```

이유:

```text
STOM tick table에는 종가 column이 없는 경우가 있고 현재가를 close로 사용한다.
초/틱 단위에서 DB의 시가/고가/저가 의미가 확실하지 않으면, open/high/low/close를 모두 현재가 기반으로 맞추는 close_only가 더 보수적이다.
```

판단:

```text
Kronos가 요구하는 OHLCV 입력 형식에 맞추기 위한 변환은 적절하다.
다만 이것은 “진짜 일봉/분봉 OHLC”가 아니라 “STOM tick 현재가 sequence를 Kronos OHLCV 형태로 맞춘 close-only representation”이다.
따라서 모델 성능 해석 시 이 한계를 반드시 고려해야 한다.
```

---

## 7. STOM tick DB 학습이 정확히 되었는지 검토

### 7-1. CUDA/GPU 환경

검증 evidence:

```text
torch version: 2.9.0+cu128
cuda_available: true
cuda_version: 12.8
GPU: NVIDIA GeForce RTX 4080 SUPER
VRAM: 15.99 GB
```

판단:

```text
이 워크스테이션에서 GPU 학습이 실제로 가능한 상태로 세팅되었다.
```

### 7-2. 학습 scale-up 결과

| 단계 | 데이터 | device | validation loss | 학습 시간 | checkpoint |
|---|---:|---|---:|---:|---|
| GPU pilot | 100-table pilot | cuda:0 | 2.4311 | 1.40분 | 생성됨 |
| 300-table | 300개 table | cuda:0 | 2.3258 | 9.32분 | 생성됨 |
| 1,000-table | 1,000개 table | cuda:0 | 2.3030 | 35.22분 | 생성됨 |
| all-table bounded | 전체 universe bounded | cuda:0 | 2.3983 | 약 55.95분 | 생성됨 |

checkpoint 위치 예:

```text
finetune_csv/finetuned/stom_1tick_all_lookback300_pred60/basemodel/best_model/model.safetensors
```

판단:

```text
학습 프로세스 자체는 정상 완료되었다.
validation loss와 checkpoint 저장 근거가 있고, RTX 4080 SUPER에서 cuda:0으로 실행되었다.
```

### 7-3. 전체 DB 학습 방식의 한계

전체 원본 CSV는 다음 규모였다.

```text
full export rows: 122,345,828
full CSV size: 약 9GB
```

직접 학습 문제:

```text
9GB CSV를 pandas read_csv로 직접 학습하면 7시간 이상 loading 단계에서 정체되었고 GPU 사용률이 0%였다.
```

대응:

```text
각 symbol/session group을 연속 420 row로 제한한 bounded export 사용
bounded rows: 30,902,629
bounded groups: 73,582
max_rows_per_group: 420
```

판단:

```text
전체 universe의 종목/세션 coverage는 유지했지만, 각 group 전체 history를 모두 학습한 것은 아니다.
현재 all-table 학습은 “전체 종목/세션을 포함한 bounded 대표 구간 학습”이라고 표현하는 것이 정확하다.
```

---

## 8. 학습 모델을 잘 사용해 예측했는지 검토

### 8-1. Kronos mode 예측 사용 여부

`stom_prediction_eval.py`는 baseline mode와 kronos mode를 구분한다. 실제 학습 모델 예측은 다음처럼 수행되었다.

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline_all_bounded.csv `
  --output webui\stom_predictions\kronos_all_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 300 `
  --stride 120 `
  --mode kronos `
  --model-path finetune_csv\finetuned\stom_1tick_all_lookback300_pred60\basemodel\best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

판단:

```text
학습된 checkpoint를 지정해서 mode=kronos로 예측했으므로, baseline이 아니라 실제 Kronos model path를 사용한 예측이다.
```

### 8-2. 예측 metrics

| 예측 파일 | mode | windows | rows | MAPE | 방향정확도 | 평균 예측등락률 | 평균 실제등락률 |
|---|---|---:|---:|---:|---:|---:|---:|
| pilot_predictions.csv | baseline | 5 | 300 | 0.7366 | 0.20 | 0.0000 | 0.4960 |
| kronos_gpu_pilot_predictions.csv | kronos | 20 | 1,200 | 0.8289 | 0.50 | -0.2807 | 0.1523 |
| kronos_300_predictions.csv | kronos | 100 | 6,000 | 0.6687 | 0.58 | -0.1967 | 0.0202 |
| kronos_1000_predictions.csv | kronos | 200 | 12,000 | 0.5583 | 0.49 | -0.1879 | -0.0481 |
| kronos_all_predictions.csv | kronos | 300 | 18,000 | 0.2720 | 0.40 | -0.0751 | 0.0094 |

해석:

```text
MAPE는 all-table bounded에서 0.2720으로 가장 낮다.
그러나 direction_accuracy는 0.40으로 낮아, 방향성 예측을 그대로 매매 신호로 쓰기 어렵다.
MAE/RMSE는 종목 가격대 차이가 섞여 있어 scale 비교에 주의해야 한다.
```

### 8-3. Score/ranking으로 보완한 결과

raw prediction을 그대로 쓰지 않고, 다음 live 사용 가능 field만 score에 사용했다.

```text
pred_return_window
prediction_consistency
pred_range_pct
```

실제값 기반 field는 diagnostic으로만 분리했다.

```text
actual_return_window
direction_hit_window
realized_mape
```

Top-K/조건식 evidence:

```text
Top-10 recommendation hit_rate: 0.50
buy_candidate_score60: count 61, profit_factor 1.2632
score65_consistency80: count 17, profit_factor 1.4872
stable_positive_filter: count 7, hit/win 57.14%
```

주의:

```text
profit_factor는 수수료/슬리피지를 반영하지 않은 diagnostic이다.
표본 수가 작은 조건식은 과최적화 위험이 있다.
실전 적용 전 walk-forward 검증이 필요하다.
```

---

## 9. “잘 예측하는가?”에 대한 최종 판단

### 9-1. 긍정 근거

```text
1. 실제 fine-tuned checkpoint를 사용한 kronos mode 예측이 생성되었다.
2. dashboard/API에서 prediction CSV가 정상 표시된다.
3. MAPE 기준으로 all-table bounded 모델은 0.2720까지 낮아졌다.
4. score/ranking과 조건식 filter를 적용하면 raw 방향정확도보다 나은 후보군을 찾을 수 있는 신호가 있다.
```

### 9-2. 부정/한계 근거

```text
1. all-table bounded direction_accuracy는 0.40으로 낮다.
2. 1 epoch bounded 학습이므로 충분한 일반화 검증이라고 보기는 어렵다.
3. all-table은 전체 history 전부가 아니라 group당 420 row 제한 대표 구간이다.
4. 수수료/슬리피지/체결 가능성/거래대금 조건이 아직 반영되지 않았다.
5. test 기간이 walk-forward/live simulation 형태로 충분히 분리되어 있지 않다.
```

### 9-3. 결론

```text
“학습과 예측 파이프라인이 정상 작동한다”는 판단은 가능하다.
“이 모델이 단독으로 실전 매매에 충분히 잘 예측한다”는 판단은 아직 불가능하다.
현재 가장 정확한 표현은 “Kronos fine-tuned model을 이용한 후보 생성 + score/조건식 보완 단계까지 도달했다”이다.
```

---

## 10. 코드 구조 검토

### 10-1. 잘 된 점

```text
- 원본 DB read-only 원칙을 지켰다.
- symbol/session grouping으로 종목/일자 간 leakage를 줄였다.
- lookback/predict window를 명시적으로 관리한다.
- 대용량 산출물을 .gitignore로 제외했다.
- CUDA 환경 검증과 실제 training log를 남겼다.
- dashboard route가 helper import 실패 시 전체 app을 죽이지 않도록 처리했다.
- score는 미래 실제값을 쓰지 않고 prediction field만 사용한다.
- diagnostic 실제값은 명확히 분리했다.
```

### 10-2. 개선 필요

```text
- GroupedKlineDataset이 pandas eager read 구조라 9GB full CSV 직접 학습이 어렵다.
- all-table bounded는 group 앞쪽 420 row 중심이므로 장중 전체 패턴 학습에는 제한이 있다.
- 현재 score threshold는 경험적이고, walk-forward optimization이 아니다.
- 수수료/슬리피지/거래대금/호가/체결량 조건이 없다.
- 현재 dashboard는 검증용이며 운영용 권한/보안/로그 관리가 부족하다.
```

---

## 11. 검증 명령 및 결과

이번 검토 기준으로 사용한 주요 검증 명령:

```powershell
git log --reverse --oneline origin/master..HEAD
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

예상/기록된 최신 회귀 결과:

```text
17 passed, 1 warning
No broken requirements found.
```

---

## 12. 최종 권고

다음 단계는 둘 중 하나를 먼저 하는 것이 좋다.

### 권고 A: 외부 추천 프로그램 import 연결

```text
D:\Chanil_Park\Project\Programming\?? ?? ?? 프로그램에서
/api/stom/recommendation-export 또는 CSV/JSON export 파일을 읽어
기존 종목 추천 점수에 Kronos score를 보조 점수로 반영한다.
```

### 권고 B: 예측 신뢰도 강화

```text
거래대금, 거래량, 변동성, 가격대, 시간대, 수수료, 슬리피지를 조건식에 넣고
walk-forward 방식으로 threshold를 검증한다.
```

가장 중요한 운영 원칙:

```text
Kronos score는 지금 단계에서 “자동 매수 신호”가 아니라 “후보 종목을 줄이는 보조 점수”로만 사용해야 한다.
```