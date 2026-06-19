# STOM tick 학습 범위 및 external trading-program 제외 상태

작성일: 2026-05-08

## 1. external trading-program 연동 상태

external trading-program 전용 연동은 현재 범위에서 제거/제외한다.

현재 유지하는 것은 다음뿐이다.

- STOM 대시보드 내부 검증용 Kronos score 표시
- CSV/JSON score export
- 예측값/실제값/Top-K/filter-search/rolling-validation 확인

현재 제거/제외한 것은 다음이다.

- `external trading-program repository` repository 직접 수정
- external trading-program import 예시 구현
- external trading-program 실전 추천 로직 연결
- external trading-program 전용 adapter라는 문구

따라서 앞으로 이 프로젝트의 현재 목표는 **STOM tick → Kronos 학습/평가/대시보드 검증**이며, 외부 프로그램 연동은 하지 않는다.

## 2. STOM tick 전체 학습 여부

결론부터 말하면 다음과 같다.

```text
전체 DB를 학습 가능한 dataset으로 변환: 완료
전체 DB 기반 학습 루프 연결: 완료
전체 가능한 window를 빠짐없이 모두 학습: 아직 아님
```

## 3. 완료된 전체 데이터 작업

`stock_tick_back.db`의 전체 주식 테이블을 대상으로 1초봉 QlibDataset pickle을 생성했다.

| 항목 | pred30 | pred60 |
| --- | ---: | ---: |
| stock table | 2,425 | 2,425 |
| 제외 table | 2 (`moneytop`, `stockinfo`) | 2 (`moneytop`, `stockinfo`) |
| export group | 73,900 | 73,900 |
| export row | 131,470,857 | 131,470,857 |
| session split overlap | 0 | 0 |

즉, **모든 주식 tick table의 OHLCV를 Kronos fine-tuning에 사용할 수 있는 형태로 만드는 작업은 완료**했다.

## 4. 실제 학습에 사용한 범위

현재 실제 fine-tuning은 전체 dataset을 연결했지만, 시간/검증 비용 때문에 budgeted sample로 실행했다.

| 항목 | pred30 | pred60 |
| --- | ---: | ---: |
| possible train samples | 75,277,195 | 73,718,875 |
| possible val samples | 16,275,307 | 15,938,107 |
| 실제 사용 train samples | 20,000 | 20,000 |
| 실제 사용 val samples | 4,000 | 4,000 |
| best val loss | 2.1549 | 2.1302 |
| 학습 시간 | 약 551초 | 약 549초 |

따라서 `STOM tick 전체를 모두 학습했느냐`에 대한 정확한 답은 다음이다.

```text
아니오. 전체 DB를 학습 가능한 데이터셋으로 만들고, 그 전체 데이터셋을 학습 루프에 연결한 뒤 budgeted sample 학습을 수행했다.
하지만 7천만 개 이상의 가능한 train window 전체를 전량 epoch 학습한 것은 아니다.
```

## 5. 왜 아직 전체 window 전량 학습이 아닌가

현재 workstation은 3990X + RTX 4080 SUPER로 학습 가능하지만, 가능한 window가 horizon별 7천만 개 이상이다.
이를 모두 여러 epoch 학습하면 장시간이 필요하고, 먼저 다음 검증이 필요하다.

1. 현재 조건식이 큰 walk-forward에서도 유지되는지 확인
2. random/persistence baseline 대비 우위가 반복되는지 확인
3. 비용 후 net return이 양수로 전환되는지 확인
4. 그 이후 full/bigger training budget을 늘릴지 결정

## 6. 다음 권장 단계

다음은 학습량을 늘리기 전에 평가 표본을 먼저 키우는 것이 맞다.

```text
pred60 checkpoint
max_sessions 100
max_asofs 5
max_symbols 50
large walk-forward
rolling filter validation 재실행
```

이 결과가 좋아야 train sample을 20,000에서 200,000, 1,000,000 이상으로 확대하는 것이 합리적이다.

## 7. 2026-05-09 staged full-training 계획 반영

전체 window 전량 학습은 `docs/stom_1s_staged_full_training_plan.md`에 단계형 로드맵으로 반영했다.

현재 실행 순서는 다음과 같다.

```text
budget_20k 완료
→ expand_200k
→ expand_1m
→ expand_5m
→ full_window 후보
```

`finetune/run_stom_1s_finetune.py`에는 `--sample-stage` 옵션을 추가해 각 단계의 train/val sample budget이 실행 manifest에 명확히 남도록 한다.

예시:

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_200k `
  --output-root finetune\outputs
```

단, 아직 바로 전량 학습으로 가지 않는다. 먼저 pred60 대형 walk-forward와 rolling validation에서 baseline 대비 개선이 유지되는지 확인한 뒤 `expand_200k`부터 실행한다.
