# STOM RL 랩 — 2026-05-29 재개 커밋 문서

- 작성일: **2026-05-29 KST**
- 대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`
- 브랜치: `feature/stom-rl-lab`
- 작성 직전 HEAD: `13b4162`
- 이 문서의 목적: **새 대화에서 이 파일 하나만 읽고도, 지금까지의 대화 맥락·검증 결과·정직성 가드레일·다음 페이지 작업을 그대로 이어가게 하는 것.**
- 이전 마스터 문서: `docs/stom_rl_resume_handoff_2026-05-28.md`
- 이 문서는 위 문서를 대체하기보다, **2026-05-28 문서 이후 대화에서 확인한 “현재 페이지/전체 진행률/다음 페이지”까지 반영한 최신 재개 앵커**다.

---

## 0. 새 대화에서 바로 사용할 프롬프트

새 대화 첫 메시지로 아래를 그대로 붙여넣는다.

```text
D:\Chanil_Park\Project\Programming\Kronos 에서 이어서 진행합니다.
먼저 docs/stom_rl_resume_commit_2026-05-29.md 를 읽고, 그 문서만을 기준으로 STOM RL 랩을 재개하세요.

중요:
1. RL 알파 부재는 이미 검증됐으므로, 갭상승 룰 전략 곡선을 강화학습/RL이라고 부르지 마세요.
2. 현재 다음 페이지는 “사이징/리스크 설계”입니다.
3. 먼저 git status, 현재 브랜치, 핵심 테스트 47개를 확인한 뒤 작업을 이어가세요.
```

재개 후 최소 확인 명령:

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
git branch --show-current
git rev-parse --short HEAD
py -3.11 -m pytest tests\test_stom_rl_gap_up_backtest.py tests\test_stom_rl_gap_up_dashboard_publish.py -q
```

기대 검증:

```text
feature/stom-rl-lab
<이 문서 커밋 또는 그 이후 커밋>
47 passed
```

---

## 1. 한 줄 결론

**현재 STOM RL 랩의 수익성 있는 축은 RL이 아니라 “시초 갭상승 룰 전략”이다.**

- RL/PPO/DQN 기반 cross-sectional 선택 알파는 1초·1분·세션 프록시에서 shuffle 검정 기준으로 실패했다.
- 사용자가 원한 “우상향 수익 곡선”은 RL 정책이 아니라, 사용자 실제 전략과 맞는 **시초 갭상승 + 체결강도/호가 필터 룰 백테스트**에서 나왔다.
- 주력 룰은 23bp 실제 왕복비용과 체결 de-idealization 스트레스까지 견뎠다.
- 다음 작업은 모델을 더 돌리는 것이 아니라, **실전 직전 운영 룰: 포지션 사이징·동시보유·일손실한도·중단조건**을 정하는 것이다.

---

## 2. 절대 지켜야 할 정직성 가드레일

이 프로젝트는 투자 판단 자동화로 오해될 수 있으므로, 아래 표현 규칙을 반드시 지킨다.

1. **갭상승 곡선을 “강화학습/RL 곡선”이라고 부르지 않는다.**
   - 올바른 표현: `시초 갭상승 룰 전략`, `RULE strategy`, `NOT RL`.
   - dashboard run label도 `algorithm="rule:gap_up_<filter>"`, `is_reinforcement_learning=false`를 유지한다.

2. **누적곡선은 비복리 per-trade % 합 또는 fixed-notional NAV다.**
   - 연수익률, 복리 계좌 성장률, 실계좌 보장 수익처럼 과장하지 않는다.

3. **실거래 준비 완료라고 말하지 않는다.**
   - 현재는 백테스트 + 체결 stress + dashboard 발행 완료 상태다.
   - 실전 전에는 사이징/리스크 룰, full universe 확인, read-only forward/paper 검증이 필요하다.

4. **2022 약세는 레짐 붕괴라고 단정하지 않는다.**
   - 2022는 N=39 소표본이며 95% CI가 0을 포함한다.
   - 다중비교 보정 기준으로 “소표본 변동성” 결론이 현재 정직한 해석이다.

5. **진짜 큐/부분체결 replay는 현재 DB만으로 만들지 않는다.**
   - L2 큐포지션 데이터가 없다.
   - 가능한 상한은 `realized`, `sl_gap_stress`, 슬리피지 sweep이다.

