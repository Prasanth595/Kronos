# STOM 강화학습 — 조건식 기반 포트폴리오 RL 설계 & 핸드오프

작성일: 2026-05-25
브랜치: `feature/stom-rl-lab`
대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`
성격: **새 대화에서 그대로 이어받을 수 있는 설계·핸드오프 문서**

이 문서는 (1) 현재 강화학습(RL) 실험실의 실제 상태, (2) 사용자가 원하는 목표(자본금으로 여러 종목을 사고팔며 총자산을 키우는 포트폴리오 RL), (3) 그 가능성, (4) 목표 달성을 위한 단계별 방법, (5) 새 대화에서 이어갈 때 필요한 파일·명령·프롬프트를 한 곳에 모은 것이다.

> ⚠️ 중요 전제: 이 RL 실험실은 **Kronos 예측 모델과 독립(Kronos 비의존)** 이다. 다만 매매 변수·조건식 문법은 원본 STOM 조건식 생성기에서 가져온 레퍼런스(`docs/reference/stom_ai_agent/`)를 단일 진실 공급원으로 참고한다.

---

## 0. 한 줄 요약

현재 RL은 **한 종목의 시장 원천 feature 6개(open/high/low/close/volume/amount)와 포지션 파생 3개만 보고 사고/팔고/기다리는 단일 종목 에이전트**다. 사용자가 원하는 것은 **초기 자본금으로 조건식에 걸린 여러 종목을 동시에 사고팔며 총자산(NAV)을 키우는 포트폴리오 RL**이다. 이는 올바른 방향이지만 현재 구조의 **큰 재설계**이며, 본 문서의 단계 로드맵(0→6)을 따른다.

---

## 1. 현재 상황 (실제 코드 기준)

### 1.1 RL 실험실 구조

| 영역 | 파일 | 역할 |
|---|---|---|
| 환경(MDP) | `stom_rl/trading_env.py` | 단일 종목 1초봉 트레이딩 env |
| 회계 | `stom_rl/baselines.py` (`AccountState`) | 비용·포지션·equity 계산 |
| Gym 어댑터 | `stom_rl/sb3_adapter.py` | Gymnasium/SB3 호환 |
| 학습 | `stom_rl/sb3_smoke.py` | DQN/PPO 학습·저장·평가·live event |
| 저장모델 평가 | `stom_rl/sb3_eval.py` | 재학습 없이 N episode 재평가 (eval-only) |
| 기간검증 | `stom_rl/walk_forward.py` | 시간순 fold별 재평가(과적합 탐지) |
| 성과표 | `stom_rl/performance_leaderboard.py` | baseline/bandit/SB3 통합 leaderboard |
| 웹 | `webui/rl_dashboard.py`, `webui/v2_src/src/tabs/RLLabTab.svelte` | `http://127.0.0.1:5070/rl` |
| 공부자료 | `docs/stom_rl_study_guide.html`, `docs/wiki/11-reinforcement-learning.md` | RL 원리 설명 |

### 1.2 현재 RL의 한계 (검증으로 드러남)

| 항목 | 현재 |
|---|---|
| 종목 | **한 번에 1종목** (episode = 1종목의 하루 세션) |
| 포지션 | **0/1** (전액 매수 / 전액 청산), 사이징 없음 |
| 자본금 | **없음** — `equity=1.0`에서 시작하는 정규화 지수(돈 아님) |
| 동시 보유 | 없음 (episode 순차 평가 후 곱셈) |
| 사용 변수 | **9개** (시장 6: open/high/low/close/volume/amount + 파생 3: position/unrealized_return/time_in_position) |
| 보상 | `reward_mode="horizon"`, 300초 forward 수익률 − 25bp 비용 |
| 성능 | 50k 모델이 100 episode에서 +1.34%(dqn) — buy&hold(+0.51%) 초과하나 **regime_sensitive** |
| 학습량 확대 | 50k→100k **무효**(오히려 약간 하락) |
| 기간 안정성 | walk-forward 6 fold 중 dqn 5/6·ppo 4/6 양수, **최근 구간 손실** |

### 1.3 데이터 흐름 (병목)

```
STOM DB(_database/stock_tick_back.db, 29.7GB, 종목별 ~50변수)
   └─(export, 여기서 OHLCV+amount만 추림)→ finetune/qlib_exports/.../qlib_csv/*.csv (10컬럼)
       └→ episode_manifest(종목-세션 분할) → trading_env(9 feature) → SB3
```
→ **변수를 늘리려면 export 단계부터 다시** 내보내야 한다.

---

## 2. 사용자가 원하는 목표

1. **초기 자본금**에서 시작한다(정규화 지수가 아니라 실제 ₩ 개념).
2. **조건식에 걸린 여러 종목**을 후보로 받아 **동시에 여러 개 사고판다**.
3. 매매를 반복하며 **총자산(NAV)이 늘어나는 방향**으로 강화학습한다.
4. **시간 조절**(언제 사고 언제 파는지, 보유시간)을 RL이 학습/제어한다.
5. 조건식 생성은 원본 STOM 프로그램(`docs/reference/stom_ai_agent/`)의 문법·변수를 따른다.

