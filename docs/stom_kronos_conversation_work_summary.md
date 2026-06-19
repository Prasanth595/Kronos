# STOM tick Kronos 작업/대화/조사 통합 기록

작성일: 2026-05-10 KST
대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`
작성 브랜치: `work/stom-kronos-conversation-summary`
기준 원격: `origin/master` = `67b630e67f6a`
작업 기준 HEAD: `55650e600375`

## 1. 문서 목적

이 문서는 지금까지 대화에서 결정한 방향, 실제 조사 결과, 코드/문서 작업, 학습 성과, 남은 단계, 그리고 `master`에 누적되어 있던 커밋의 의미를 한 번에 추적하기 위한 기록이다.

핵심 목표는 다음 세 가지다.

1. STOM 1tick/1초봉 DB를 Kronos 공식 학습 흐름에 맞게 사용할 수 있는지 검증한다.
2. 실제 학습 모델의 예측값을 웹 대시보드에서 실제값과 비교하고, 종목별/전체 통계로 성과를 판단한다.
3. 4080 Super 로컬 학습과 RTX 5090 이상 클라우드 GPU 대여를 비교해, 전체 STOM tick 학습을 어느 범위까지 확대할지 결정한다.

---

## 2. 대화 흐름 요약

| 구간 | 질문/요구 | 정리된 결론 |
|---|---|---|
| 초기 검토 | STOM tick DB로 Kronos 학습/예측이 가능한가 | DB 테이블별 OHLCV 추출 후 Kronos 입력 형식으로 변환 가능. 원본 DB는 수정하지 않고 read-only로 사용해야 함. |
| GPU/실시간 예측 | GPU 사용 여부, 1분/실시간 예측 가능성 | CUDA GPU 사용 가능. 실시간 예측은 가능하지만 정확도 검증, 지연시간, 데이터 누수 방지, 운영 안정성이 별도 필요. |
| 일봉/종가매매 | 일봉 종가매매와 점수화 활용 | 예측 등락률, 방향성, confidence, Top-K ranking, 조건식 필터를 결합해 점수화 가능. 단, backtest와 holdout 검증이 필요. |
| 다른 프로그램 연동 | Future_trading 등 외부 추천 프로그램 적용 | 중간에 외부 연동을 검토했으나, 이후 사용자가 STOM tick 학습 자체를 우선하라고 하여 범위에서 제외. |
| 여러 종목 학습 | 여러 종목을 하나의 모델로 학습하는지 | Kronos는 여러 종목/여러 날짜를 하나의 시계열 학습 데이터셋으로 묶어 학습 가능. 매일 거래대금 상위 100위처럼 종목 구성이 바뀌어도 공통 모델 방식이 적합. |
| 1초봉/1분봉 | 09:00~09:30 1초봉 OHLCV 학습 가능 여부 | lookback 300초, pred30/pred60 같은 고정 horizon으로 학습 가능. 전체 길이/날짜/테이블을 window sample로 변환해야 함. |
| Qlib 논의 | 공식 가이드가 Qlib을 언급하는 이유 | QlibDataset 기반 학습은 Kronos 공식 파인튜닝 흐름에 더 가깝고, split/normalization/dataloader 재현성이 좋아 전체 학습 확대에 적합. |
| 정확도 0.4 문제 | 0.4면 랜덤보다 나은가 | 방향 정확도 0.4 수준은 단독 매매 신호로 부족. 더 많은 데이터, 공식 학습, rolling/holdout 검증, score 필터가 필요하다고 판단. |
| 공식 200k 학습 | Kronos 공식 순서 준수 여부 | tokenizer fine-tune 후 predictor fine-tune 순서로 200k 공식 실험을 완료. 전체 가능 샘플 대비 약 0.27% 데이터 coverage라 최종 판단에는 부족. |
| 대시보드 | 실제값/예측값/종목별 통계 시각화 | `/stom` 대시보드, 종목별 통계 API, 예측 CSV 기반 차트/필터/진단 기능을 구현하고 브라우저로 직접 확인. |
| 전체 학습/클라우드 | 2025년/전체 STOM tick 학습 시간과 5090 대여 | 2025년 Kronos-small은 4080S 약 8일, RTX 5090 약 3.7일 추정. 전체는 4080S 약 31.7일, RTX 5090 약 14.4일 추정. |

---

## 3. 현재까지 구현/검증된 주요 산출물

### 3.1 STOM tick 데이터 변환

- `finetune_csv/stom_tick_dataset.py`
- `finetune_csv/prepare_stom_1tick.py`
- `finetune_csv/stom_ohlcv_pipeline.py`
- `finetune_csv/configs/config_stom_1tick*.yaml`

기능:

- STOM SQLite tick DB를 read-only로 읽음
- 각 종목 테이블의 날짜/session을 분리
- 09:00~09:30 구간 1초봉 기준으로 정규화
- `lookback=300`, `pred=30/60` window 학습 샘플 생성
- 기존 DB를 수정하지 않고 CSV/manifest/학습 입력으로 변환

### 3.2 Kronos 공식 파인튜닝 경로

- `finetune/train_tokenizer.py`
- `finetune/train_predictor.py`
- `finetune/dataset.py`
- `finetune/config.py`
- `finetune/run_stom_1s_finetune.py`
- `finetune/model_source.py`

확인된 공식 순서:

1. STOM 데이터로 tokenizer fine-tune
2. fine-tuned tokenizer를 사용해 predictor fine-tune
3. predictor checkpoint로 예측 CSV 생성
4. holdout/test 및 대시보드에서 실제값과 비교

최근 완료 기준:

- tokenizer: `NeoQuasar/Kronos-Tokenizer-base`
- predictor: `NeoQuasar/Kronos-small`
- 학습명: `stom_1s_grid_pred60_official_200k`
- train: 200,000 samples
- validation: 40,000 samples
- 전체 train 가능량 대비 coverage: 약 0.2713%
- train+val 가능량 대비 coverage: 약 0.2677%

### 3.3 평가/필터/통계

- `finetune/evaluate_stom_1s_checkpoint.py`
- `finetune/search_stom_1s_filters.py`
- `finetune_csv/stom_prediction_eval.py`
- `tests/test_stom_*`

확인한 내용:

- 단순 방향 정확도 0.4 수준은 실제 사용에 부족
- pred60 대형 walk-forward와 rolling 조건식 검증에서 비용 대비 확대 gate가 필요하다고 판단
- 조건식/score band/Top-K를 보완층으로 두되, 과최적화 방지를 위해 rolling validation 필요

### 3.4 웹 대시보드

- `webui/stom_dashboard.py`
- `webui/templates/stom_dashboard.html`
- `webui/app.py`
- `webui/run.py`
- `webui/README_STOM_DASHBOARD.md`

기능:

- 예측 CSV 목록 조회
- 실제값/예측값 그래프 확인
- 종목별 통계 진단
- 전체 통계 요약
- 추천/score export 확인
- 브라우저 직접 실행 검증 완료

현재 직접 확인용 서버 기록:

- URL: `http://127.0.0.1:5000/stom`
- 마지막 확인 당시 Flask 서버가 정상 응답
- 브라우저/Playwright fallback으로 화면 요소 검증

---

## 4. STOM tick DB 분석 결과

분석 기준:

- DB: `_database/stock_tick_back.db`
- 원본 DB read-only
- 1초 정규화
- 09:00:00~09:30:00
- lookback 300초
- pred60
- `price_mode=close_only`

연도별 직접 계산 결과:

| 연도 | 거래일/session | 전체 pred60 sample | 70/15/15 기준 train+val sample |
|---|---:|---:|---:|
| 2022 | 193 | 21,959,234 | 18,637,997 |
| 2023 | 244 | 28,176,371 | 24,002,988 |
| 2024 | 240 | 24,712,681 | 21,208,505 |
| 2025 | 240 | 26,569,619 | 22,694,289 |
| 2026 | 34 | 3,320,745 | 2,735,733 |
| 전체 reference | - | 104,738,650 | - |
| 전체 official manifest train+val | - | - | 89,656,982 |