---

## 3. 사용자 목표와 전략 스펙

사용자 목표:

- 한국 STOM 기반 퀀트/단타 전략 연구.
- 유튜브 NEAT 영상 스크린샷처럼 “꾸준히 우상향하는 곡선”을 원함.
- 단, 대화 중 핵심 약속은 “억지로 RL에 끼워 맞춰 거짓 우상향을 만들지 않는다”였다.

확정 전략:

| 항목 | 값 |
|---|---|
| 전략명 | 시초 급등 / 9시 시초 갭상승 momentum |
| 진입 | 시초 `등락율` >= 2% |
| 주력 필터 | `ts_imb` = 체결강도 >= 100 AND 매수호가 imbalance >= 0.5 |
| 청산 | TP 5% / SL 1% / 09:25 시간청산 |
| 실제 왕복비용 | 23bp = 매수수수료 0.015% + 매도수수료 0.015% + 매도세 0.20% |
| 데이터 | `_database\stock_tick_back.db` 하나 |
| DB 특성 | 1초봉, 09:00~09:30 이벤트 트리거 희소 기록, 2427종목, UTF-8 한글 컬럼 |
| 주의 | 종목코드 선행 0 보존. `000250`을 int로 바꾸지 말 것. |

---

## 4. 지금까지의 핵심 흐름

### 4.1 과거 RL 방향

처음에는 단일 종목 RL, SB3 DQN/PPO, dashboard, live event, leaderboard까지 구현했다.

관련 과거 문서:

- `docs/stom_rl_page100_completion_report_2026-05-24.md`
- `docs/stom_rl_portfolio_design_handoff_2026-05-25.md`
- `docs/stom_rl_rl_execution_research_plan_2026-05-25.md`
- `docs/stom_rl_page10_5_earlyread_2026-05-26.md`
- `docs/stom_rl_page14_perf_optimization_2026-05-26.md`
- `docs/stom_rl_page16_full_universe_2026-05-26.md`
- `docs/stom_rl_page_c0_feature_probe_2026-05-27.md`

하지만 RL 쪽 핵심 결론은 다음이다.

- 1초 horizon: 선택 알파 없음.
- 1분 horizon: 선택 알파 없음.
- 세션바/일봉 proxy: 선택 알파 없음.
- 비용 반영 시 결정론 RL 대역은 turnover 비용에 먹힘.
- 그래서 RL 포트폴리오를 더 밀기보다, 사용자 실제 전략과 DB가 맞는 **시초 갭상승 룰 전략**으로 reframe했다.

### 4.2 갭상승 룰 전략 방향

순서:

1. 필터 없이 2% 갭상승 TP/SL grid 테스트 → 비용에 먹혀 OOS 실패.
2. 체결강도/호가 필터 추가 → 비용 후 양수 신호.
3. 레짐 robustness + 슬리피지 sweep → 매년/경계 검증 통과.
4. 사용자 실제 비용 23bp 반영 → `ts_imb` 기대값 약 +0.95%/trade.
5. dashboard run과 PNG 곡선 발행.
6. `realized` / `sl_gap_stress` fill mode로 체결 de-idealization.
7. 2022 약세는 다중비교 보정 결과, 소표본 변동성으로 해석.
8. 2026-05-29 현재: 다음은 수익성 탐색이 아니라 **실전 운영 룰 설계**.

---

## 5. 확정 수치 요약

### 5.1 주력 필터 정의

소스: `stom_rl/gap_up_backtest.py`

| 필터 | 정의 |
|---|---|
| `none` | 시초 등락율 >= 2%만 |
| `ts` | `none` + 체결강도 >= 100 |
| `ts_imb` | `ts` + 매수호가 imbalance >= 0.5 |

### 5.2 23bp 기준 기대값, TP5/SL1/09:25

| 필터 | N | 기대값 @23bp | de-idealized | breakeven | 여유 |
|---|---:|---:|---:|---:|---:|
| none | 1349 | +0.246% | +0.206% | 42.7bp | 1.9x |
| ts | 425 | +0.633% | +0.593% | 82.7bp | 3.6x |
| **ts_imb** | 235 | **+0.952%** | **+0.912%** | 116.6bp | **5.1x** |

### 5.3 누적 equity 곡선, idealized 캐시 + 23bp 환산