---

## 3. STOM 조건식 시스템 (레퍼런스 요약)

출처: `docs/reference/stom_ai_agent/` (원본 `C:\System_Trading\STOM\STOM_V.wt-dev\utility\ai_agent` 복사본)

### 3.1 사용 가능한 변수 (DB가 실제 제공)

| 그룹 | 대표 변수 |
|---|---|
| 가격 | 현재가, 시가, 고가, 저가, 등락율, 고저평균대비등락율, 저가대비고가등락율 |
| 거래/수급 | 당일거래대금, 초당거래대금, **체결강도(0~500)**, 초당매수수량, 초당매도수량, 초당매수금액, 초당매도금액, 최고매수/매도금액·가격 |
| 호가창 | 매도호가1~5, 매수호가1~5, 매도잔량1~5, 매수잔량1~5, 매도총잔량, 매수총잔량, 매도수5호가잔량합 |
| 국내전용 | 거래대금증감, 전일비, 회전율, 전일동시간비, 시가총액, 라운드피겨위5호가이내, VI해제시간/VI가격/VI호가단위 |
| 구간연산 | 이동평균, 변동성, 최고/최저현재가, 체결강도평균, 거래대금각도, 등락율각도 … |
| 복합조건 | 가격급등, 거래대금급증, 체결강도급등, 호가상승압력, 횡보후가격급등 … (181개 함수형) |
| 보조지표(1분봉) | RSI, MACD, ATR, BB, CCI, OBV, STOCH, WILLR … |
| **매도전용 잔고** | **수익률, 수익금, 매수가, 보유수량, 보유시간, 최고수익률, 최저수익률, 분할매수/매도횟수** |

### 3.2 조건식(전략) 문법

- **매수전략**: `매수 = True`로 시작 → 통과 못할 조건은 `매수 = False`로 차단 → `if 매수: self.Buy()`.
- **매도전략**: 청산 조건을 나열해 하나라도 참이면 `매도 = True` → `if 매도: self.Sell()`.
- 이전값: `현재가N(1)`(1틱 전), 구간연산: `이동평균(60)` / `체결강도평균(30)`.
- 매수전략에서 매도전용 변수(수익률·보유시간 등) 사용 금지.

매수 예시:
```python
매수 = True
if 관심종목 != 1: 매수 = False
elif not (0 < 등락율 <= 25): 매수 = False
elif not (당일거래대금 > 100): 매수 = False
elif not (체결강도 >= 체결강도평균(30) + 5): 매수 = False
if 매수: self.Buy()
```
매도(동적청산) 예시:
```python
if 수익률 >= 3: 매도 = True
elif 수익률 <= -2: 매도 = True
elif 보유시간 >= 600 and 변동성(30) <= 0.5: 매도 = True
if 매도: self.Sell()
```

### 3.3 RL 관점의 핵심 통찰

- **조건식 = 종목 universe 필터**: 매수 조건식이 "지금 살 만한 후보"를 골라준다 → RL이 수천 종목을 다 평가할 필요 없이 **후보 중에서만** 선택하면 된다(행동 공간 축소).
- **매도전용 변수(보유시간·수익률)** 가 이미 정의돼 있다 → "시간 조절/동적청산"을 RL 보상·상태에 그대로 녹일 수 있다.

---

## 4. 가능성 검토 (3가지 질문에 대한 답)

### Q1. 강화학습으로 "시간 조절"이 가능한가? → ✅ 가능 (이미 일부 됨)
- 현재도 에이전트가 `sell` 시점을 스스로 정하므로 **보유시간은 가변**이다. `time_in_position`이 상태에 들어간다.
- `reward_horizon_seconds`(현재 300)는 설정 가능하고, `reward_mode="mark_to_market"`(보상은 1-step 손익)도 이미 구현돼 있다. 단, 현재 env의 episode 안전 구간(`max_action_idx`)과 최소 row 계산은 여전히 `reward_horizon_seconds`에 의존하므로, mark-to-market 전환 시 이 의존성을 함께 점검해야 한다.
- 보유시간을 **단일 고정값으로 둘 필요 없다** — 다중 horizon·동적청산(수익률/변동성 기반)으로 확장 가능.

### Q2. 지금 모델이 "여러 종목 동시 매수"를 고려하나? → ❌ 아니다
- 현재는 단일 종목·0/1 포지션·자본금 없음. 포트폴리오가 아니다.

### Q3. 자본금으로 다종목 사고팔며 총자산을 키우는 RL이 좋은가? → ✅ 방향은 옳음, 단 큰 재설계
- 실거래에 훨씬 가깝고 STOM 백테스트 DB의 성격(조건식 매매)과도 맞다.
- 그러나 행동공간·자본제약·동시 포지션 회계·신용할당(credit assignment)·검증 난이도가 모두 커진다.
- 현재 단일 종목조차 정보부족(9변수)·기간민감이므로, **토대(변수·신호)부터 강화한 뒤 포트폴리오로 확장**해야 안전하다.