2025년 상세:

- compatible tables: 2,425 / 2,427
- 2025년 row가 있는 tables: 1,638
- sessions: 240
- raw distinct rows: 30,435,244
- regularized rows: 33,319,260
- pred60 possible samples: 26,569,619
- train+val samples: 22,694,289

---

## 5. 학습 시간/비용 조사 요약

### 5.1 로컬 RTX 4080 Super 실측 기준

공식 200k 실험 실측:

| 단계 | samples | 시간 |
|---|---:|---:|
| tokenizer | train 200k + val 40k | 3,211초, 약 53.5분 |
| predictor | train 200k + val 40k | 4,129초, 약 68.8분 |
| 합계 | 240k | 7,340초, 약 2.04시간 |

이를 기준으로 선형 환산하면:

| 대상 | 4080 Super 예상 |
|---|---:|
| 2025년 Kronos-small train+val | 약 8.0일 |
| 전체 official train+val | 약 31.7일 |
| 전체 reference window | 약 37.1일 |

### 5.2 RTX 5090 이상 GPU 대여 검토

웹 조사 기준 가격은 2026-05-10 확인값이며 변동 가능성이 크다.

| 대상 | RTX 5090 예상 | 비용 추정 |
|---|---:|---:|
| 2025년 Kronos-small | 약 3.7일 | 약 $60~$87 |
| 전체 official train+val | 약 14.4일 | 약 $239~$343 |
| 전체 reference window | 약 16.9일 | 약 $279~$400 |

권장 판단:

1. RTX 5090 1대에서 200k benchmark를 먼저 실행한다.
2. 실제 samples/sec로 2025년 전체 학습 시간을 재계산한다.
3. 2025년 Kronos-small 전체 학습을 우선 수행한다.
4. 성과가 좋아질 때만 Kronos-base/H100/H200/B200으로 확대한다.

주의:

- 현재 코드에는 AMP/autocast/BF16/FP16/DDP 최적화가 충분히 적용되어 있지 않다.
- H100/H200/B200은 빠르지만, 현재 코드 상태에서는 비용 대비 효율이 RTX 5090보다 낮을 수 있다.

참고 출처:

- NVIDIA RTX 5090: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/
- RunPod Pricing: https://www.runpod.io/pricing
- Lambda GPU Cloud: https://lambda.ai/pricing
- DeployBase RTX 5090 Cloud: https://deploybase.ai/articles/rtx-5090-cloud
- gpus.io RTX 5090: https://gpus.io/en/gpus/rtx5090
- Runcrate RTX 5090: https://www.runcrate.ai/pricing/gpu/rtx-5090
- NeevCloud RTX 5090: https://www.neevcloud.com/nvidia-rtx-5090.php

---

## 6. Kronos 모델별 판단

| 모델 | 파라미터 | context | 현재 판단 |
|---|---:|---:|---|
| Kronos-mini | 4.1M | 2048 | 빠른 실험/파이프라인 검증용 |
| Kronos-small | 24.7M | 512 | 현재 주력 기준 모델. 4080S/5090에서 현실적 |
| Kronos-base | 102.3M | 512 | small 개선 신호 확인 후 확대 검토 |
| Kronos-large | 499.2M | 512 | 공개/실행 가능성/비용 측면에서 현재 비권장 |

2025년 기준 추정:

| 모델 | 4080 Super | RTX 5090 |
|---|---:|---:|
| mini | 약 3.6일 | 약 1.6일 |
| small | 약 8.0일 | 약 3.7일 |
| base | 약 30.5일 | 약 13.9일 |
| large 추정 | 약 144.6일 | 약 65.7일 |

---

## 7. 현재까지 master 커밋 전체 정리

현재 작업 시작 전 `master`는 `origin/master` 대비 43개 커밋 ahead 상태였다. 아래 표는 각 커밋의 의도를 작업 흐름별로 재분류한 것이다.

| # | commit | 날짜 | 분류 | 커밋 의도 |
|---:|---|---|---|---|
| 1 | `3e8508d` | 2026-05-06 | 데이터/DB 이해와 변환 기반 | Kronos가 STOM tick 데이터를 누수 없이 학습할 수 있게 준비하다 |
| 2 | `54ba6f9` | 2026-05-06 | 데이터/DB 이해와 변환 기반 | STOM 예측 결과를 눈으로 검증할 수 있게 하다 |
| 3 | `afaa267` | 2026-05-06 | 데이터/DB 이해와 변환 기반 | STOM 파이프라인에서 불필요한 셸 실행 위험을 줄이다 |
| 4 | `ebc0a34` | 2026-05-06 | 데이터/DB 이해와 변환 기반 | STOM 파일럿 export 진행 상태를 재현 가능하게 남기다 |
| 5 | `a30b414` | 2026-05-06 | GPU 파일럿과 대시보드 검증 | RTX 4080 SUPER에서 STOM GPU 파일럿 학습 경로를 입증하다 |
| 6 | `3908ba9` | 2026-05-06 | GPU 파일럿과 대시보드 검증 | GPU 파일럿 checkpoint가 예측 산출물을 만들 수 있음을 기록하다 |
| 7 | `e9b4f3b` | 2026-05-06 | GPU 파일럿과 대시보드 검증 | STOM 대시보드가 실제 예측 CSV를 표시함을 검증하다 |
| 8 | `37c51cd` | 2026-05-06 | GPU 파일럿과 대시보드 검증 | STOM 학습 확대를 300개 테이블에서 먼저 검증하다 |
| 9 | `0d73b40` | 2026-05-06 | GPU 파일럿과 대시보드 검증 | STOM 학습 확대를 1000개 테이블까지 검증하다 |
| 10 | `e6d935b` | 2026-05-07 | GPU 파일럿과 대시보드 검증 | 전체 STOM universe를 bounded 방식으로 학습 가능하게 만들다 |
| 11 | `19e6842` | 2026-05-07 | 추천/점수화와 외부 연동 검토 | 낮은 raw 방향정확도를 보완할 score 추천층을 만들다 |
| 12 | `74266b5` | 2026-05-07 | 추천/점수화와 외부 연동 검토 | Adapter 연결 전 score 필터의 검증 근거를 분해하다 |
| 13 | `8b8cfde` | 2026-05-07 | 추천/점수화와 외부 연동 검토 | Kronos 추천 결과를 외부 프로그램이 읽을 수 있게 내보내다 |
| 14 | `1c3974e` | 2026-05-07 | 검토/문서화/파인튜닝 정합성 | Kronos 개발 과정을 검토 가능하게 정리하다 |
| 15 | `710afc9` | 2026-05-07 | 검토/문서화/파인튜닝 정합성 | STOM Kronos 파인튜닝 검증 근거를 분리하다 |
| 16 | `3c3017c` | 2026-05-07 | 검토/문서화/파인튜닝 정합성 | STOM 데이터를 Qlib 검증 흐름으로 보낼 수 있게 하다 |
| 17 | `158e904` | 2026-05-07 | 검토/문서화/파인튜닝 정합성 | Qlib 실제 실행 전 환경 게이트를 명확히 하다 |
| 18 | `9996847` | 2026-05-07 | 검토/문서화/파인튜닝 정합성 | Qlib 실제 변환 가능성을 증거로 고정하다 |
| 19 | `540e540` | 2026-05-08 | 검토/문서화/파인튜닝 정합성 | 1초봉 전체 재학습 전에 시간 기준 데이터를 고정하다 |
| 20 | `c8636ba` | 2026-05-08 | 검토/문서화/파인튜닝 정합성 | STOM 1초봉 전체 export 근거를 고정하다 |
| 21 | `bd5d5ca` | 2026-05-08 | 검토/문서화/파인튜닝 정합성 | STOM 1초봉 전체 데이터를 실제 파인튜닝 루프에 연결하다 |
| 22 | `94c2ab3` | 2026-05-08 | 평가/필터/확대 gate | STOM 1초봉 checkpoint를 실제 holdout 방향성 평가로 연결하다 |
| 23 | `ab07709` | 2026-05-08 | 평가/필터/확대 gate | STOM 1초봉 60초 모델의 walk-forward 필터 한계를 고정하다 |
| 24 | `0f76ea4` | 2026-05-08 | 평가/필터/확대 gate | STOM 1초봉 조건식 과최적화를 rolling 검증으로 분리하다 |
| 25 | `bbb0dbf` | 2026-05-09 | 추천/점수화와 외부 연동 검토 | 외부 trading-program 연동을 제외하고 STOM tick 학습 범위를 고정하다 |
| 26 | `60be1e3` | 2026-05-09 | 평가/필터/확대 gate | 전체 데이터 학습 확대를 단계형 실행 계획으로 고정하다 |
| 27 | `56c38bd` | 2026-05-09 | 평가/필터/확대 gate | pred60 대형 walk-forward가 학습 확대 조건을 충족하지 못함을 고정하다 |
| 28 | `9cef1eb` | 2026-05-09 | 평가/필터/확대 gate | 비용 민감도 gate로 학습 확대 결정을 자동화하다 |
| 29 | `2153f9f` | 2026-05-09 | 공식 Kronos 200k 학습 | Kronos 공식 tokenizer 학습 경로를 Windows 단일 GPU에 맞추다 |
| 30 | `9ef5207` | 2026-05-09 | 공식 Kronos 200k 학습 | STOM pred60 tokenizer 20k 실측으로 확대 시간을 고정하다 |
| 31 | `66dd204` | 2026-05-09 | 공식 Kronos 200k 학습 | STOM pred60 tokenizer 200k 학습을 공식 순서에 고정하다 |
| 32 | `6fc9bf2` | 2026-05-09 | 공식 Kronos 200k 학습 | STOM tokenizer 기반 predictor 200k 학습을 완료하다 |
| 33 | `79c5e6c` | 2026-05-09 | 공식 Kronos 200k 학습 | Official 200k 예측 그래프와 필터 검증 속도를 확보하다 |
| 34 | `60dc759` | 2026-05-09 | 평가/필터/확대 gate | Official 200k 성과를 비용 gate 기준으로 판정하다 |
| 35 | `eb3f9ba` | 2026-05-09 | 평가/필터/확대 gate | pred30 확대를 cost gate 이후로 미루다 |
| 36 | `3dbb149` | 2026-05-09 | 평가/필터/확대 gate | 1M 이후 확대를 목적별 실행안으로 분리하다 |
| 37 | `a488b0e` | 2026-05-09 | 기타 | Ralph 마무리 전 공식 학습 변경부를 정리하다 |
| 38 | `4f2bc02` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | 통계 대시보드 고도화 계획을 autopilot 흐름으로 고정하다 |
| 39 | `480803e` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | 예측 CSV의 종목별 통계 진단 API를 추가하다 |
| 40 | `3da9438` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | 종목별 통계 진단을 STOM 대시보드 화면에 연결하다 |
| 41 | `a1b6ae7` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | 통계 대시보드 변경을 리뷰하고 출력 안전성을 보강하다 |
| 42 | `df683a1` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | 브라우저 검증에서 발견한 표시 품질 문제를 없애다 |
| 43 | `55650e6` | 2026-05-10 | 통계 대시보드와 GPU 대여 연구 | GPU 대여 기반 Kronos 확대 학습 판단 기준을 남기다 |