| 필터 | N | 누적% 비복리 | 기대값/trade | 승률 | 최대낙폭 | 최장연패 |
|---|---:|---:|---:|---:|---:|---:|
| UNFILTERED | 1349 | +332.2% | +0.246% | 29% | -26.0% | 17 |
| ts | 425 | +269.0% | +0.633% | 36% | -19.3% | 12 |
| **ts_imb** | 235 | **+223.6%** | **+0.952%** | **42%** | **-15.7%** | **9** |

해석:

- `none`은 총 누적은 크지만 낙폭과 연패가 크다.
- `ts_imb`는 trade 수가 줄어도 곡선이 가장 매끈하고 위험이 낮다.
- 다음 사이징 페이지는 `ts_imb`를 기준으로 설계한다.

### 5.4 체결 de-idealization

주의: `.omx\artifacts\gap_up_*\instances.json` 캐시는 기본적으로 25bp 값이 들어있고, 23bp 환산은 `+0.02%p`를 더한다.

| 모드 | 캐시 raw @25bp | 23bp 환산 | 의미 |
|---|---:|---:|---|
| idealized | +0.932% | +0.952% | 낙관적 기준 |
| realized | +0.886% | +0.906% | 실제 기록가 기반 |
| sl_gap_stress | +0.791% | +0.811% | 손절 gap-through 최악 스트레스 |

핵심:

- 최악 stress 후에도 `ts_imb`는 **+0.811%/trade**로 양수.
- 다만 MDD는 약 -20%대까지 볼 수 있으므로, 다음 페이지에서 risk sizing이 필수다.

### 5.5 연도별 약세

| 모드 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| idealized | +0.09 | +1.45 | +1.10 | +1.00 | +0.91 |
| realized | -0.01 | +1.50 | +1.02 | +0.93 | +0.90 |
| sl_gap_stress | -0.05 | +1.32 | +0.96 | +0.85 | +0.76 |

해석:

- 2022만 약하다.
- 그러나 N=39, SE 약 ±0.40%/trade로 오차가 크다.
- Bonferroni 보정 후 레짐 붕괴로 단정하지 않는다.
- 사이징 페이지에서는 “단일 연도 flat/음수 가능”을 리스크 한도로 흡수해야 한다.

---

## 6. 방금 대화에서 확인한 페이지/진행률

사용자 요청:

> “방금 진행한 페이지 그리고 전체 페이지 진행률로 다음 페이지와 함께 안내”

그에 대해 확인한 최신 상태:

### 6.1 방금 진행한 페이지

**페이지명:** `2026-05-29 재개/현황 복원 페이지`

완료한 일:

- `docs/stom_rl_resume_handoff_2026-05-28.md` 읽음.
- 최신 브랜치/HEAD 확인.
- 핵심 테스트 재실행: `47 passed`.
- gitignored 캐시 및 dashboard run 존재 확인.
- `build_equity_curve.py` / `fill_mode_compare.py` 실행으로 수치 재확인.
- dashboard progress API의 기존 RL Lab page 기준 진행률 확인.
- 다음 페이지를 “사이징/리스크 설계”로 결정.

상태: **완료**

### 6.2 전체 진행률 — 두 기준을 분리해서 해석

#### A. 구 dashboard RL Lab page progress 기준

`webui.rl_dashboard.load_rl_progress()` 결과:

| dashboard page | 진행률 | 상태 |
|---|---:|---|
| RL Lab 개요 | 100% | complete |
| 실시간 RL | 67% | in_progress |
| 실제 딥러닝 학습 | 33% | in_progress |
| Performance Leaderboard | 100% | complete |
| Artifacts / Models | 33% | in_progress |
| Docs / 운영 경계 | 100% | complete |
| **전체** | **72%** | in_progress |

해석:

- 이 72%는 **과거 SB3/RL Lab dashboard artifact 기준**이다.
- 현재 갭상승 룰 전략의 실질 진행률과 혼동하면 안 된다.
- 일부 model zip/check_env criteria 때문에 낮게 잡힌다.

#### B. 최신 갭상승 룰 전략 기준