---

## 5. 목표 달성 방법 — 단계 로드맵

> 원칙: 한 번에 포트폴리오로 점프하지 말고, 검증 가능한 작은 단계로 쌓는다.

### 단계 0 — 실행 문서/명령 보정 (개발 전 정리)
- PowerShell 기준으로 테스트/DB 확인 명령을 실제 동작하는 형태로 고친다.
- 현재 `ruff` 실패 항목은 known issue로 기록하거나 별도 정리 후 다음 단계에 들어간다.
- 완료기준: 새 대화의 작업자가 7.2 명령을 그대로 복사해 최소 검증을 재현할 수 있다.

### 단계 1 — Feature 확장 (가장 먼저, 적은 변경/큰 효과)
- export 파이프라인에 **호가불균형(매수잔량합/(매수+매도잔량)), 체결강도, 초당매수/매도수량, 거래대금각도** 등을 추가.
- `trading_env.BASE_MARKET_COLUMNS` / `feature_columns` 확장, 정규화 처리.
- 완료기준: 단일 종목 RL이 새 feature로 walk-forward 일관성이 개선되는지 비교.

### 단계 2 — 자본금 + 포지션 사이징
- `AccountState`를 정규화 1.0 → **실제 자본금(현금잔고 + 보유평가액)** 으로 일반화.
- 현재 `StomTickTradingEnv`도 내부에 `position/entry_price/realized_return` 회계를 별도로 갖고 있으므로, 단순히 `AccountState`만 고치지 말고 **공용 accounting 모듈**로 통합하거나 env가 같은 회계 로직을 호출하도록 정리한다.
- 행동을 0/1 → **비중(예: 0/25/50/100% 또는 연속)** 으로 확장.
- 완료기준: 단일 종목에서 사이징이 동작하고 NAV가 추적되며, baseline/env/향후 portfolio env가 같은 회계 규칙을 공유함.

### 단계 3 — 조건식 후보 생성기 연결
- `docs/reference/stom_ai_agent/`의 매수 조건식을 STOM DB(`_database/stock_tick_back.db`)에 적용해 **시점별 매수 후보 종목 목록**을 생성하는 모듈(`stom_rl/condition_screener.py`(가칭)) 추가.
- 조건식 평가기는 화이트리스트 변수만 허용(forbidden.md 준수, `eval` 금지 → 안전한 파서/AST).
- 산출물 schema는 최소 `timestamp`, `symbol`, `condition_id`, `passed`, `rank_score`, `feature...`를 포함하고, 포트폴리오 env가 바로 읽을 수 있도록 parquet/csv/jsonl 중 하나로 고정한다.
- 완료기준: 특정 일자/시점에 "조건 통과 종목 리스트 + 그 시점 feature"가 재현 가능.

### 단계 4 — 포트폴리오 환경(PortfolioEnv)
- 상태: 현금잔고 + 보유종목들(종목별 수익률·보유시간) + **조건식 후보들의 feature**.
- SB3 호환을 위해 관측 shape는 고정해야 한다. 후보는 `top_k_candidates` 슬롯으로 자르고 부족분은 padding하며, `candidate_mask`로 실제 후보/패딩을 구분한다. 보유 종목도 `max_positions` 슬롯으로 고정한다.
- 행동: 후보 중 매수 선택·비중 + 보유종목 매도(동적청산 변수 활용). 초기 버전은 `Discrete` action으로 단순화한다(예: hold, 후보 슬롯 i를 25/50% 매수, 보유 슬롯 j 전량/부분 매도). 이후 안정화되면 MultiDiscrete/Box로 확장한다.
- 보상: 매 step **총자산(NAV) 변화 − 비용/슬리피지 − 선택적 risk penalty**.
- 제약: 현금 한도, 동시 보유 종목 수 상한(예 ≤5~10), 종목당 비중 상한, action mask 또는 invalid-action penalty.
- 완료기준: 소수 후보/소수 종목(예 top-K≤10, 보유≤5) 동시 보유로 학습/평가가 돌고 NAV 곡선·거래 로그·action mask 통계가 나온다.

### 단계 5 — 검증 (walk-forward + 기준선)
- 포트폴리오 NAV를 기간 분할 walk-forward로 검증, buy&hold·동일가중 등과 비교.
- 완료기준: 여러 기간에서 일관되게 기준선 초과 + 비용·MDD 게이트 통과.

### 단계 6 — 위험관리 & paper replay
- Max DD·연속손실·일일거래한도·종목당 비중상한 등 risk gate.
- read-only paper replay(실주문 없음)로 실거래 직전 점검.