---

## 8. 단계별 완료율

| 단계 | 내용 | 상태 | 완료율 |
|---:|---|---|---:|
| 1 | STOM DB 구조 파악과 OHLCV 추출 가능성 확인 | 완료 | 100% |
| 2 | tick/1초봉 학습 데이터셋 변환기 구현 | 완료 | 100% |
| 3 | 파일럿 export/GPU 학습/예측 CSV 생성 | 완료 | 100% |
| 4 | 웹 대시보드 실제값/예측값 시각화 | 완료 | 100% |
| 5 | 전체 테이블 bounded 학습 가능성 검증 | 완료 | 100% |
| 6 | score/ranking/조건식 보완층 검토 | 완료 | 100% |
| 7 | Qlib/Kronos 공식 파인튜닝 방향 검토 | 완료 | 100% |
| 8 | 공식 tokenizer→predictor 200k 학습 | 완료 | 100% |
| 9 | 종목별 통계 대시보드 고도화 | 완료 | 100% |
| 10 | 2025년/전체 학습량과 GPU 대여 비용 산정 | 완료 | 100% |
| 11 | 2025년 전체 Kronos-small 학습 | 남음 | 0% |
| 12 | 2025년 holdout 및 2026년 forward 검증 | 남음 | 0% |
| 13 | 성과 개선 시 Kronos-base 확대 실험 | 남음 | 0% |
| 14 | 전체 2022~2026 학습 및 실전 적용 판단 | 남음 | 0% |

전체 연구/개발 관점 진행률:

```text
██████████████░░░░░░  약 70%
```

해석:

- 파이프라인, 대시보드, 공식 200k 학습, 비용 산정은 상당히 진행됨.
- 그러나 사용자가 가장 보고 싶어 한 “전체 STOM tick 학습 후 실제 그래프/통계 성과 확인”은 아직 남아 있음.
- 따라서 다음 핵심은 **2025년 전체 학습**이다.

---

## 9. 남은 핵심 작업

우선순위 순서:

1. **RTX 4080S 또는 RTX 5090에서 2025년 Kronos-small 전체 학습 실행**
   - 4080S 예상: 약 8~9일
   - RTX 5090 예상: 약 3~5일
2. 학습 완료 checkpoint로 전체 종목 예측 CSV 생성
3. `/stom` 대시보드에서 종목별 실제값/예측값 비교
4. 전체 통계 확인
   - direction accuracy
   - MAE/RMSE/MAPE
   - pred_return bucket별 실제 return
   - Top-K 추천 성과
   - 날짜별/종목별 분산
5. 2026년 또는 최근 미사용 기간 forward test
6. 성과가 baseline/random/persistence보다 개선될 경우 Kronos-base 확대
7. 개선이 없으면 feature/label/horizon/market regime 분리 재설계

---

## 10. 브랜치/커밋 정리 계획 기록

사용자는 현재 `master`에서 직접 누적된 작업을 새 브랜치에 이동하고, `master`에는 그 브랜치를 merge하는 방식으로 정리하라고 요청했다.

승인된 정리 방식:

1. 현재 `master` HEAD를 안전 백업 브랜치로 보존
2. 현재 HEAD에서 작업 브랜치 `work/stom-kronos-conversation-summary` 생성
3. 이 문서를 작업 브랜치에서 커밋
4. `master`를 `origin/master`로 되돌림
5. 작업 브랜치를 `master`로 `--no-ff` merge
6. 최종 `master`는 “원격 기준 + 작업 브랜치 merge commit” 형태가 됨

이 방식의 장점:

- 기존 43개 커밋을 잃지 않음
- 작업 이력을 하나의 feature branch로 묶어 볼 수 있음
- `master` 첫 번째 부모 이력이 원격 기준에서 merge commit으로 정리됨

주의:

- 원격 push는 수행하지 않음
- `.omx/` runtime 파일은 커밋하지 않음
- reset 전 backup/work branch가 현재 HEAD와 문서 커밋을 포함하는지 검증해야 함

---

## 11. 최종 판단

지금까지의 작업은 “STOM tick을 Kronos로 학습할 수 있는가?”라는 질문에는 상당 부분 답했다.

