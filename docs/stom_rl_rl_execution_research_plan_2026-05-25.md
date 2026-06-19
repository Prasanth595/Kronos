# STOM RL 실행 연구 계획 — DB 변수 기반 RL vs 조건식 생성 판단

작성일: 2026-05-25
관련 문서:
- `docs/stom_rl_portfolio_design_handoff_2026-05-25.md`
- `.omx/plans/ralplan-stom-rl-portfolio-page1-6.md`

## 1. 결론

현재 단계에서 강화학습을 진행하는 올바른 방향은 다음이다.

> 조건식을 강화학습이 직접 생성하게 하지 않는다.
> STOM DB 변수와 파생 feature를 RL state로 넣고, 조건식은 후보 종목을 줄이는 screener/filter로 사용한다.

즉, 초기 실전 구조는 다음처럼 분리한다.

```text
STOM DB 변수/feature
  -> 조건식 screener로 후보 top-K 생성
  -> PortfolioEnv가 후보/보유/현금/NAV 상태 구성
  -> RL agent가 매수/매도/보유/사이징을 학습
  -> walk-forward + paper replay로 검증
```

## 2. 왜 조건식 생성과 RL을 동시에 하지 않는가

| 항목 | 판단 | 이유 |
|---|---|---|
| DB 변수 기반 RL | 권장 | 가격, 수급, 호가, 체결강도, 포트폴리오 상태를 관측값으로 두고 행동을 학습하는 일반적 구조 |
| 조건식 후보 필터 + RL 의사결정 | 권장 | 수천 종목 행동공간을 top-K 후보로 줄여 학습 안정성과 검증 가능성을 높임 |
| RL이 조건식을 동시에 생성 | 초기 단계 비권장 | 조건 변수/임계값/AND/OR 조합으로 행동공간이 폭발하고 과최적화·룩어헤드·데이터마이닝 위험이 큼 |
| 조건식 자동 생성 | 후속 연구 가능 | RL 본체와 분리해 walk-forward로 고정 조건식 세트를 검증한 뒤 별도 최적화 문제로 다뤄야 함 |

핵심 원칙:

1. 조건식은 초기에는 **universe/candidate filter**다.
2. RL은 **후보 중 선택, 비중, 청산, 보유시간**을 학습한다.
3. 조건식 자체를 자동 생성하는 문제는 성능 검증 후 별도 Page로 분리한다.

## 3. 현재까지 연구/문서화 충분성 평가

| 영역 | 충분성 | 현재 상태 | 남은 연구 |
|---|---:|---|---|
| 단일 종목 RL 기반 | 높음 | env/SB3/eval/walk-forward 기존 구현 있음 | 포트폴리오 회계와 완전 통합은 후속 |
| 포트폴리오 RL 엔진 구조 | 중~높음 | Page 1~6 구현, synthetic smoke 통과 | 실제 후보 데이터에서 shape/action/mask 재검증 |
| 조건식 screener 안전성 | 중 | AST whitelist, 금지 토큰 테스트 있음 | 실제 STOM 조건식 문법 coverage 확장 |
| DB 변수 feature 설계 | 중 | canonical feature mapping 구현 | 실제 DB 컬럼별 결측/스케일/분포 분석 필요 |
| 실제 RL 학습 알고리즘 | 낮~중 | smoke runner는 있음 | DQN/PPO/MaskablePPO 등 알고리즘 선택 연구 필요 |
| reward/action 설계 | 낮~중 | 기본 NAV reward/action contract 있음 | 비용, MDD, turnover, 보유시간 penalty 연구 필요 |
| full walk-forward 성능 검증 | 낮 | smoke report 있음 | 실제 기간별 fold, baseline 대비 검증 필요 |
| paper replay 실전성 | 중 | read-only replay/risk log 구현 | 실제 candidate/model action replay 필요 |
| dashboard 연결 | 낮 | 기존 RL UI 기반 있음 | portfolio artifact 전용 UI 설계 필요 |

판단:

- **Page 7~9, 즉 실제 DB feature export와 조건식 후보 CSV 생성은 진행해도 된다.**
- **Page 10 이후 실제 RL 학습은 시작 가능하지만, 최종 성능 달성으로 보려면 알고리즘·보상·검증 연구가 더 필요하다.**
- 따라서 현재 연구는 “강화학습 실행 준비”로는 충분하지만, “수익성 있는 최종 RL 전략 완성”으로는 아직 충분하지 않다.

## 4. 최종 목적 기준 진행률

| 구간 | 진행률 | 의미 |
|---|---:|---|
| Page 1~6 엔지니어링 기반 | 100% | 포트폴리오 RL 뼈대, 회계, screener, smoke, risk/paper 구조 완료 |
| 실제 DB feature export 준비 | 20% | helper는 있으나 full-scale 실행 전 |
| 실제 조건식 후보 생성 준비 | 20% | screener는 있으나 실제 전략 파일 연결 전 |
| 실제 candidate CSV 기반 RL 입력 | 10% | schema는 있으나 실제 산출물 전 |
| 실제 portfolio RL 학습 | 10% | env는 있으나 학습 알고리즘/runner 고도화 전 |
| full walk-forward 성능 검증 | 15% | smoke는 있으나 실제 fold 검증 전 |
| paper replay 실전 검증 | 20% | read-only 구조는 있으나 실제 replay 전 |
| dashboard 연결 | 0~20% | 기존 UI 기반은 있으나 portfolio 전용 연결 전 |
| 성능 최적화 | 0% | 최종 수익성/안정성 개선 단계 전 |

최종 목적 전체 진행률: **약 55~60%**

## 5. 남은 페이지 로드맵

### Page 7 — 실제 STOM DB feature export dry-run

| 항목 | 내용 |
|---|---|
| 목표 | 실제 `_database/stock_tick_back.db`에서 canonical RL feature를 생성 |
| 입력 | STOM SQLite DB |
| 출력 | 확장 feature CSV/manifest/report |
| 완료 기준 | 작은 테이블/짧은 기간 dry-run 성공, 결측/스케일 리포트 생성 |
| 주요 위험 | 29.7GB DB runtime, 컬럼명 encoding, 결측/스케일 불안정 |

### Page 7.5 — 다종목 1초 시간 동기화 join (신규, 핵심 데이터 게이트)

| 항목 | 내용 |
|---|---|
| 목표 | 여러 종목의 1초봉을 **공통 시간 인덱스**에 정렬해 포트폴리오가 같은 시각에 여러 종목을 동시에 관측·매매할 수 있는 panel을 만든다 |
| 배경 | 포트폴리오 RL은 동일 시각에 여러 종목 상태를 동시에 봐야 성립한다. DB는 종목별 테이블로 분리돼 있어 이 join이 없으면 candidate CSV(Page 9)와 PortfolioEnv가 성립하지 않는다 |
| 입력 | Page 7 feature export(종목별 1초 feature) |
| 출력 | `timestamp`를 키로 정렬한 다종목 panel(또는 long-format `timestamp, symbol, feature...`) + 결측 시각 처리 규칙(forward-fill 한계, 거래정지/VI 구간 제외) |
| 완료 기준 | ① 정렬 후 종목 간 timestamp 정합성 검증 ② 룩어헤드 차단(각 시점 row는 decision time 이하 데이터만 사용) ③ 결측/거래정지 구간 리포트 ④ 소수 종목·짧은 구간 정렬 결과 재현 가능 |
| 주요 위험 | 종목별 상이한 거래 시작/정지 시각, 1초 결측, 동시호가/VI 구간, 메모리(다종목 × 하루 1초 ≈ 수십만 row) |
| 비고 | 이 게이트는 Page 9(candidate CSV)의 **선행 조건**이다. Page 1~6의 synthetic candidate는 이 문제를 우회했으므로, 실데이터에서 처음 드러나는 가장 큰 데이터 엔지니어링 난관이다 |

### Page 8 — 실제 조건식 전략 선정/정규화

| 항목 | 내용 |
|---|---|
| 목표 | 실제 사용할 매수 조건식 세트를 선정하고 screener 입력으로 정규화 |
| 입력 | `docs/reference/stom_ai_agent/*`, 실제 조건식 파일 |
| 출력 | whitelist 통과 조건식 JSON/rule set |
| 완료 기준 | 금지 문법 차단, unknown variable 정리, buy/sell-only 변수 분리 |