| 단계 | 핵심 산출물 | 난이도 | 권장 순서 |
|:--:|---|:--:|:--:|
| 0 | 실행 문서/명령 보정 | 낮음 | 완료 |
| 1 | feature 확장 + 비교 | 낮음 | **지금** |
| 2 | 자본금/사이징 | 중 | 다음 |
| 3 | 조건식 스크리너 | 중 | 3번째 |
| 4 | PortfolioEnv + RL | **높음** | 4번째 |
| 5 | walk-forward 검증 | 중 | 5번째 |
| 6 | risk gate/paper | 중 | 마지막 |

---

## 6. 주요 도전 과제와 완화책

| 도전 | 설명 | 완화책 |
|---|---|---|
| 행동공간 폭발 | 수천 종목 × 비중 | **조건식 후보 필터**로 universe 축소 |
| 신용 할당 | 어느 매수가 수익에 기여했는지 모호 | NAV 기반 보상 + 충분한 데이터 + 단순 사이징부터 |
| 데이터 동기화 | 다종목 1초 동기 정렬 | DB에 종목별 테이블 존재(가능) — 시점 인덱스 정렬 유틸 필요 |
| 회계 정확성 | 현금/평가액/비용/동시포지션 | `AccountState`와 env 내부 회계를 공용 accounting 모듈로 통합 + 단위 테스트 |
| 과적합/기간민감 | 단일 종목도 이미 발생 | 단계마다 walk-forward, 보수적 비중상한 |
| 안전(조건식 eval) | 임의 코드 실행 위험 | forbidden.md 토큰 차단, AST 화이트리스트 파서 |

---

## 7. 새 대화에서 이어가기 (핸드오프)

### 7.1 먼저 읽을 것
1. 이 문서 (`docs/stom_rl_portfolio_design_handoff_2026-05-25.md`)
2. `docs/reference/stom_ai_agent/README.md` 및 `strategy.txt`, `variables_reference.md`
3. RL 원리: `docs/wiki/11-reinforcement-learning.md` 또는 `docs/stom_rl_study_guide.html`
4. 직전 RL 핸드오프: `docs/stom_rl_current_branch_handoff_2026-05-24.md`

### 7.2 환경/명령
```powershell
# 서버 (5070, 리로더 off가 기본)
$env:KRONOS_WEBUI_PORT="5070"; $env:KRONOS_V2_DIST="1"
py -3.11 webui\run.py            # http://127.0.0.1:5070/rl

# 단일 종목 RL 학습/평가 (현재 구조)
py -3.11 -m stom_rl.sb3_smoke --algorithms dqn,ppo --total-timesteps 50000 --device auto
py -3.11 -m stom_rl.sb3_eval --model-dir webui/rl_runs/stom_1s_2025_sb3_50k --eval-episodes 100
py -3.11 -m stom_rl.walk_forward --model-dir webui/rl_runs/stom_1s_2025_sb3_50k --n-folds 6
py -3.11 -m stom_rl.performance_leaderboard --sb3-smoke-reports auto

# DB 스키마 확인 (PowerShell quoting 안전 버전)
py -3.11 -c "import sqlite3; c=sqlite3.connect('_database/stock_tick_back.db'); print([r[1] for r in c.execute('PRAGMA table_info([247540])')])"

# 테스트 (PowerShell은 pytest glob을 자동 확장하지 않으므로 파일 목록을 먼저 만든다)
$stomRlTests = (Get-ChildItem .\tests -Filter 'test_stom_rl_*.py').FullName
py -3.11 -m pytest $stomRlTests -q

# lint (2026-05-25 현재 known issue: stom_rl 일부 unused import 및 비-STOM 테스트 E402가 남아 실패할 수 있음)
py -3.11 -m ruff check stom_rl $stomRlTests
```

### 7.3 제약/관례 (반드시 준수)
- 마무리는 **일반 git commit**(ultragoal checkpoint 금지), 커밋 메시지는 한글로 자세히.
- v2 SPA 수정 시 `webui/v2_src/src/`만 수정 → `npm run build`로 dist 갱신, SSR marker `kronos-v2-shell` 보존, `/api/*` 신규 금지.
- `webui/rl_runs/*`는 gitignore(런타임 산출물). 커밋 대상 아님.
- 조건식 평가는 `eval` 금지 — AST/화이트리스트 파서로 안전하게.
- 운영/확인 포트는 5070, `/rl` 기준.

### 7.4 새 대화 시작 프롬프트(붙여넣기용)
```text
D:\Chanil_Park\Project\Programming\Kronos 에서 이어서 진행합니다. 브랜치 feature/stom-rl-lab.
먼저 docs/stom_rl_portfolio_design_handoff_2026-05-25.md 와 docs/reference/stom_ai_agent/ 를 읽으세요.

목표: 단일 종목 OHLCV RL을, 조건식(STOM 변수)으로 후보를 거른 뒤 자본금으로 여러 종목을
동시에 사고팔며 총자산(NAV)을 키우는 포트폴리오 RL로 단계적으로 확장합니다.

단계 로드맵(문서 5장): 0)실행 명령 보정(완료) 1)feature 확장 2)자본금/사이징
3)조건식 스크리너 4)PortfolioEnv+RL 5)walk-forward 검증 6)risk gate/paper.

지금은 [단계 N]부터 진행해주세요. 제약: 일반 git commit(한글), webui /api 신규 금지,
rl_runs는 gitignore, 조건식은 eval 금지·AST 화이트리스트 파서.
```