- 데이터 변환 가능: 예
- 여러 종목 통합 학습 가능: 예
- 공식 tokenizer→predictor fine-tune 가능: 예
- 4080S GPU 사용 가능: 예
- 실제값/예측값 대시보드 확인 가능: 예
- 현재 200k 모델만으로 실전 판단 가능: 아니오
- 전체/2025년 학습을 통해 성과 개선을 검증할 필요: 매우 높음

따라서 다음 방향은 명확하다.

> **2025년 전체 STOM tick 데이터로 Kronos-small을 공식 방식으로 학습하고, 대시보드에서 실제값/예측값/종목별 통계/Top-K 성과를 확인한다. 그 결과가 개선될 때만 Kronos-base 또는 전체 연도 학습으로 확대한다.**

---

## 12. 2026-05-11 업데이트: 2025년 전체 학습 preflight 완료

다음 단계로 2025년 STOM tick 전체 학습 전 preflight를 완료했다.

추가된 핵심 기능:

- `finetune_csv/stom_tick_dataset.py`: `session_start`, `session_end` 기반 날짜/session 필터 추가
- `finetune/qlib_stom_pipeline.py`: 2025년 전용 Qlib/Kronos export를 위한 `--session-start`, `--session-end` 인자 추가
- `finetune/preflight_stom_2025_full.py`: DB read-only, CUDA, 디스크, 샘플 수, export/training 명령을 자동 점검
- `docs/stom_2025_full_training_preflight.md`: preflight 결과와 다음 실행 명령 기록

실제 preflight 결과:

- 상태: `ready_with_actions`
- blocker: 0개
- DB: `_database/stock_tick_back.db`, 27.69GB, 2,427 tables, read-only/query_only 통과
- CUDA: RTX 4080 SUPER, PyTorch 2.9.0+cu128, VRAM 15.99GB
- D: 여유 공간: 약 538.64GB
- 2025년 train samples: 18,771,531
- 2025년 validation samples: 3,922,758
- train+validation: 22,694,289
- 4080S 예상 학습 시간: 약 192.81시간, 약 8.03일

현재 단계 판단:

```text
전체 진행률: ████████████████░░░░ 80%
현재 단계: 2025년 전체 학습 preflight 완료
다음 단계: 2025년 processed dataset export
남은 단계: 2025년 full training → 예측 CSV → 대시보드/통계 검증 → base 확대 여부 판단
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 processed dataset export를 실행하고 export report, train/val/test pkl 생성 여부, session split, row/sample 수를 검증한 뒤 문서와 commit으로 남기세요.
```

---

## 13. 2026-05-11 업데이트: 2025년 processed dataset export 완료

2025년 STOM tick pred60 전체 학습을 위한 processed dataset export를 완료했다.

핵심 결과:

- export duration: 1,433.24초, 약 23분 53초
- output: `finetune/qlib_exports/stom_1s_grid_pred60_2025/processed_datasets`
- `train_data.pkl`: 약 1.234GB
- `val_data.pkl`: 약 0.258GB
- `test_data.pkl`: 약 0.254GB
- export report: `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json`
- split 기준: session chronological split
- train sessions: 168, 20250103~20250910
- val sessions: 36, 20250911~20251106
- test sessions: 36, 20251107~20251230
- train samples: 18,806,883
- val samples: 3,925,397
- train+val samples: 22,732,280

현재 단계 판단:

```text
전체 진행률: ██████████████████░░ 90%
현재 단계: 2025년 processed dataset export 완료
다음 단계: 2025년 Kronos-small tokenizer→predictor full training
남은 단계: checkpoint 검증 → 예측 CSV 생성 → 대시보드 실제/예측 비교 → 성과 판단
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습을 checkpoint/resume와 절전 방지 조건을 확인한 뒤 실행하고, tokenizer/predictor 로그와 checkpoint 생성 여부를 주기적으로 점검하며 완료 후 문서와 commit으로 남기세요.
```

---

## 14. 2026-05-11 업데이트: 실시간 학습 모니터링 선행 구현

2025년 STOM tick pred60 Kronos-small 전체 학습은 RTX 4080 SUPER 기준 약 8~9일이 예상되므로, 본 학습을 바로 시작하기 전에 실시간 관측 기능을 먼저 추가했다.

추가/변경 내용:

- `finetune/run_stom_1s_finetune.py`: child process stdout을 실시간으로 로그 파일에 기록하고 progress JSON을 갱신하도록 변경
- `finetune/training_progress.py`: Kronos 학습 로그 parser와 progress sidecar writer 추가
- `webui/training_monitor.py`: `finetune/outputs` run 목록, status, log tail, GPU 상태 helper 추가
- `webui/app.py`: `/training` 및 `/api/training/*` route 추가
- `webui/templates/training_dashboard.html`: 학습 단계, 진행률, ETA, loss, GPU/전력, 로그 tail 표시
- `docs/stom_training_monitor_dashboard.md`: 사용법과 본 학습 전 체크포인트 문서화

현재 단계 판단:

```text
전체 진행률: ███████████████████░ 95%
현재 단계:   ████████████████████ 100%  실시간 학습 모니터링 구현 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 5%   2025 full training → 평가/대시보드 검증
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습을 실행하기 전에 /training 대시보드가 실시간 progress/log/GPU 상태를 표시하는지 브라우저로 확인하고, 확인되면 2025 full training을 시작한 뒤 checkpoint와 progress를 주기적으로 점검하세요.
```
---

## 15. 2026-05-11 업데이트: /training 서버·API·브라우저 검증 완료

실시간 학습 모니터 구현 후 실제 서버와 브라우저에서 검증했다.

검증 결과:

- 서버: `http://127.0.0.1:5070/training`
- API: `/api/training/runs`, `/status`, `/logs`, `/gpu` 모두 200 OK
- 브라우저: Playwright headless 검증 통과
- 표시 확인: run 목록, 전체 진행률, tokenizer/predictor 단계, GPU, log tail
- console/page error: 0개
- 추가 수정: dry-run progress가 50%처럼 보이지 않도록 0% 유지, dry-run log placeholder 생성

현재 단계 판단:

```text
전체 진행률: ███████████████████░ 96%
현재 단계:   ████████████████████ 100%  /training 실사용 검증 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 4%   2025 full training → checkpoint → 예측/성과 검증
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습을 시작하고, /training 대시보드에서 tokenizer 단계의 progress/log/GPU 상태가 실제로 갱신되는지 1차 확인한 뒤 장기 학습 상태로 전환하세요.
```
---

## 16. 2026-05-11 업데이트: 2025년 STOM full training 실제 시작

2025년 STOM tick pred60 Kronos-small 전체 학습을 실제로 시작했다.

실행 상태:

- run: `stom_1s_grid_pred60_2025_full_small`
- runner PID: 3944
- tokenizer child PID: 70448
- stage: tokenizer running
- train samples: 18,806,883
- validation samples: 3,925,397
- tokenizer train steps/epoch: 4,701,721
- 확인된 로그: `Step 2000/4701721`, loss `-0.0299`
- `/training`: `http://127.0.0.1:5070/training`에서 running/progress/log/GPU 표시 확인
- GPU: RTX 4080 SUPER, VRAM 약 3.1GB 사용, utilization 약 37~40% 관측

현재 단계 판단:

```text
전체 진행률: ███████████████████░ 97%
현재 단계:   ████████████████████ 100%  full training 시작 및 초기 live 검증 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 3%   장기 학습 완료 → checkpoint → 예측/성과 검증
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습의 tokenizer 단계가 계속 정상 진행 중인지 progress/log/GPU를 재점검하고, checkpoint 생성 전까지 중간 상태를 문서와 commit으로 주기적으로 남기세요.
```
---

## 17. 2026-05-11 업데이트: full training tokenizer 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 중간 점검했다.