| 영역 | 상태 |
|---|---|
| RL 알파 부재 판정 | 완료 |
| 갭상승 룰 백테스트 | 완료 |
| 비용 23bp 반영 | 완료 |
| 필터 ts/ts_imb 검증 | 완료 |
| 레짐/슬리피지 검증 | 완료 |
| fill_mode 체결 stress | 완료 |
| dashboard run 발행 | 완료 |
| 2022 소표본 해석 | 완료 |
| **사이징/리스크 설계** | **다음** |
| full universe 재검증 | 이후 |
| read-only forward/paper | 이후 |

실질 체감 진행률:

- **갭상승 룰 전략 연구/검증:** 90% 내외.
- **실거래 직전 운영 준비:** 70~80%.
- **주문 직전 안전 운영체계까지 포함한 전체:** 약 80~85%.

남은 핵심 15~20%는 수익 곡선을 더 찾는 일이 아니라, **돈을 얼마나 안전하게 태울지 정하는 운영 설계**다.

---

## 7. 현재 파일/산출물 지도

### 7.1 커밋된 핵심 소스

| 파일 | 역할 |
|---|---|
| `stom_rl/gap_up_backtest.py` | 갭상승 룰 백테스트 엔진. `--fill-mode`, `--regime-analysis`, `--cost-bps`, `--max-symbols`, `--artifacts-dir` 지원. |
| `stom_rl/gap_up_dashboard_publish.py` | 갭상승 곡선을 `webui/rl_runs` dashboard run으로 발행. |
| `tests/test_stom_rl_gap_up_backtest.py` | 백테스트 테스트 41개. |
| `tests/test_stom_rl_gap_up_dashboard_publish.py` | dashboard 발행 테스트 6개. |
| `webui/rl_dashboard.py` / `webui/app.py` | `/api/rl/*` read-only dashboard. |
| `stom_rl/rl_events.py` | dashboard event/summary 재사용 계층. |

### 7.2 커밋된 핵심 문서

읽기 순서:

1. `docs/stom_rl_resume_commit_2026-05-29.md` — 이 문서, 최신 재개 앵커.
2. `docs/stom_rl_resume_handoff_2026-05-28.md` — 이전 마스터 핸드오프, 재현 스크립트 내장.
3. `docs/stom_rl_gap_up_fillmode_2026-05-28.md` — 체결 de-idealization + 2022 분석.
4. `docs/stom_rl_gap_up_realcost_2026-05-28.md` — 23bp 비용 확정.
5. `docs/stom_rl_gap_up_regime_validation_2026-05-28.md` — 레짐/슬리피지 검증.
6. `docs/stom_rl_gap_up_cost_filter_2026-05-27.md` — 현실 비용 + 진입 필터.
7. `docs/stom_rl_gap_up_backtest_2026-05-27.md` — 필터 전 기준선.
8. `docs/stom_rl_deep_rl_verdict_2026-05-27.md` — RL 알파 부재 종합.

### 7.3 gitignored 산출물

다음은 커밋 대상이 아니며, 필요 시 §8 명령으로 재생성한다.

| 경로 | 역할 |
|---|---|
| `.omx\artifacts\gap_up_backtest\instances.json` | idealized 기본 캐시 |
| `.omx\artifacts\gap_up_idealized\instances.json` | 비교용 idealized 캐시 |
| `.omx\artifacts\gap_up_realized\instances.json` | realized fill 캐시 |
| `.omx\artifacts\gap_up_sl_gap_stress\instances.json` | 최악 손절 gap stress 캐시 |
| `.omx\artifacts\gap_up_backtest\build_equity_curve.py` | 캐시 기반 곡선 요약/PNG 생성 |
| `.omx\artifacts\gap_up_backtest\fill_mode_compare.py` | fill mode 비교 |
| `webui\rl_runs\gap_up_*` | dashboard run 5개 |

2026-05-29 확인 시 위 캐시와 run은 존재했다.

---

## 8. 재현 명령

### 8.1 핵심 테스트

```powershell
py -3.11 -m pytest tests\test_stom_rl_gap_up_backtest.py tests\test_stom_rl_gap_up_dashboard_publish.py -q
```

검증 결과:

```text
47 passed
```

### 8.2 갭상승 캐시 재생성

```powershell
# idealized 기본 캐시 + 레짐분석
py -3.11 stom_rl\gap_up_backtest.py --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_backtest

# fill mode별 캐시
py -3.11 stom_rl\gap_up_backtest.py --fill-mode idealized      --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_idealized
py -3.11 stom_rl\gap_up_backtest.py --fill-mode realized       --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_realized
py -3.11 stom_rl\gap_up_backtest.py --fill-mode sl_gap_stress  --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_sl_gap_stress
```