---

## 8. 진행 현황 (2026-05-25 기준)

> 아래 표가 **단일 기준(single source of truth)** 이다. 이전 버전에 있던 "feature 확장 0% / 전체 약 2%" 표는 stale이라 삭제했다.
> 검증 근거: 신규 테스트 14개 통과(`14 passed in 7.37s`), smoke 산출물 3종 생성(`.omx/artifacts/*`), 아키텍트 재검토 APPROVE.

| 페이지 | 상태 | 핵심 산출물 | 검증 근거 |
|:--:|:--:|---|---|
| 0. 단일 종목 RL 플랫폼 | ✅ 100% | env/SB3/eval-only/walk-forward/대시보드 | `stom_rl/trading_env.py`, `tests/test_stom_rl_*.py` |
| 0a. Hygiene/명령 보정 | ✅ 100% | ruff unused import 정리, PowerShell pytest/DB 확인 명령 보정 | `baselines.py`, `episode_manifest.py`, `leaderboard.py` |
| 1. feature 확장 | ✅ 100% | canonical feature mapping/helper, env configurable feature columns | `finetune/qlib_stom_pipeline.py`, `stom_rl/trading_env.py`, `tests/test_stom_rl_feature_expansion.py` |
| 2. 자본금/사이징 | ✅ 100% | cash/holding/NAV 회계 일원화, NAV 보존 invariant 테스트 | `stom_rl/accounting.py`, `tests/test_stom_rl_accounting.py` |
| 2.5. PortfolioEnv 계약 spike | ✅ 100% | fixed top-K, max_positions, candidate/holding mask, discrete action layout | `stom_rl/portfolio_env.py`, `tests/test_stom_rl_portfolio_env.py` |
| 3. 조건식 스크리너 | ✅ 100% | AST whitelist evaluator, 금지 토큰/unknown variable/sell-only guard, candidate schema | `stom_rl/condition_screener.py`, `tests/test_stom_rl_condition_screener.py` |
| 4. PortfolioEnv + RL smoke | ✅ 100% | synthetic candidate 기반 deterministic smoke runner | `stom_rl/portfolio_train.py`, `tests/test_stom_rl_portfolio_train.py` |
| 5. portfolio walk-forward | ✅ 100% | contiguous fold split, no-trade/equal-weight/buy&hold/rule baseline report | `stom_rl/portfolio_walk_forward.py`, `tests/test_stom_rl_portfolio_walk_forward.py` |
| 6. risk gate / paper replay | ✅ 100% | max DD/연속손실/일일거래/비중 cap reason code, read-only replay | `stom_rl/risk_gate.py`, `stom_rl/paper_replay.py`, `tests/test_stom_rl_risk_gate.py`, `tests/test_stom_rl_paper_replay.py` |

**진행률 요약**

- 포트폴리오 전환 엔지니어링(페이지 1~6) 기준: **100%** — 구현·테스트·smoke 산출물 완료.
- 최종 목적(실제 DB 기반 수익성 RL) 기준: **약 55~60%** — 실제 DB 실행·알고리즘/보상 설계·full walk-forward·성능 최적화가 남음 (상세는 12장 및 `docs/stom_rl_rl_execution_research_plan_2026-05-25.md`).
- 다음 시작점은 **페이지 7(실제 STOM DB feature export dry-run)** 이다. 페이지 1~6은 재구현 대상이 아니다.

---

## 9. 한 줄 결론

목표(자본금 → 조건식 후보 → 다종목 동시매매 → 총자산 성장)는 **타당하고 현실적**이다.
다만 현재 단일 종목·9변수·기간민감 상태에서 바로 포트폴리오로 점프하면 검증이 불가능하므로,
**단계 1(feature 확장)부터 쌓아 4(PortfolioEnv)로 확장**하는 경로를 권장한다.
조건식 문법·변수는 `docs/reference/stom_ai_agent/`를 단일 진실 공급원으로 삼는다.

---

## 10. 부록 A — 단계(페이지)별 상세 실행 계획

> 각 단계를 독립된 "페이지"로 보고, 목표 · 입력/출력 · 신규/수정 파일 · 작업 체크리스트 · 데이터/스키마 · 완료 기준 · 테스트 · 예상 규모 · 위험을 정의한다. 페이지마다 관련 `pytest`를 통과시키고, `ruff`는 현재 known issue를 먼저 정리하거나 해당 페이지 범위의 신규 오류가 없음을 확인한 뒤 한글 git commit으로 닫는다.

### 페이지 0 — 핸드오프/실행 명령 보정 (완료)