확인 결과:

- runner PID: 3944 실행 중
- tokenizer PID: 70448 실행 중
- stage: tokenizer running
- 1차 샘플: step 28,000 / 4,701,721, loss -0.0274
- 2차 샘플: step 30,000 / 4,701,721, loss -0.0316
- 문서 검증 직전 추가 확인: step 31,000 / 4,701,721, loss -0.0306
- tokenizer stage progress: 0.6381%
- overall progress: 0.3190%
- samples/sec: 약 72.63
- GPU: RTX 4080 SUPER, utilization 약 35~37%, VRAM 약 3.1GB, 온도 약 44~46°C

현재 단계 판단:

```text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  중간 progress/log/GPU 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 0.3190%
```

다음 권장 OMX 명령:

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 progress/log/GPU를 다시 점검하고, step 증가와 이상 여부를 문서화한 뒤 checkpoint 생성 전까지 중간 commit으로 남기세요.
```
---

## 18. 2026-05-11 업데이트: full training tokenizer 두 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 두 번째로 중간 점검했다.

확인 결과:

- runner PID: 3944 실행 중
- tokenizer PID: 70448 실행 중
- stage: tokenizer running
- 1차 샘플: step 132,000 / 4,701,721, loss -0.0251
- 2차 샘플: step 134,000 / 4,701,721, loss -0.0308
- 문서 검증 직전 추가 확인: step 140,000 / 4,701,721, loss -0.0339
- tokenizer stage progress: 2.9776%
- overall progress: 1.4888%
- samples/sec: 약 76.81
- GPU: RTX 4080 SUPER, 최신 관측 NVIDIA GeForce RTX 4080 SUPER, 38, 3004, 16376, [N/A], 43, 이전 샘플 기준 utilization 약 38~46%, VRAM 약 3.1~3.3GB, 온도 약 44~50°C

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  두 번째 중간 progress/log/GPU 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 1.4888%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~
---

## 19. 2026-05-11 업데이트: full training tokenizer 세 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 세 번째로 중간 점검했다.

확인 결과:

- stage: tokenizer running
- 이전 commit 후 최종 관측: step 142,000 / 4,701,721, overall 1.5101%
- 이번 1차 샘플: step 164,000 / 4,701,721, loss -0.0329
- 이번 2차 샘플: step 165,000 / 4,701,721, loss -0.0339
- 문서 작성 직전: step 167,000 / 4,701,721, loss -0.0269
- tokenizer stage progress: 3.5519%
- overall progress: 1.7759%
- samples/sec: 약 76.5
- checkpoint/model file count: 0
- predictor 전환: 아직 전
- GPU: NVIDIA GeForce RTX 4080 SUPER, 39, 2995, 16376, [N/A], 44

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  세 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 1.7759%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~
---

## 20. 2026-05-11 업데이트: full training tokenizer 네 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 네 번째로 중간 점검했다.

확인 결과:

- stage: tokenizer running
- 이전 commit 최종 관측: step 167,000 / 4,701,721, overall 1.7759%
- 이번 1차 샘플: step 460,000 / 4,701,721, loss -0.0303, overall 4.8918%
- 이번 2차 샘플: step 462,000 / 4,701,721, loss -0.0191, overall 4.9131%
- 문서 작성 직전: step 462,000 / 4,701,721, loss -0.0191
- tokenizer stage progress: 9.8262%
- overall progress: 4.9131%
- samples/sec: 약 78.04
- checkpoint/model/predictor file count: 0
- predictor 전환: 아직 전
- GPU: NVIDIA GeForce RTX 4080 SUPER, 38, 3018, 16376, [N/A], 42

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  네 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     ░░░░░░░░░░░░░░░░░░░░ 4.9131%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~
---

## 21. 2026-05-11 업데이트: full training tokenizer 다섯 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 다섯 번째로 중간 점검했다.

확인 결과:

- stage: tokenizer running
- 이전 commit 최종 관측: step 463,000 / 4,701,721, overall 4.9237%
- 이번 1차 샘플: step 662,000 / 4,701,721, loss -0.0297, overall 7.0400%
- 이번 2차 샘플: step 663,000 / 4,701,721, loss -0.0298, overall 7.0506%
- 문서 작성 직전: step 664,000 / 4,701,721, loss -0.0324
- tokenizer stage progress: 14.1225%
- overall progress: 7.0612%
- samples/sec: 약 73.42
- checkpoint/model/predictor file count: 0
- predictor 전환: 아직 전
- GPU: NVIDIA GeForce RTX 4080 SUPER, 38, 3179, 16376, [N/A], 42

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  다섯 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     █░░░░░░░░░░░░░░░░░░░ 7.0612%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~
---

## 22. 2026-05-12 업데이트: full training tokenizer 여섯 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 날짜 전환 후 여섯 번째로 중간 점검했다.

확인 결과:

- stage: tokenizer running
- 이전 commit 최종 관측: step 665,000 / 4,701,721, overall 7.0719%
- 이번 1차 샘플: step 682,000 / 4,701,721, loss -0.0332, overall 7.2527%
- 이번 2차 샘플: step 683,000 / 4,701,721, loss -0.0233, overall 7.2633%
- 문서 작성 직전: step 684,000 / 4,701,721, loss -0.0261
- tokenizer stage progress: 14.5479%
- overall progress: 7.2739%
- samples/sec: 약 72.85
- checkpoint/model/predictor file count: 0
- predictor 전환: 아직 전
- GPU: NVIDIA GeForce RTX 4080 SUPER, 38, 3076, 16376, [N/A], 42

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  여섯 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     █░░░░░░░░░░░░░░░░░░░ 7.2739%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 23. 2026-05-12 업데이트: full training tokenizer 일곱 번째 중간 진행 확인

실행 중인 2025년 STOM tick pred60 Kronos-small 전체 학습을 일곱 번째로 중간 점검했다.

확인 결과:

- stage: tokenizer running
- 이전 commit 최종 관측: step 685,000 / 4,701,721, overall 7.2846%
- 이번 1차 샘플: step 689,000 / 4,701,721, loss -0.0326, overall 7.3271%
- 이번 2차 샘플: step 690,000 / 4,701,721, loss -0.0299, overall 7.3377%
- 문서 작성 직전: step 691,000 / 4,701,721, loss -0.0238
- tokenizer stage progress: 14.6967%
- overall progress: 7.3484%
- samples/sec: 약 72.62
- checkpoint/model/predictor file count: 0
- predictor 전환: 아직 전
- GPU: NVIDIA GeForce RTX 4080 SUPER, 41, 3082, 16376, [N/A], 42

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
현재 점검 완료율:     ████████████████████ 100%  일곱 번째 progress/log/GPU/checkpoint 확인 완료
실제 학습 진행률:     █░░░░░░░░░░░░░░░░░░░ 7.3484%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 24. 2026-05-12 업데이트: 학습 대시보드 자동 새로고침/전체 웹 통합 계획

Autopilot `ralplan` 단계로 다음 개발 목표를 확정했다.

목표:

- `/training`에서 학습 running 중 설정 가능한 간격으로 자동 새로고침
- `/`, `/stom`에서도 현재 학습 요약과 `/training` 링크 제공
- 학습 프로세스는 종료하지 않고 관측만 수행
- 구현 후 테스트와 code-review까지 진행

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
Autopilot 계획 단계: ████████████████████ 100%
구현/검증/리뷰:      ░░░░░░░░░░░░░░░░░░░░ 0%
~~~

---

## 25. 2026-05-12 업데이트: 학습 대시보드 자동 새로고침/전체 웹 통합 구현

Autopilot `ralph` 단계로 웹 통합 구현을 완료했다.

구현 완료:

- `/training`: 자동 새로고침 ON/OFF, 설정 가능한 초 단위 interval, localStorage 저장
- `/`: 실시간 학습 상태 요약 카드와 `/training` 링크
- `/stom`: 예측/성과 대시보드 상단 학습 상태 strip과 `/training` 링크
- Flask: `refresh_interval` query parameter와 min/max clamp
- 테스트: `tests/test_training_monitor.py`, `tests/test_training_progress.py` 통과

검증:

~~~text
python -m pytest tests/test_training_monitor.py tests/test_training_progress.py -q
8 passed
~~~

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
Autopilot 구현 단계: ████████████████████ 100%
검증 단계:           ████████████████████ 100%
code-review 단계:    ░░░░░░░░░░░░░░░░░░░░ 0%
~~~

---

## 26. 2026-05-12 업데이트: 학습 대시보드 자동 새로고침 코드 리뷰 완료

Autopilot `code-review` 단계에서 변경 diff를 검토했다.

리뷰 결과:

- Recommendation: APPROVE
- Architectural status: CLEAR
- Critical/High/Medium/Low: 0

리뷰 중 보완:

- `/training` 자동 갱신 렌더링에서 log/API/GPU 값이 innerHTML에 들어가는 경로를 HTML escape 처리
- badge CSS class는 안전한 문자만 사용하도록 제한

검증:

~~~text
python -m pytest tests/test_training_monitor.py tests/test_training_progress.py -q
8 passed
~~~

현재 단계 판단:

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
Autopilot 계획 단계: ████████████████████ 100%
Autopilot 구현 단계: ████████████████████ 100%
Autopilot 리뷰 단계: ████████████████████ 100%
~~~

---

## 27. 2026-05-12 업데이트: STOM 전체 학습 여덟 번째 중간 진행 점검

`$ralph` 다음 단계로 STOM 2025 pred60 Kronos-small 전체 학습이 실제 진행 중인지 재검증했다.

확인 결과:

- 현재 stage: `tokenizer`
- status: `running`
- step: `920000 / 4701721`
- tokenizer 진행률: 19.5673%
- 전체 both-stage 진행률: 9.7837%
- 최신 로그: `[Rank 0, Epoch 1/1, Step 920000/4701721] LR 0.000186, Loss: -0.0307`
- 70초 재확인: `918000 -> 919000` step 증가 확인
- GPU: `NVIDIA GeForce RTX 4080 SUPER`, util 약 42%, VRAM 약 3130 / 16376 MiB, temp 약 42C
- checkpoint/model weight: 아직 0개
- predictor 전환: 아직 전
- 대시보드: `/training`, `/`, `/stom` 자동 갱신 UI 응답 확인

현재 판단:

~~~text
개발/대시보드 준비       [███████████████████░] 97.00%
tokenizer 학습            [████░░░░░░░░░░░░░░░░] 19.57%
전체 both-stage 학습       [██░░░░░░░░░░░░░░░░░░] 9.78%
predictor 학습             [░░░░░░░░░░░░░░░░░░░░] 0.00%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 28. 2026-05-12 업데이트: STOM 전체 학습 아홉 번째 중간 진행 점검

`$ralph` 다음 단계로 STOM 2025 pred60 Kronos-small 전체 학습 진행 상태를 다시 점검했다.

확인 결과:

- 현재 stage: `tokenizer`
- status: `running`
- step: `1,020,000 / 4,701,721`
- tokenizer 진행률: 21.6942%
- 전체 both-stage 진행률: 10.8471%
- 최신 로그: `[Rank 0, Epoch 1/1, Step 1020000/4701721] LR 0.000182, Loss: -0.0311`
- checkpoint 08 대비 증가량: `+98,000 step`
- 75초 재확인: `1,019,000 -> 1,020,000` step 증가 확인
- GPU: `NVIDIA GeForce RTX 4080 SUPER`, util 약 40%, VRAM 약 3241 / 16376 MiB, temp 약 42C
- checkpoint/model weight: 아직 0개
- predictor 전환: 아직 전
- 대시보드: `/training`, `/`, `/stom` 자동 갱신 UI 응답 확인

현재 판단:

~~~text
개발/대시보드 준비       [███████████████████░] 97.00%
tokenizer 학습            [████░░░░░░░░░░░░░░░░] 21.69%
전체 both-stage 학습       [██░░░░░░░░░░░░░░░░░░] 10.85%
predictor 학습             [░░░░░░░░░░░░░░░░░░░░] 0.00%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 29. 2026-05-12 업데이트: STOM 전체 학습 열 번째 중간 진행 점검

`$ralph` 다음 단계로 STOM 2025 pred60 Kronos-small 전체 학습 진행 상태를 다시 점검했다.

확인 결과:

- 현재 stage: `tokenizer`
- status: `running`
- step: `1,079,000 / 4,701,721`
- tokenizer 진행률: 22.9490%
- 전체 both-stage 진행률: 11.4745%
- 최신 로그: `[Rank 0, Epoch 1/1, Step 1079000/4701721] LR 0.000180, Loss: -0.0291`
- checkpoint 09 대비 증가량: `+59,000 step`
- 75초 재확인: `1,078,000 -> 1,079,000` step 증가 확인
- GPU: `NVIDIA GeForce RTX 4080 SUPER`, util 약 35%, VRAM 약 3316 / 16376 MiB, temp 약 50C
- checkpoint/model weight: 아직 0개
- predictor 전환: 아직 전
- 대시보드: `/training`, `/`, `/stom` 자동 갱신 UI 응답 확인

현재 판단:

~~~text
개발/대시보드 준비       [███████████████████░] 97.00%
tokenizer 학습            [█████░░░░░░░░░░░░░░░] 22.95%
전체 both-stage 학습       [██░░░░░░░░░░░░░░░░░░] 11.47%
predictor 학습             [░░░░░░░░░░░░░░░░░░░░] 0.00%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 30. 2026-05-12 업데이트: STOM 전체 학습 열한 번째 중간 진행 점검

`$ralph` 다음 단계로 STOM 2025 pred60 Kronos-small 전체 학습 진행 상태를 다시 점검했다.

확인 결과:

- 현재 stage: `tokenizer`
- status: `running`
- step: `1,136,000 / 4,701,721`
- tokenizer 진행률: 24.1614%
- 전체 both-stage 진행률: 12.0807%
- 최신 로그: `[Rank 0, Epoch 1/1, Step 1136000/4701721] LR 0.000177, Loss: -0.0311`
- checkpoint 10 대비 증가량: `+57,000 step`
- 75초 재확인: `1,134,000 -> 1,136,000` step 증가 확인
- GPU: `NVIDIA GeForce RTX 4080 SUPER`, util 약 43%, VRAM 약 3294 / 16376 MiB, temp 약 50C
- checkpoint/model weight: 아직 0개
- predictor 전환: 아직 전
- 대시보드: `/training`, `/`, `/stom` 자동 갱신 UI 응답 확인

현재 판단:

~~~text
개발/대시보드 준비       [███████████████████░] 97.00%
tokenizer 학습            [█████░░░░░░░░░░░░░░░] 24.16%
전체 both-stage 학습       [██░░░░░░░░░░░░░░░░░░] 12.08%
predictor 학습             [░░░░░░░░░░░░░░░░░░░░] 0.00%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 2026-05-12 기준 STOM tick pred60 Kronos-small 전체 학습 tokenizer 단계의 다음 중간 진행률을 다시 점검하고, checkpoint 생성 여부와 predictor 전환 여부를 확인한 뒤 문서와 commit으로 남기세요.
~~~

---

## 31. 2026-05-12 업데이트: 학습 유지 상태의 웹 대시보드 병렬 개선 계획

`$ralplan` 단계로 현재 STOM full training은 계속 유지하면서 웹 대시보드/프론트엔드 통합 개선을 병렬로 진행하기 위한 안전 계획을 수립했다.

현재 live 기준선:

- status: `running`
- stage: `tokenizer`
- step: `1,168,000 / 4,701,721`
- tokenizer 진행률: 24.8420%
- 전체 both-stage 진행률: 12.4210%
- checkpoint/predictor: 아직 전

채택한 방향:

- running 학습, DB, CUDA/PyTorch, 현재 run output은 수정 금지
- `/training`, `/`, `/stom` 웹/API는 읽기 전용으로 개선
- checkpoint/predictor 전에는 예측 성과를 표시하지 않고 “학습 중/성과 대기”로 표시
- 단계별 테스트 후 Lore commit

진행률:

~~~text
안전 계획 수립                  [████████████████████] 100%
학습 모니터링 체계              [████████████████████] 100%
웹 기본 통합                    [███████████████████░] 95%
프론트엔드 고도화               [████████░░░░░░░░░░░░] 40%
read-only artifacts API          [░░░░░░░░░░░░░░░░░░░░] 0%
진행률 히스토리 시각화           [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률          [██░░░░░░░░░░░░░░░░░░] 12.42%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획에 따라 1단계만 구현하세요. 목표는 /training, /, /stom의 학습 상태 UI를 공통 기준으로 정리하고 checkpoint/predictor 전환 전 성과 오해를 막는 표시를 추가하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고, live HTTP 확인 후 Lore commit으로 남기세요.
~~~

---

## 32. 2026-05-12 업데이트: 학습 유지 웹 대시보드 개선 1단계 구현

`$ralph` 단계로 현재 STOM full training은 계속 유지하면서 `/training`, `/`, `/stom`의 학습 상태 UI를 공통 readiness 기준으로 정리했다.

구현 완료:

- `/api/training/status`에 공통 `readiness` 필드 추가
- tokenizer 단계에서는 `성과 대기: tokenizer 학습 중`으로 표시
- predictor 진행 중/완료 상태를 공통 정책으로 분리
- `/training`: `예측 성과 준비 상태` 카드 추가
- `/`: 상단 학습 상태 카드에 `성과 상태`와 안내 메시지 추가
- `/stom`: 상단 strip에 `성과 상태`와 predictor 전 성과 대기 안내 추가

검증:

~~~text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
9 passed in 1.70s

C:\Python\64\Python3119\python.exe -m compileall webui
통과

Live HTTP:
/training?refresh_interval=10: trainingReadinessCard 확인
/?refresh_interval=10: trainingInlineReadiness 확인
/stom?refresh_interval=10: stomTrainingReadiness 확인
~~~

현재 live 학습 상태:

~~~text
status: running
stage: tokenizer
step: 1,177,000 / 4,701,721
tokenizer 진행률: 25.0334%
전체 both-stage 진행률: 12.5167%
readiness: 성과 대기: tokenizer 학습 중
~~~

진행률:

~~~text
1단계 공통 readiness UI/API       [████████████████████] 100%
학습 모니터링 체계                [████████████████████] 100%
웹 기본 통합                      [████████████████████] 100%
프론트엔드 고도화                 [██████████░░░░░░░░░░] 50%
read-only artifacts API            [░░░░░░░░░░░░░░░░░░░░] 0%
진행률 히스토리 시각화             [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률            [███░░░░░░░░░░░░░░░░░] 12.52%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 2단계를 구현하세요. 목표는 checkpoint/predictor/weight artifact 상태를 읽기 전용 API로 노출하고, /training과 /stom에서 checkpoint 생성 여부를 명확히 표시하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
~~~

---

## 33. 2026-05-12 업데이트: 학습 유지 웹 대시보드 개선 2단계 구현

`$ralph` 단계로 현재 STOM full training은 계속 유지하면서 checkpoint/predictor/model weight artifact 상태를 읽기 전용 API와 웹 UI로 표시했다.

구현 완료:

- `/api/training/artifacts` 추가
- tokenizer/predictor checkpoint directory와 weight 파일 수 확인
- `/training`: `Checkpoint / Predictor Artifact` 카드 추가
- `/stom`: 상단 학습 strip 아래 artifact 상태 문구 추가
- checkpoint/predictor 전에는 `checkpoint 대기`로 명확히 표시

검증:

~~~text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
10 passed in 2.17s

C:\Python\64\Python3119\python.exe -m compileall webui
통과

Live HTTP:
/api/training/status: readiness 확인
/api/training/artifacts: checkpoint 대기, weight 0개 확인
/training?refresh_interval=10: trainingArtifactCard 확인
/stom?refresh_interval=10: stomTrainingArtifacts 확인
~~~

현재 live 학습 상태:

~~~text
status: running
stage: tokenizer
step: 1,198,000 / 4,701,721
tokenizer 진행률: 25.4800%
전체 both-stage 진행률: 12.7400%
artifact: checkpoint 대기, model weight 0개, checkpoint 0개
~~~

진행률:

~~~text
1단계 공통 readiness UI/API       [████████████████████] 100%
2단계 read-only artifacts API      [████████████████████] 100%
학습 모니터링 체계                [████████████████████] 100%
웹 기본 통합                      [████████████████████] 100%
프론트엔드 고도화                 [████████████░░░░░░░░] 60%
진행률 히스토리 시각화             [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률            [███░░░░░░░░░░░░░░░░░] 12.74%
~~~

다음 권장 OMX 명령:

~~~text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 3단계를 구현하세요. 목표는 tokenizer progress JSON/log를 읽기 전용으로 사용해 /training에 간단한 진행률 히스토리 카드 또는 표를 추가하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
~~~

---

## 34. 2026-05-12 업데이트: 학습 진행률 히스토리 대시보드 구현

현재 STOM full training을 중단하지 않고 `$ralph` 단계로 `/training` 대시보드에 최근 학습 step 히스토리를 추가했습니다.

구현 완료:

- `/api/training/history` 추가
- tokenizer stdout log에서 step, total_steps, LR, loss, stage %, overall % 파싱
- `/training`에 진행률 히스토리 카드와 테이블 추가
- 자동 새로고침 시 history도 함께 갱신
- predictor처럼 아직 stdout log가 없는 명시 단계는 tokenizer log로 fallback하지 않도록 안전장치 추가

검증:

```text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
12 passed in 2.07s

