# STOM tick Kronos 학습용 GPU 대여/상위 모델 검토 보고서

작성일: 2026-05-10
대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`

## 1. 결론 요약

핵심 목적은 **STOM tick 전체/연도별 데이터를 더 많이 학습하여 Kronos 예측 가능성이 실제로 상승하는지 검증**하는 것이다. 현재 로컬 4080 Super에서 완료한 공식 200k 학습은 전체 pred60 train 가능량 대비 약 0.27% 수준이므로, 연구 관점에서는 더 큰 학습 실험을 해볼 가치가 있다. 다만 **더 큰 GPU/더 큰 모델이 예측률 상승을 보장하지는 않는다.** 반드시 동일 holdout, random/persistence 비교, 비용 차감 Top-K backtest, rolling validation으로 검증해야 한다.

권장 순서:

1. **클라우드 RTX 5090 1대**에서 2025년 Kronos-small 전체 학습을 먼저 실행한다.
   - 예상 시간: 약 3.7일
   - 예상 비용: 약 $60~$87, provider/가격에 따라 변동
2. 2025년 holdout/test 및 2026년 데이터로 성과를 비교한다.
3. 성과가 개선되면 **Kronos-base + RTX 5090/H100/H200** 비교 실험으로 넘어간다.
4. base에서도 개선이 확인될 때만 전체 2022~2026 학습 또는 B200/H200 장기 학습을 검토한다.

가장 비용 대비 좋은 1차 선택지는 **RTX 5090 cloud**다. H100/H200/B200은 더 빠르지만, 현재 코드가 FP8/AMP/DDP를 충분히 활용하지 못하므로 가격 대비 효율이 항상 좋지는 않다.

---

## 2. 현재 로컬 실측 기준

현재 완료된 공식 학습:

- 모델: `NeoQuasar/Kronos-small`
- tokenizer: `NeoQuasar/Kronos-Tokenizer-base`에서 시작해 STOM용 200k tokenizer fine-tune
- predictor: fine-tuned tokenizer를 사용해 `NeoQuasar/Kronos-small` predictor 200k fine-tune
- GPU: RTX 4080 Super 16GB
- batch size: 4
- num_workers: 0
- sample mode: `full_sequential`
- lookback: 300초
- pred: 60초

실측 시간:

| 단계 | samples | 시간 |
|---|---:|---:|
| tokenizer | train 200k + val 40k | 3,211초, 약 53.5분 |
| predictor | train 200k + val 40k | 4,129초, 약 68.8분 |
| 합계 | 240k | 7,340초, 약 2.04시간 |

이 보고서의 시간 계산은 위 실측치를 기준으로 선형 환산했다. 실제 클라우드에서는 CPU, 디스크, 데이터로더, PyTorch/CUDA 버전, batch size 조정에 따라 달라진다.

---

## 3. STOM tick DB 직접 분석 결과

분석 기준:

- DB: `_database/stock_tick_back.db`
- read-only 스캔
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

세부 산출물:

- `.omx/analysis/stom_yearly_db_sample_report.json`
- `.omx/analysis/stom_yearly_db_split_sample_report.json`

---

## 4. Kronos 모델별 의미

로컬 README 기준 모델 구성:

| 모델 | 파라미터 | context | 상태 | 목적 |
|---|---:|---:|---|---|
| Kronos-mini | 4.1M | 2048 | 사용 가능 | 빠른 실험, 긴 context, 낮은 비용 |
| Kronos-small | 24.7M | 512 | 사용 가능 | 현재 기준 모델, 비용/속도/성능 균형 |
| Kronos-base | 102.3M | 512 | 사용 가능 | 더 높은 표현력, 충분한 데이터에서 성능 개선 검증 |
| Kronos-large | 499.2M | 512 | README상 공개 모델 없음 | 현재 즉시 실행 대상 아님 |

해석:

- **small**: 지금의 기준선이다. 1M, 5M, 2025년 학습까지는 small로 먼저 확인하는 것이 합리적이다.
- **base**: 2025년 small에서 개선 신호가 나오면 시도할 가치가 있다. 모델이 약 4.1배 크므로 학습 시간도 대략 3.5~4.5배 증가할 수 있다.
- **mini**: 빠른 사전 실험에는 좋지만 최종 예측 성능 기대치는 낮다.
- **large**: 공개/로컬 사용 가능성이 불명확하고, 현재 목표에서는 우선순위가 낮다.

---

## 5. GPU 대여 서비스 선택지

가격은 2026-05-10 웹 확인 기준이며 수시로 변동된다.

| 선택지 | 장점 | 단점 | 보고서 계산용 가격 |
|---|---|---|---:|
| RTX 5090 marketplace/cloud | 가장 비용 대비 좋음, 32GB VRAM, 2025년 small/base 실험 가능 | host 품질/중단/지역 차이, provider별 환경 편차 | $0.55~$0.99/hr |
| RunPod RTX 5090 | 접근성 좋고 템플릿/스토리지 편함 | 실제 pod 가격/가용성 변동 | 약 $0.69~$0.99/hr |
| Vast.ai RTX 5090 | 최저가 가능 | 보안/안정성/호스트 편차 큼 | 약 $0.15~$0.80/hr 범위 |
| Lambda H100/B200 | 관리형, 안정성, 빠른 datacenter GPU | 비용 높음 | H100 $3.29~$4.29/hr, B200 $6.99/hr |
| H200 | 141GB VRAM, 큰 모델/큰 batch 유리 | Kronos-small에서는 VRAM 이점이 제한적일 수 있음 | $2.25~$4.31/hr |
| B200 | 최고급, 180GB VRAM | 현재 코드가 FP8/멀티GPU 최적화를 못 쓰면 과투자 가능 | $3.40~$6.99/hr |

주의: 현재 `train_tokenizer.py`, `train_predictor.py`에는 AMP/autocast 사용 흔적이 없고, 최근 실행은 single GPU + DDP disabled였다. 따라서 H100/H200/B200의 이론 성능을 그대로 쓰지 못한다. 클라우드 고급 GPU를 제대로 쓰려면 다음 최적화가 필요하다.

- `torch.autocast`/AMP 또는 BF16 안정화
- batch size 증가
- `num_workers`, `pin_memory`, prefetch 조정
- 데이터셋 pickle/CSV를 로컬 NVMe에 배치
- 장기 학습 checkpoint/resume
- 멀티GPU를 쓸 경우 DDP 재검증

---

## 6. Kronos-small 기준 GPU별 시간/비용 계산

계산 가정:

- 로컬 4080 Super 실측을 1.0배로 둔다.
- RTX 5090은 현실값 2.2배로 추정한다.
- A100은 1.8배, H100은 3.2배, H200은 3.5배, B200은 4.5배로 보수 추정한다.
- 가격은 대표 on-demand/marketplace 값을 사용한다.

### 6.1 연도별 train+val 학습 시간/비용, Kronos-small

| 범위 | sample | 4080S 로컬 | RTX 5090 $0.69/hr | RTX 5090 $0.99/hr | H100 $3.29/hr | H200 $4.31/hr | B200 $6.99/hr |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 18,637,997 | 6.6일 | 3.0일 / $50 | 3.0일 / $71 | 2.1일 / $163 | 1.9일 / $195 | 1.5일 / $246 |
| 2023 | 24,002,988 | 8.5일 | 3.9일 / $64 | 3.9일 / $92 | 2.7일 / $210 | 2.4일 / $251 | 1.9일 / $317 |
| 2024 | 21,208,505 | 7.5일 | 3.4일 / $57 | 3.4일 / $81 | 2.3일 / $185 | 2.1일 / $222 | 1.7일 / $280 |
| 2025 | 22,694,289 | 8.0일 | 3.7일 / $60 | 3.7일 / $87 | 2.5일 / $198 | 2.3일 / $237 | 1.8일 / $300 |
| 2026 | 2,735,733 | 23.2시간 | 10.6시간 / $7 | 10.6시간 / $10 | 7.3시간 / $24 | 6.6시간 / $29 | 5.2시간 / $36 |
| 전체 official train+val | 89,656,982 | 31.7일 | 14.4일 / $239 | 14.4일 / $343 | 9.9일 / $783 | 9.1일 / $938 | 7.1일 / $1,183 |
| 전체 windows reference | 104,738,650 | 37.1일 | 16.9일 / $279 | 16.9일 / $400 | 11.6일 / $915 | 10.6일 / $1,096 | 8.2일 / $1,382 |

해석:

- **2025년 small 학습**은 RTX 5090으로 약 3.7일, 비용은 약 $60~$87 수준이다.
- **전체 official small 학습**은 RTX 5090으로 약 14.4일, 비용은 약 $239~$343 수준이다.
- H100/H200/B200은 빠르지만 비용은 RTX 5090보다 대체로 높다.

---

## 7. 2025년 기준 모델별/GPU별 시간·비용

2025년 train+val 22,694,289 sample 기준이다.

| 모델 | 4080S 로컬 | RTX 5090 $0.69/hr | H100 $3.29/hr | H200 $4.31/hr | B200 $6.99/hr |
|---|---:|---:|---:|---:|---:|
| Kronos-mini | 3.6일 | 1.6일 / $27 | 1.1일 / $89 | 1.0일 / $107 | 19.3시간 / $135 |
| Kronos-small | 8.0일 | 3.7일 / $60 | 2.5일 / $198 | 2.3일 / $237 | 1.8일 / $300 |
| Kronos-base | 30.5일 | 13.9일 / $230 | 9.5일 / $753 | 8.7일 / $902 | 6.8일 / $1,138 |
| Kronos-large, if available | 144.6일 | 65.7일 / $1,089 | 45.2일 / $3,568 | 41.3일 / $4,274 | 32.1일 / $5,391 |

해석:

- **Kronos-base 2025년 학습은 5090에서 약 14일**로 추정된다. 비용은 낮지만 중단 없이 2주간 안정 운용해야 한다.
- H100/H200/B200은 base 학습 시간을 7~10일대로 줄일 수 있지만, 비용은 수백~천 달러 수준으로 올라간다.
- large는 현재 공개/사용 가능성이 불명확하므로 계획상 제외하는 것이 맞다.

---

## 8. 예측 성능 상승 가능성 평가

현재 official 200k 결과:

- direction accuracy: 약 41.88%
- random baseline과 차이가 작음
- 25bp 비용 gate 통과 실패
- 실전 승인 불가, 연구용 기준선

더 많은 데이터/더 큰 모델이 좋아질 수 있는 이유:

1. 현재 200k는 전체 official train 가능량 대비 약 0.27%뿐이다.
2. 2025년만 해도 train+val sample이 약 2,269만으로 200k 대비 113배 수준이다.
3. 종목/날짜/장세 다양성이 늘면 단순 overfit이 줄 수 있다.
4. Kronos-base는 small보다 표현력이 높아, 충분한 데이터에서는 패턴 포착 가능성이 더 높다.

하지만 성능이 안 오를 수 있는 이유:

1. 1초봉은 microstructure noise가 매우 크다.
2. 거래대금 상위 종목 universe가 매일 바뀐다.
3. 오래된 데이터와 최신 데이터의 시장 regime이 다르다.
4. 방향 정확도 50%를 넘어도 수수료/슬리피지 후 수익성이 음수일 수 있다.
5. 큰 모델은 데이터가 충분해도 잘못된 split이나 누수/과최적화가 있으면 실전 성과가 악화될 수 있다.

따라서 목표 지표는 단순 정확도 하나가 아니라 다음이어야 한다.

| 지표 | 통과 기준 예시 |
|---|---|
| direction accuracy | random 대비 안정적 우위 |
| Top-K actual return | persistence/random보다 우위 |
| net return after cost | 0 이상 또는 baseline 대비 의미 있는 개선 |
| rolling validation | 여러 fold에서 반복 개선 |
| 2026 out-of-sample | 2025 학습 모델이 2026에도 유지되는지 확인 |

---

## 9. 추천 실행 로드맵

### Phase A: 클라우드 이전 준비, 로컬

목표: 대여 시간을 낭비하지 않도록 클라우드 실행 전 준비 완료.

1. 2025년 전용 processed dataset 생성 또는 기존 DB 기반 export command 확정
2. checkpoint/resume 기능 확인
3. 200k benchmark를 클라우드에서 30~60분 돌려 실제 samples/sec 측정
4. 비용 상한 설정

### Phase B: RTX 5090 2025-small 본학습

권장 provider:

- 1순위: RunPod/Neev/Runcrate 등 RTX 5090 on-demand
- 2순위: Vast.ai 저가 spot, 단 중단/보안/스토리지 위험 감수

목표:

- Kronos-small 2025 train+val 학습
- 예상 시간: 약 3.7일
- 예상 비용: 약 $60~$87
- 평가: 2025 test, 가능하면 2026 holdout

### Phase C: 성과 판단

통과 조건:

- official 200k보다 direction accuracy 상승
- random/persistence 대비 유의미한 우위
- Top-K net return 개선
- rolling validation에서 손실 축소가 아니라 실제 positive net에 접근

실패하면:

- 전체 학습 확대보다 feature/target/조건식/비용 구조 개선 우선

### Phase D: Kronos-base 비교

조건: Phase B에서 개선 확인 시.

- RTX 5090: 약 14일, $230~$330
- H100/H200: 약 9일 전후, $750~$900
- B200: 약 7일, $1,100 이상

목표:

- small 대비 base가 성능을 높이는지 동일 test에서 비교

### Phase E: 전체 학습

조건: 2025-small/base에서 out-of-sample 우위 확인 시.

- RTX 5090 small 전체: 약 14~17일, $240~$400
- H100/H200 small 전체: 약 9~12일, $780~$1,100
- B200 small 전체: 약 7~8일, $1,180~$1,380
- base 전체는 RTX 5090 기준 약 55일 이상 가능성이 있어 우선순위 낮음

---

## 10. 데이터/보안/운영 리스크

클라우드 대여 시 주의사항:

1. DB 원본 `stock_tick_back.db`는 약 29.7GB다. 업로드/다운로드 시간이 별도로 든다.
2. 가능하면 원본 DB 대신 2025년 processed dataset만 업로드한다.
3. Vast.ai 같은 marketplace는 저렴하지만 host 신뢰/중단 위험이 있다.
4. 민감한 전략/데이터라면 managed provider 또는 encrypted volume을 사용한다.
5. spot instance는 중단 가능성이 있어 checkpoint를 자주 저장해야 한다.
6. 장기 학습은 WandB/Comet 없이도 로컬 JSON 로그와 checkpoint를 주기적으로 외부 저장소에 복사해야 한다.

---

## 11. 최종 선택지

| 선택지 | 목적 | 권장도 |
|---|---|---:|
| 로컬 4080S로 2025-small | 비용 0, 단 8일 소요 | 중 |
| RTX 5090 대여로 2025-small | 가장 합리적인 첫 본학습 | 매우 높음 |
| RTX 5090 대여로 2025-base | small 개선 후 비교 | 높음 |
| H100/H200으로 2025-base | 시간 단축, 비용 증가 | 중상 |
| B200으로 small/base | 빠르지만 현재 코드 최적화 전에는 과투자 가능 | 중 |
| 전체 데이터를 바로 base로 학습 | 비용/시간/검증 리스크 큼 | 낮음 |

최종 권장:

```text
1차: RTX 5090에서 2025년 Kronos-small 학습
2차: 2025 test + 2026 holdout 검증
3차: 개선 확인 시 Kronos-base 비교
4차: base도 개선되면 전체 학습 검토
```

이 순서가 비용 대비 가장 안전하고, “학습량 증가가 예측 가능성 상승으로 이어지는가”를 가장 빠르게 검증할 수 있다.

---

## 12. 참고 출처

- NVIDIA RTX 5090 공식 사양: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/
- NVIDIA H100 공식 설명: https://www.nvidia.com/en-us/data-center/h100/
- NVIDIA H200 공식 설명: https://www.nvidia.com/en-us/data-center/h200/
- RTX 4080 Super 사양 참고: https://www.techspot.com/specs/gpu/290834-nvidia-geforce-rtx-4080-super.html
- Lambda GPU Cloud pricing: https://lambda.ai/pricing
- RunPod pricing: https://www.runpod.io/pricing
- DeployBase RTX 5090 cloud pricing overview: https://deploybase.ai/articles/rtx-5090-cloud
- gpus.io RTX 5090 price comparison: https://gpus.io/en/gpus/rtx5090
- Runcrate RTX 5090 pricing/spec overview: https://www.runcrate.ai/pricing/gpu/rtx-5090
- NeevCloud RTX 5090 pricing: https://www.neevcloud.com/nvidia-rtx-5090.php