- **목표**: 새 대화의 작업자가 문서 명령을 그대로 복사해 최소 검증을 재현할 수 있게 한다.
- **반영 내용**: PowerShell용 pytest 파일 목록 생성, DB schema 확인 quoting 보정, 현재 `ruff` 실패를 known issue로 명시.
- **검증 근거**: 보정된 pytest 방식으로 `tests/test_stom_rl_*.py` 32개 테스트 통과 확인.
- **남은 위험**: `ruff`는 아직 코드 미사용 import/일부 테스트 E402로 실패 가능하므로, 페이지 1 착수 전 정리하면 이후 검증 비용이 낮아진다.

### 페이지 1 — Feature 확장 (단일 종목 신호 강화)

- **목표**: 현재 9개 feature(시장 원천 6 + 포지션 파생 3)에 수급·호가 변수를 더해 단일 종목 RL의 정보량을 늘린다.
- **입력 → 출력**: STOM DB/qlib export → 확장 feature가 포함된 episode CSV → `trading_env` 관측.
- **추가할 feature (목표 +8, 총 ~17개)**:

  | feature | 정의 | 그룹 |
  |---|---|---|
  | `호가불균형` | 매수총잔량 / (매수총잔량+매도총잔량) | 호가 |
  | `호가스프레드` | (매도호가1−매수호가1) / 호가단위 | 호가 |
  | `체결강도` | 매수수량/매도수량×100 (0~500) | 수급 |
  | `체결강도평균대비` | 체결강도 / 체결강도평균(N) | 수급 |
  | `초당매수수량`, `초당매도수량` | 1초 누적 매수/매도 수량 | 수급 |
  | `순매수수량` | 초당매수수량 − 초당매도수량 | 수급 |
  | `거래대금각도` | 당일거래대금 기울기(0~90) | 모멘텀 |

- **신규/수정 파일**:
  - 수정: export 파이프라인(`finetune/`의 qlib export 코드) — DB의 추가 컬럼을 CSV로 내보내기.
  - 수정: `stom_rl/trading_env.py` — `BASE_MARKET_COLUMNS`/`feature_columns`에 신규 컬럼 추가 + 정규화 처리(스케일이 큰 잔량/금액은 비율·로그·z-score).
  - 수정: `stom_rl/episode_manifest.py` — 신규 컬럼 존재 검증.
- **작업 체크리스트**: ① export에 컬럼 추가 → ② env feature 확장 + 정규화 → ③ 결측/이상치 처리 → ④ check_env 통과 → ⑤ 50k 재학습 → ⑥ 100ep eval-only + walk-forward로 기존 9-feature 모델과 비교.
- **완료 기준**: 확장 feature 모델이 walk-forward folds_positive·평균 net에서 기존 대비 **개선**(또는 개선 없음을 데이터로 확인).
- **테스트**: `tests/test_stom_rl_trading_env.py`에 신규 feature 차원·정규화 단위 테스트 추가.
- **예상 규모**: 중소 (export 재실행 시간 포함). **위험**: 잔량/금액 스케일 정규화 실패 시 학습 불안정 → 비율화 우선.

### 페이지 2 — 자본금 + 포지션 사이징

- **목표**: 정규화 equity(1.0)를 **실제 자본금(현금+평가액)** 으로 일반화하고, 0/1 포지션을 비중으로 확장.
- **신규/수정 파일**:
  - 신규/수정: `stom_rl/accounting.py`(가칭) — `cash`, `position_qty`, `avg_entry_price`, `holdings_value`, `nav`, `realized_pnl`, `cost_paid`를 한 곳에서 계산.
  - 수정: `stom_rl/baselines.py` `AccountState` — 공용 accounting 모듈을 사용하도록 축소/위임. `apply_action(action, weight)` 로 비중 매수/부분 매도 지원.
  - 수정: `stom_rl/trading_env.py` — 내부 `position/entry_price/realized_return` 회계를 공용 accounting 모듈로 대체. action_space `Discrete(3)` → `Discrete(N)`(예: 0=hold, 1=25%, 2=50%, 3=100% 매수, 4=전량매도) 또는 비중 Box. 상태에 `cash_ratio`, `position_weight` 추가.
- **데이터/스키마**: `nav = cash + Σ(보유수량 × 현재가)`, 거래 시 `cost = 거래금액 × (cost_bps/10000)`.
- **완료 기준**: 단일 종목에서 초기자본 ₩N → NAV 곡선이 정상 추적되고, 비중 행동이 회계와 일치(단위 테스트).
- **테스트**: `tests/test_stom_rl_account_sizing.py` — 매수/부분매도/전량매도 후 cash·nav·position_weight 일치 검증.
- **예상 규모**: 중. **위험**: 부분 매도 평단가·실현손익 회계 버그 → 단위 테스트로 고정.

### 페이지 3 — 조건식 스크리너 (후보 종목 생성)