C:\Python\64\Python3119\python.exe -m compileall webui
통과

Live HTTP:
/api/training/history?limit=5: point_count 5, latest_point.step 1,320,000
/api/training/history?stage=predictor&limit=5: point_count 0, no stdout log found
/training?refresh_interval=10: historyRows/historySummary/refreshIntervalSeconds 확인
```

현재 live 학습 상태:

```text
status: running
stage: tokenizer
step: 1,320,000 / 4,701,721
tokenizer 진행률: 28.0748%
전체 both-stage 진행률: 14.0374%
readiness: 성과 대기(tokenizer 학습 중, predictor 미시작)
```

진행률:

```text
1단계 공통 readiness UI/API       [██████████] 100%
2단계 read-only artifacts API      [██████████] 100%
3단계 진행률 히스토리 표시        [██████████] 100%
4단계 GPU/ETA/속도 카드 개선      [░░░░░░░░░░] 0%
5단계 /stom 성과 준비 상태 연결   [░░░░░░░░░░] 0%
6단계 최종 code-review 문서       [░░░░░░░░░░] 0%
프론트엔드 고도화 전체            [██████░░░░] 60%
학습 산출물 전체 진행률           [█░░░░░░░░░] 14.04%
```

다음 권장 OMX 명령:

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 4단계를 구현하세요. 목표는 /training의 GPU/ETA/속도 카드를 개선해 samples/sec, ETA, GPU util/VRAM/온도/전력 상태를 더 명확히 표시하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```

