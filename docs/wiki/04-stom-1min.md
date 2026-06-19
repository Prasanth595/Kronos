# STOM 1-min (분봉) 데이터 활용법

> **이 문서는 사용자가 직접 채워나가는 살아있는 노하우 문서입니다.**

## 1-min 데이터란

1분 단위로 OHLCV(시가/고가/저가/종가/거래량) 가 집계된 시계열. 주식 시장 일중 데이터의 가장 흔한 단위.

## 데이터 위치 / 스키마

- **DB**: `_database/` 의 STOM SQLite (정확한 테이블명은 사용자 채움)
- **컬럼**: open, high, low, close, volume + timestamp
- **호환 테이블 수**: 2,425개 (`/api/stom/summary` 의 `compatible_stock_table_count`)
- **eligible 그룹 수**: 73,650개 (학습 가능 그룹)
- **추정 샘플 수**: 약 95.9M

## STOM 데이터의 한국어 컬럼명

`/api/stom/summary` 의 `warnings`:
> close column not found; using 종가 as close.

즉 일부 테이블은 영문 컬럼명(`close`) 이 없고 한국어(`종가`) 만 있음. 학습 코드는 이를 자동 매핑하지만 직접 SQL 조회 시 주의.

## 활용 패턴 (사용자 작성 영역)

### A. 일중 추세 학습
- (사용자 채울 자리)

### B. 갭(GAP) 처리 — 장 마감/개장 사이
- (사용자 채울 자리: 09:00 시작 / 15:30 마감 사이의 갭을 어떻게 다루는지)

### C. 거래량 가중 (Volume-weighted)
- (사용자 채울 자리)

### D. 학습 윈도우 구성
- lookback 400 + pred_len 120 = 520 분 ≈ 8.7 시간 (장 시간 6.5h 보다 길어 인접 일자 포함)
- 또는 lookback 200 + pred_len 60 = 260 분 ≈ 4.3 시간 (장중 일부)

## 시행착오 (사용자 작성 영역)

### 메모리 OOM (관련: 학습 실패 commit 7742cb8)
- **증상**: validation 단계에서 GPU VRAM 16 GiB 초과 → OOM crash
- **원인**: validation batch size 가 큼
- **시도한 것**: (사용자 채울 자리)
- **해결**: (사용자 채울 자리)

## 권장 하이퍼파라미터 (사용자 작성 영역)

| 항목 | 값 | 사유 |
|---|---|---|
| lookback | (예: 400) | |
| pred_len | (예: 60 / 120) | |
| batch_size (train) | (사용자 채울 자리) | |
| batch_size (val) | (OOM 회피 위해 train 보다 작게) | |
| learning_rate | (사용자 채울 자리) | |

## 관련 문서

- [03-stom-1tick](03-stom-1tick) — 1틱 비교
- [05-stom-1day](05-stom-1day) — 1일봉 비교
- [07-trial-and-error](07-trial-and-error) — 시행착오 기록

---

*이 문서는 초안 골격입니다. 사용자 본인의 1-min 활용 경험을 직접 채워주세요.*