- **목표**: STOM 매수 조건식을 DB에 적용해 **시점별 매수 후보 종목 리스트**를 산출한다.
- **신규 파일**: `stom_rl/condition_screener.py`
  - `SafeExpr` — `ast` 기반 화이트리스트 평가기(`forbidden.md` 준수: `import/exec/eval/open/compile/__` 금지, 화이트리스트 변수·연산자만 허용).
  - `load_strategy(path)` — `docs/reference/stom_ai_agent/` 형식의 매수전략 텍스트 파싱.
  - `screen(db, strategy, at_time)` → 조건 통과 종목코드 리스트 + 그 시점 feature.
- **데이터/스키마**: 입력=STOM DB 종목별 1초 테이블, 시점(시분초). 출력은 포트폴리오 env가 그대로 읽을 수 있게 아래 형태로 고정한다.

  | 컬럼 | 설명 |
  |---|---|
  | `timestamp` | 조건 평가 시각 |
  | `symbol` | 종목코드/테이블명 |
  | `condition_id` | 조건식 버전/파일 식별자 |
  | `passed` | 조건 통과 여부 |
  | `rank_score` | 후보 top-K 정렬 점수(초기엔 거래대금/체결강도 등 rule score) |
  | `feature...` | PortfolioEnv 후보 슬롯에 들어갈 수급·호가·가격 feature |

  금지: 미래 시점 feature/수익률 누수, 임의 `eval`, whitelist 외 변수.
- **완료 기준**: WideV1/V2 조건식을 특정 일자에 적용 → 후보 리스트가 재현 가능하고, 금지 토큰은 거부됨.
- **테스트**: `tests/test_stom_rl_condition_screener.py` — ① 화이트리스트 외 이름/금지 토큰 거부 ② 예제 조건식이 알려진 종목을 통과/차단.
- **예상 규모**: 중. **위험**: `eval` 유혹 → 반드시 AST 파서. DB 29.7GB 풀스캔 비용 → 시점/종목 인덱스로 제한.

### 페이지 4 — PortfolioEnv + RL (핵심 재설계)

- **목표**: 자본금으로 조건식 후보 중 여러 종목을 동시 매매하며 NAV를 키우는 환경.
- **신규 파일**: `stom_rl/portfolio_env.py`, 학습 러너 `stom_rl/portfolio_train.py`.
  - **상태**: `[현금비율, NAV 변화율, 보유 슬롯(max_positions)별(수익률·보유시간·비중·feature), 후보 슬롯(top_k_candidates)별 feature, candidate_mask, holding_mask]`. SB3 호환을 위해 항상 고정 shape로 padding한다.
  - **행동**: 초기 버전은 `Discrete`로 제한한다. 예: `0=hold`, `1..K=후보 i 25% 매수`, `K+1..2K=후보 i 50% 매수`, 그 이후 `보유 j 전량/부분 매도`. invalid action은 mask로 차단하거나 penalty로 기록한다.
  - **보상**: `Δnav − 비용 − 슬리피지 − risk_penalty`. 종료 시 final NAV, MDD, 거래비용을 summary artifact에 남긴다.
  - **제약**: 현금 한도, 동시 보유 ≤5~10, 종목당 비중 상한, 일일 거래횟수 상한.
- **완료 기준**: 소수 종목(≤5) 동시 보유 학습/평가가 돌고, NAV 곡선·거래 로그·live event가 생성됨.
- **테스트**: `tests/test_stom_rl_portfolio_env.py` — 회계 보존(현금+평가액=nav), 제약 위반 방지, check_env(가능 시).
- **예상 규모**: **대**. **위험**: 행동공간·신용할당 → 조건식으로 후보 축소 + 단순 사이징부터, 점진 확대.

### 페이지 5 — 포트폴리오 walk-forward 검증

- **목표**: 포트폴리오 NAV를 기간 분할로 검증해 과적합/레짐 의존을 판별.
- **신규/수정 파일**: `stom_rl/portfolio_walk_forward.py`(기존 `walk_forward.py` 패턴 재사용) + 기준선(buy&hold, 동일가중, 무거래).
- **완료 기준**: 여러 기간에서 일관되게 기준선 초과 + 비용·MDD 게이트 통과(또는 미달을 데이터로 확인).
- **테스트**: fold 분할·기준선 계산 단위 테스트.
- **예상 규모**: 중.

### 페이지 6 — Risk gate + Paper replay

- **목표**: 실전 직전 안전장치와 read-only 시뮬레이션.
- **신규 파일**: `stom_rl/risk_gate.py`(Max DD·연속손실·일일거래한도·종목당 비중상한), `stom_rl/paper_replay.py`(실주문 없는 시점별 재생).
- **완료 기준**: 위험 한도 내에서만 매매, paper replay가 과거 데이터로 NAV를 재현.
- **테스트**: gate 트리거 단위 테스트.
- **예상 규모**: 중.

### 대시보드 반영 (각 페이지 공통, 선택)