---

## 35. 2026-05-12 업데이트: GPU/ETA/속도 카드 개선

현재 STOM full training을 중단하지 않고 `$ralph` 단계로 `/training` 대시보드의 GPU/ETA/속도 표시를 개선했습니다.

구현 완료:

- `/training`에 `학습 속도 / ETA` 카드 추가
- 현재 단계, samples/sec, 경과 시간, 남은 시간, 예상 완료 시각, 최근 loss 표시
- `/api/training/gpu` summary 확장
- 평균 GPU Util, 총 VRAM 사용률, 총 전력 제한, power draw 실측 가능 여부 표시
- power draw 실측이 불가한 환경에서는 `실측 불가`로 명확히 표시
- GPU 테이블에 VRAM %, Power, Limit, Temp 컬럼 확장

검증:

```text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
13 passed in 1.94s

C:\Python\64\Python3119\python.exe -m compileall webui
통과

Live HTTP:
/api/training/gpu: available true, avg util 39.0%, VRAM 19.61%, power limit 320W
/api/training/status: tokenizer running, step 1,329,000, overall 14.1331%
/training?refresh_interval=10: runtimeSummaryCard/gpuSummaryMetrics 확인
```

현재 live 학습 상태:

```text
status: running
stage: tokenizer
step: 1,329,000 / 4,701,721
tokenizer 진행률: 28.2662%
전체 both-stage 진행률: 14.1331%
samples/sec: 약 65.37
readiness: 성과 대기(tokenizer 학습 중, predictor 미시작)
```