주의:

- `--max-symbols 120`은 현재 문서 수치와 맞는 bounded 검증 universe다.
- `--max-symbols 0`은 full universe이며 매우 오래 걸릴 수 있다. 다음 단계 B에서 별도 장기 작업으로 다룬다.

### 8.3 곡선/체결 비교 재확인

```powershell
py -3.11 .omx\artifacts\gap_up_backtest\build_equity_curve.py
py -3.11 .omx\artifacts\gap_up_backtest\fill_mode_compare.py
```

기대 핵심 출력:

```text
UNFILTERED(2%갭만)       N=1349 cum= +332.2% exp=+0.246%/trade win=29% maxDD=-26.0% maxLossStreak=17
+체결강도(ts)              N= 425 cum= +269.0% exp=+0.633%/trade win=36% maxDD=-19.3% maxLossStreak=12
+체결강도+호가(ts_imb)       N= 235 cum= +223.6% exp=+0.952%/trade win=42% maxDD=-15.7% maxLossStreak=9
```

fill mode 출력은 캐시 raw @25bp 기준 값이므로, 23bp로 읽을 때 +0.02%p를 더한다.

### 8.4 dashboard run 발행

```powershell
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter none   --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter ts     --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter ts_imb --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --instances .omx\artifacts\gap_up_realized\instances.json --filter ts_imb --cost-bps 23 --run-name gap_up_ts_imb_realized
py -3.11 -m stom_rl.gap_up_dashboard_publish --instances .omx\artifacts\gap_up_sl_gap_stress\instances.json --filter ts_imb --cost-bps 23 --run-name gap_up_ts_imb_sl_gap_stress
```

대시보드 서버:

```powershell
$env:KRONOS_WEBUI_PORT='5070'
$env:KRONOS_WEBUI_OPEN_BROWSER='0'
$env:KRONOS_WEBUI_RELOAD='0'
py -3.11 webui\run.py
```

URL:

```text
http://127.0.0.1:5070/rl
```

서버는 리로더 OFF이므로 신규 run을 인식하지 못하면 재시작한다.

---

## 9. 다음 페이지 — 사이징/리스크 설계

### 9.1 왜 다음 페이지가 이것인가

지금은 “수익 곡선을 찾는 단계”가 아니다.

이미 확인된 것:

- `ts_imb`는 비용 후 양수.
- 최악 체결 stress도 양수.
- dashboard 곡선도 발행됨.
- RL이 아니라 룰 전략이라는 정직한 framing도 확정됨.

따라서 다음 질문은 다음이다.

> 이 전략에 실제 계좌의 몇 %를 넣을 수 있으며, 언제 멈춰야 하는가?

### 9.2 Page A 목표

**Page A — 시초 갭상승 룰 전략 사이징/리스크 설계**

산출물:

1. `docs/stom_rl_gap_up_risk_sizing_2026-05-29.md`
2. 가능하면 `stom_rl/gap_up_risk_sizing.py` 또는 테스트 가능한 순수 함수.
3. 최소 테스트 파일: `tests/test_stom_rl_gap_up_risk_sizing.py`

### 9.3 Page A 입력값

| 항목 | 기준값 |
|---|---:|
| 주력 필터 | `ts_imb` |
| trade 수 | 235 |
| 기대값 @23bp | +0.952%/trade |
| 최악체결 기대값 @23bp | +0.811%/trade |
| 승률 | 약 42% |
| 최장연패 | 9 |
| 최대낙폭 idealized | 약 -15.7% |
| 최대낙폭 stress | 약 -20%대 |
| TP/SL | +5% / -1% |
| 2022 stress | flat~소폭 음수 가능 |

### 9.4 Page A에서 정해야 할 룰

필수 결정 항목:

1. **1회 진입 노셔널**
   - 예: 계좌의 5%, 10%, 20% 중 무엇이 허용 가능한가.

2. **동시보유 제한**
   - 09:00~09:25 window에서 여러 종목이 동시에 뜰 수 있다.
   - top-K 우선순위가 필요하다.

3. **일손실한도**
   - 예: 하루 -1R, -2R, -3R 도달 시 그날 신규 진입 중단.