- 포트폴리오 run도 `webui/rl_runs/`에 sb3 형식 또는 신규 artifact로 남기면 RL Lab 화면 run 목록에 노출된다.
- 전용 뷰(포트폴리오 NAV·보유종목·후보)는 `webui/v2_src/src/`만 수정 → `npm run build`, `/api/*` 신규 금지, SSR marker 보존 원칙 준수.

### 의존 관계 요약

```
페이지1(feature) ─┐
페이지2(자본/사이징) ─┼─→ 페이지4(PortfolioEnv) ─→ 페이지5(검증) ─→ 페이지6(risk/paper)
페이지3(조건식 스크리너) ─┘
```
페이지 1·2·3은 비교적 독립적이라 병행 가능하고, 4는 1·2·3을 모두 입력으로 받는다.

---

## 11. Ralph 실행 완료 기록 (2026-05-25)

### 페이지별 완료 산출물

| 페이지 | 상태 | 산출물 | 검증 |
|---:|:--:|---|---|
| 0b | ✅ 완료 | ruff unused import 정리 | `py -3.11 -m ruff check ...` green |
| 1 | ✅ 완료 | `STOM_RL_CANONICAL_FEATURES`, `build_stom_rl_feature_frame`, env configurable features | `tests/test_stom_rl_feature_expansion.py` |
| 2 | ✅ 완료 | `PortfolioAccount`, `PositionLot`, `TradeFill` | `tests/test_stom_rl_accounting.py` |
| 2.5 | ✅ 완료 | fixed-slot PortfolioEnv contract, masks, action layout | `tests/test_stom_rl_portfolio_env.py` |
| 3 | ✅ 완료 | safe AST condition screener, CSV/JSONL candidate writer | `tests/test_stom_rl_condition_screener.py` |
| 4 | ✅ 완료 | `portfolio_train --smoke` artifact runner | `.omx/artifacts/portfolio_train_smoke/*` |
| 5 | ✅ 완료 | portfolio walk-forward fold/baseline report | `.omx/artifacts/portfolio_walk_forward_smoke/*` |
| 6 | ✅ 완료 | read-only paper replay + risk trigger logs | `.omx/artifacts/paper_replay_smoke/*` |

### smoke 명령 (PowerShell, 복사 실행용)

> 출력 경로는 `.omx\artifacts\...` 이다(이전 문서의 `.omx\artifacts` 오타 수정). 모든 플래그는 실제 argparse와 일치한다.

```powershell
py -3.11 -m stom_rl.portfolio_train --smoke --output-dir .omx\artifacts\portfolio_train_smoke --max-steps 6 --top-k-candidates 2 --max-positions 1
py -3.11 -m stom_rl.portfolio_walk_forward --output-dir .omx\artifacts\portfolio_walk_forward_smoke --n-folds 2 --max-steps-per-fold 4
py -3.11 -m stom_rl.paper_replay --read-only --output-dir .omx\artifacts\paper_replay_smoke --max-steps 6 --max-daily-trades 1
```

### 산출물 파일 (생성 확인됨)

- `portfolio_train_smoke/`: `portfolio_train_summary.json`, `nav.csv`, `trades.csv`, `actions.csv`, `blocked_actions.json`
- `portfolio_walk_forward_smoke/`: `portfolio_walk_forward_report.json`, `portfolio_walk_forward_folds.csv`
- `paper_replay_smoke/`: `paper_replay_summary.json`, `nav.csv`, `decisions.csv`, `risk_triggers.json`

### 다음 단계 주의

1. 실제 29.7GB STOM DB/조건식 적용은 별도 feature export·condition screener full-scale 실행이 필요하다(연구계획 Page 7~9).
2. 페이지 5의 performance target(baseline 초과)은 별도 성능 목표다: fold별 수익률, MDD, turnover, 거래횟수 리포트로 판단한다(엔지니어링 완료 ≠ alpha 달성).
3. dashboard 연결은 core artifact schema가 안정화된 뒤 별도 UI 작업으로 진행한다.

---

## 12. 강화학습 실행 연구 판단 문서

상세 문서: `docs/stom_rl_rl_execution_research_plan_2026-05-25.md`

핵심 결론:

- 조건식을 강화학습이 직접 생성하는 구조는 초기 단계에서 비추천한다.
- STOM DB 변수와 파생 feature를 RL state로 넣는 것이 더 정석적이다.
- 조건식은 후보 종목 universe/top-K를 줄이는 screener/filter로 사용한다.
- RL은 후보 중 매수/매도/보유/사이징과 청산 타이밍을 학습한다.
- 조건식 자동 생성은 Page 7~14 안정화 이후 별도 Page 15 연구로 분리한다.

현재 연구는 실제 DB 기반 강화학습 실행 준비에는 충분하지만, 최종 수익성 있는 RL 전략 완성에는 실제 DB 실행, 후보 CSV 생성, 알고리즘/보상 연구, full walk-forward, paper replay, 성능 최적화가 추가로 필요하다.