진행률:

```text
1단계 공통 readiness UI/API       [██████████] 100%
2단계 read-only artifacts API      [██████████] 100%
3단계 진행률 히스토리 표시        [██████████] 100%
4단계 GPU/ETA/속도 카드 개선      [██████████] 100%
5단계 /stom 성과 준비 상태 연결   [░░░░░░░░░░] 0%
6단계 최종 code-review 문서       [░░░░░░░░░░] 0%
프론트엔드 고도화 전체            [████████░░] 80%
학습 산출물 전체 진행률           [█░░░░░░░░░] 14.13%
```

다음 권장 OMX 명령:

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 5단계를 구현하세요. 목표는 /stom 성과 대시보드 상단에도 predictor 미시작/성과 대기/학습 진행 상태와 artifact readiness를 더 명확히 연결해, predictor 완료 전에는 예측 성과를 오해하지 않도록 하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```


---

## 36. 2026-05-12 ????: /stom ?? ?? ?? ??

?? STOM full training? ???? ?? `$ralph` ??? `/stom` ?? ???? ??? readiness/artifact gate? ??????.

?? ??:

- `/stom` ??? `?? ?? Gate`, `Predictor`, `Checkpoint`, `?? / ETA` ?? ??
- predictor/checkpoint ?? ??? `LOCKED: predictor/checkpoint ?? ? ?? ?? ??` ??
- `/api/training/status`? readiness ??? `/stom` ?? ??? ?? ??
- `/api/training/artifacts`? tokenizer/predictor checkpoint ??? predictor started ?? ??
- `/stom` route template marker ?? ??? ??

??:

```text
C:\Python4\Python3119\python.exe -m pytest tests	est_training_monitor.py tests	est_training_progress.py -q
13 passed in 1.99s

C:\Python4\Python3119\python.exe -m compileall webui
??

Live HTTP:
/stom?refresh_interval=10: stomPerformanceGate/stomPredictorGate/stomCheckpointGate/stomRuntimeGate ??
/api/training/status: tokenizer running, step 1,383,000, overall 14.7074%, performance_ready false
/api/training/artifacts: checkpoint 0?, predictor_started false
```

?? live ?? ??:

```text
status: running
stage: tokenizer
step: 1,383,000 / 4,701,721
tokenizer ???: 29.4148%
?? both-stage ???: 14.7074%
samples/sec: ? 65.05
readiness: ?? ??(tokenizer ?? ?, predictor ???)
```

???:

```text
1?? ?? readiness UI/API       [??????????] 100%
2?? read-only artifacts API      [??????????] 100%
3?? ??? ???? ??        [??????????] 100%
4?? GPU/ETA/?? ?? ??      [??????????] 100%
5?? /stom ?? ?? ?? ??   [??????????] 100%
6?? ?? code-review ??       [??????????] 0%
????? ??? ??            [??????????] 90%
?? ??? ?? ???           [??????????] 14.71%
```

?? ?? OMX ??:

```text
$code-review ???? STOM full training? ???? ?? ??? ???? read-only ?? ??? ?????. ??? docs/stom_dashboard_safe_parallel_improvement_plan.md? 1~5??? ?? commit???. ??? predictor ?? ? ?? ?? ??, /training ? /stom readiness/artifact/ETA/GPU ?? ???, ??? ???, ?? ??? ???? ?? review ??? Lore commit? ??? ????.
```


---

## 37. 2026-05-12 ????: ?? code-review ?? ??

`$code-review` ??? STOM full training ???? read-only ?? 1~5??? ?? ??????.

??:

```text
Recommendation: APPROVE
Architectural Status: CLEAR
CRITICAL: 0
HIGH: 0
MEDIUM: 0
LOW: 3? ?? ??
```

??:

```text
C:\Python4\Python3119\python.exe -m pytest tests	est_training_monitor.py tests	est_training_progress.py -q
13 passed in 2.22s

C:\Python4\Python3119\python.exe -m compileall webui
??

git diff --check aed6967..HEAD
??

Live HTTP:
/training?refresh_interval=10: readiness/artifact/runtime/gpu/history marker ??
/stom?refresh_interval=10: performance/predictor/checkpoint/runtime gate ??
/?refresh_interval=10: inline training panel ??
/api/training/status/history/artifacts/gpu ??
```

?? live ?? ??:

```text
status: running
stage: tokenizer
step: 1,389,000 / 4,701,721
tokenizer ???: 29.5424%
?? both-stage ???: 14.7712%
samples/sec: ? 65.00
readiness: ?? ??(tokenizer ?? ?, predictor ???)
checkpoint/model weight: 0?
```

???:

```text
1?? ?? readiness UI/API       [??????????] 100%
2?? read-only artifacts API      [??????????] 100%
3?? ??? ???? ??        [??????????] 100%
4?? GPU/ETA/?? ?? ??      [??????????] 100%
5?? /stom ?? ?? ?? ??   [??????????] 100%
6?? ?? code-review ??       [??????????] 100%
????? ??? ??            [??????????] 100%
?? ??? ?? ???           [??????????] 14.77%
```

?? ?? OMX ??:

```text
$ralph ?? ?? ?? STOM full training? ???? ??, ????? /api/training/status, /api/training/history, /api/training/artifacts? ??? tokenizer ??? predictor ?? ??? ???????. predictor? ???? /training ? /stom gate? training ??? ????? live HTTP? ????, predictor checkpoint? ??? ??? ??? vs ??? ?? ???? ?? ??? ?????.
```


---

## 38. 2026-05-12 ????: ?? ?? ???? ?????

?? code-review ?? ?? STOM full training? read-only? ?? ??????.

?? live ??:

```text
run: stom_1s_grid_pred60_2025_full_small
status: running
stage: tokenizer
step: 1,442,000 / 4,701,721
tokenizer ???: 30.6696%
?? both-stage ???: 15.3348%
samples/sec: ? 65.07
ETA: ? 200,393?
predictor_started: false
checkpoint/model weight: 0?
```

??:

```text
?? ?? ??: ?? ??
??: predictor ???, checkpoint/model weight ??
?? ? ?: ???? ?? ? predictor ?? ?? ??
```

?? ?? OMX ??:

```text
$ralph ?? ?? ?? STOM full training? ???? ??, 1~2?? ? ?? tokenizer ???? ?? ?? ? /api/training/status, /api/training/history, /api/training/artifacts? ?? ?????. predictor? ?? ???? ???? ???? ?????? ???, predictor? ?????? /training ? /stom gate? training ??? ????? live HTTP? ??? ? commit?? ?????.
```