4. **연속손실 중단 룰**
   - 최장연패 9를 기준으로, 3연패/5연패/7연패 구간별 감액 또는 중단.

5. **월간/연간 낙폭 룰**
   - 2022 같은 flat/음수 가능성을 견딜 한도.

6. **유동성/체결 가능성 한도**
   - `entry_sec_amount`, 체결강도, 호가 imbalance를 기반으로 주문금액 상한을 둘지 검토.

7. **실전 전 forward 조건**
   - read-only live signal N일 이상 양수/정상 작동 전에는 실주문 금지.

### 9.5 Page A 완료 기준

문서와 코드가 다음 질문에 답해야 한다.

- 계좌 1,000만원/5,000만원/1억원일 때 1회 진입금액은 얼마인가?
- 하루 최대 몇 종목까지 진입하는가?
- 하루 최대 손실은 몇 원/몇 %인가?
- 최장연패 9회가 와도 계좌가 감내 가능한가?
- 2022 같은 약세 구간에서 자동 감액/중단이 되는가?
- dashboard/paper run에 같은 risk rule을 적용할 수 있는가?

---

## 10. 이후 페이지 결정 트리

Page A 이후 권장 순서:

1. **Page A — 사이징/리스크 설계**
   - 가장 실질적이며 다음 작업.

2. **Page B — full universe 재검증**
   - `--max-symbols 0`으로 전체 2427종목에서 수치 유지 확인.
   - 장기 실행/체크포인트 필요.

3. **Page C — 실주문 슬리피지/유동성 모델**
   - 실제 주문 가능 금액, 초당 거래대금, 호가잔량 기반 상한.

4. **Page D — read-only live paper/forward**
   - 실주문 없이 시점별 신호 생성.
   - 최소 N일 관찰.

5. **Page E — broker/order 연동 검토**
   - 이 단계는 아직 하지 않는다.
   - 실거래 API/주문 발행은 명시적 별도 승인 없이는 금지.

---

## 11. 현재 git 상태 주의

2026-05-29 문서 작성 전 확인된 `git status --short`에는 다음 untracked 항목이 있었다.

```text
?? .codegraph/
?? .omc/notepad.md
?? .omc/project-memory.json
?? .omc/sessions/
?? .omc/state/
?? template/
?? webui/stom_predictions/
```

이 문서 작업에서는 위 항목을 건드리지 않는다.

커밋 대상은 이 문서 파일만이어야 한다.

---

## 12. 커밋 후 재개자가 할 첫 행동

새 대화/새 에이전트는 다음 순서로 움직인다.

1. 이 문서를 읽는다.
2. `git status --short`, `git branch --show-current`, `git log --oneline -5`를 확인한다.
3. `47 passed` 테스트를 재확인한다.
4. `docs/stom_rl_resume_handoff_2026-05-28.md`는 보조로만 읽는다.
5. 작업 모드는 **Page A 사이징/리스크 설계**로 시작한다.
6. 새 코드 작성 전, 문서형 risk plan을 먼저 쓴다.
7. 이후 테스트 가능한 순수 risk sizing 함수/테스트를 추가한다.

---

## 13. 완료 선언 기준

이 커밋 문서는 다음을 만족하면 성공이다.

- 새 대화가 과거 채팅을 보지 않아도 현재 위치를 알 수 있다.
- RL이 아니라 룰 전략이라는 정직성 가드레일을 알 수 있다.
- 검증 수치와 재현 명령을 알 수 있다.
- “전체 진행률 72%”와 “갭상승 기준 80~85%”의 기준 차이를 알 수 있다.
- 다음 페이지가 사이징/리스크 설계임을 알 수 있다.
- 어떤 파일을 건드리고 어떤 산출물을 재생성해야 하는지 알 수 있다.

---

## 14. 짧은 인수인계 멘트

현재까지는 **수익 곡선 탐색은 끝났고, 실전 운영 설계 직전**이다.

다음 에이전트는 RL 학습을 더 돌리지 말고, `ts_imb` 갭상승 룰을 기준으로 **계좌 크기별 포지션 사이징, 동시보유 제한, 일손실한도, 연패/낙폭 중단 룰**을 설계하라.

단, 모든 문서/코드/대시보드 표현에서 이 전략을 반드시 **“RULE strategy, NOT reinforcement learning”**으로 표시하라.