### Page 9 — 실제 candidate CSV 생성

| 항목 | 내용 |
|---|---|
| 목표 | 조건식 통과 종목을 PortfolioEnv 입력 후보군으로 생성 |
| 출력 schema | `timestamp`, `symbol`, `condition_id`, `passed`, `rank_score`, `price`, `feature...` |
| 완료 기준 | 여러 시점/여러 종목 candidate CSV 생성, top-K 분포 리포트 |

### Page 10 — 실제 Portfolio RL 학습

| 항목 | 내용 |
|---|---|
| 목표 | 실제 candidate CSV로 RL agent를 학습 |
| 시작 알고리즘 | DQN/PPO smoke, 이후 action mask가 중요하면 MaskablePPO 검토 |
| 출력 | model, NAV curve, trades, actions, config summary |
| 완료 기준 | deterministic seed로 재현 가능한 train/eval smoke 통과 |
| 연구 필요 | reward shaping, action space, turnover/cost penalty, mask 처리 방식 |

### Page 11 — full walk-forward 검증

| 항목 | 내용 |
|---|---|
| 목표 | 기간별 fold에서 과최적화 여부 검증 |
| 비교 기준 | no-trade, equal-weight candidate, buy-and-hold, rule baseline, RL |
| 완료 기준 | fold별 return/MDD/turnover/trade count/cost report 생성 |
| 성공 기준 | artifact 생성은 engineering complete, baseline 초과는 performance target |

### Page 12 — 실제 paper replay 검증

| 항목 | 내용 |
|---|---|
| 목표 | 실제 후보와 모델 행동을 read-only로 재생 |
| 출력 | decision log, NAV curve, risk trigger log, blocked action reason codes |
| 완료 기준 | broker/order write path 없음, 동일 seed/input에서 deterministic |

### Page 13 — portfolio dashboard 연결

| 항목 | 내용 |
|---|---|
| 목표 | portfolio run artifact를 UI에서 확인 |
| 화면 | NAV, trades, positions, candidate/risk logs, fold summary |
| 완료 기준 | 기존 `/rl` 흐름을 깨지 않고 portfolio 결과 표시 |

### Page 14 — 성능 최적화

| 항목 | 내용 |
|---|---|
| 목표 | 실제 walk-forward 기준 성능 개선 |
| 대상 | feature set, reward, action space, condition ranking, risk params |
| 완료 기준 | 비용 반영 후 baseline 대비 개선 또는 개선 실패 원인 리포트 |

### Page 15 — 조건식 자동 생성/탐색 연구(선택)

| 항목 | 내용 |
|---|---|
| 목표 | 조건식 자체를 자동 탐색하거나 생성하는 별도 연구 |
| 전제 | Page 7~14가 안정화된 뒤 진행 |
| 이유 | 조건식 생성과 RL을 동시에 하면 과최적화 위험이 크므로 분리 필요 |
| 검증 | 조건식 train/validation/test 분리, walk-forward, 데이터마이닝 방지 |

## 6. 다음 권장 실행 순서

1. 현재 Page 1~6 변경사항 커밋
2. Page 7: 실제 DB feature export를 아주 작은 범위로 dry-run
3. Page 7.5: 다종목 1초 시간 동기화 panel 구축·검증 (Page 9의 선행 조건)
4. Page 8: 실제 조건식 1~3개를 rule JSON으로 정규화
5. Page 9: 실제 candidate CSV 생성 (Page 7.5 panel 기반)
6. Page 10: 실제 candidate CSV로 portfolio RL train smoke
7. Page 11~12: full walk-forward와 paper replay
8. Page 14: 성능 최적화 목표 별도 운영

## 7. 한 줄 요약

현재 문서화/연구는 **포트폴리오 RL을 실제 데이터 단계로 진입시키기에는 충분**하다.  
하지만 **최종 수익성 있는 강화학습 전략 완성**을 위해서는 Page 7~14의 실제 DB 실행, 알고리즘/보상 설계, full walk-forward, paper replay, 성능 최적화 연구가 추가로 필요하다.
