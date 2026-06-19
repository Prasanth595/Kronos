# STOM 강화학습 포트폴리오 — 종합 연구보고서

- 작성일: 2026-05-27
- 브랜치: `feature/stom-rl-lab`
- 성격: **전체 여정 종합 + 노하우 + 검증된 인프라 인벤토리 + 다음 연구 재시작 준비 문서**
- 전제: 이 RL 실험실은 **Kronos 예측 모델과 독립**. 조건식 문법/변수만 `docs/reference/stom_ai_agent/`를 단일 진실 공급원으로 참고.

---

## 0. Executive Summary (결론 먼저)

1. **엔지니어링은 완성됐다.** 실데이터(STOM 1초봉 29.7GB DB) → feature export → 다종목 시간동기화 panel → 조건식 후보 → 포트폴리오 env(T+1 체결·비용인지 reward) → **실제 SB3 deep-RL 학습** → **train/test holdout(n_folds≥5)** → shuffle/누수 가드 → supervised-ranker 비교 → read-only paper replay → 실시간 대시보드까지, **검증된 전 과정 파이프라인**이 존재한다. (테스트 150 passed, Architect THOROUGH APPROVE)

2. **그러나 알파(수익)는 없다 — 비자문(non-advisory)으로 엄정히 증명됐다.** 111개 co-dated 종목·n_folds=5·비용 25bps·shuffle 테스트 하에서, 학습된 PPO도, 단순 supervised ranker도 **"아무것도 안 하기(no_trade)"를 이기지 못한다.** 명목상의 fold 우세는 shuffle에서 붕괴한다. **병목은 알고리즘이 아니라 신호/데이터다.**

3. **그래서 deep-RL을 이 데이터로 더 파는 것은 가치가 없다(STOP).** 알파를 계속 추구하려면 **알고리즘이 아니라 신호를 바꿔야** 한다(보유 horizon 확대, feature/데이터 확장). 자세한 로드맵은 §7.

4. **인프라 충분성: 충분하다.** 재시작에 필요한 모든 코어 모듈이 구축·검증돼 있어, 다음 연구는 "처음부터"가 아니라 "신호/데이터 레이어 교체 + 기존 평가 하니스 재사용"으로 시작할 수 있다. 상세 §6.

> 한 줄: **"수익 모델 완성"이 아니라 "이 데이터에 거래 가능한 알파가 없음을, 거짓양성 없이 증명하는 신뢰성 있는 연구 인프라 완성"** 이 이번 성과다.

---

## 1. 프로젝트 목표

초기 자본금에서 시작해, 조건식에 걸린 여러 종목을 후보로 받아 동시에 사고팔며 총자산(NAV)을 키우는 **포트폴리오 강화학습**. 시간 조절(매수/매도/보유시간)을 RL이 학습한다. 조건식은 후보 universe를 좁히는 screener로 쓰고(RL이 직접 생성하지 않음), RL은 후보 중 선택·비중·청산을 학습한다.

---

## 2. 전체 여정 (단계별, 모두 커밋·검증)

### 2.1 Stage 1 — 단일 종목 RL 플랫폼 (기반)
- 단일 종목 1초봉 trading env, SB3 DQN/PPO 학습, eval-only, walk-forward, baseline/bandit/cost-gate, 대시보드.
- **결과**: 50k DQN이 100 episode에서 +1.34% vs buy&hold +0.51% — 약간 초과하나 **regime-sensitive**, 50k→100k 개선 없음. (안정적 수익 아님)
- 베이스라인 커밋 `06e1038` (전체 정리 + 문서 mojibake/진행률 모순 수정 포함).

### 2.2 Stage 2 — 포트폴리오 RL 엔지니어링 (Page 7~16)
| Page | 내용 | 커밋 |
|---|---|---|
| 7 | 실데이터 `export-stom-rl` 경로 (14 canonical feature) | `c18e0e6` |
| 7.5 | 다종목 1초 시간동기화 panel (`merge_asof` backward, 누수 가드) | `843a0f5` |
| 8 | 조건식 → AST whitelist rule JSON (WideV1/V2/호가압력) | `f791e99` |
| 9 | candidate CSV + **T+1 체결 계약**(price@T / fill_price@T+1) + rank per-symbol | `21405d3` |
| 10 | env 체결 T+1 수정 + 결정론 학습 smoke | `7107d24` |
| 10.5 | thin-slice 조기 성능 read (go/no-go) | `2464d55` |
| 11 | walk-forward **expanding-window holdout** + leakage canary | `2709c7c` |
| 12 | paper replay (read-only, blocked-action reason codes) | `709d106` |
| 13 | 포트폴리오 run 대시보드 연결 (신규 /api 없이) | `95ff7f8` |
| 14 | 성능 최적화(트랙 B) — 비용 격차 문서화 | `3401730` |
| follow-up A | 종목코드 선행 0 strip 수정 (`000250` 보존) | `7fe3581` |
| 16 | full-universe 실행 하니스 (per-session checkpoint/resume) | `0a9a67e` |
| 17 | cost-aware 정책 실험 (train-fit/test-eval) | `b09857f` |
| live | 포트폴리오 step별 live event + 대시보드 follow/replay | `fca9e85` |

### 2.3 Deep-RL 단계 — 실제 학습형 모델 + 정직한 판정
| 단계 | 내용 | 커밋 |
|---|---|---|
| C-0 | DB feature 가용성 probe (등락율/시가총액/고저평균/체결강도 실재 ≥99.84%) | `fe632cb` |
| C | canonical feature 14→18 확장 | `3976403` |
| A | `PortfolioEnv` → Gymnasium 어댑터 (check_env 통과, `action_masks()`) | `84c91e9` |
| B | 실제 SB3 PPO 학습(결정론 핀) + `trained_ppo` seam 배선 + `supervised_ranker` | `d2104cc` |
| E | 정직한 2트랙 verdict | `dd5fd7a` |
| D | **ranker-first 비자문 신호검정** (n_folds=5, 111종목) + shuffle 테스트 구현 | `ca74c78` |

---

## 3. 핵심 발견 (정직한 과학적 결과)

### 3.1 비자문 신호검정 (가장 결정적)
세션 2022-08-30, **111개 co-dated 종목**, n_folds=5, 11,336 후보, cost_bps=25:

| 정책 | 평균 수익% |
|---|---|
| no_trade | **0.000** |
| equal_weight / buy&hold | −0.121 |
| supervised_ranker | −0.147 |
| rule_baseline | −1.416 |

- ranker가 equal_weight도 no_trade도 **못 이김.** 명목 3/5 fold 우세는 **shuffle(rank_score+feature overwrite)에서 1~2/5로 붕괴** → 노이즈.
- M=1(다중가설 보정 불요), ≥2-seed 일치, disjoint holdout·누수 canary·shuffle 전부 PASS.

### 3.2 학습형 RL (advisory, 소규모)
- trained PPO −1.55% ≤ ranker −0.10% ≤ no_trade 0%. PPO는 과회전으로 손실.
- **invalid-action 96.9%** → 마스킹 없는 PPO는 대부분-무효 행동공간을 못 배움 → MaskablePPO 필요(트리거 발동). 단, ranker도 못 이기므로 **알고리즘 교체로 해결될 문제가 아님.**

### 3.3 종합 해석
- **병목 = 신호/데이터.** 1초 개장 구간의 churn은 거래비용(25bps)에 묶여 있고, 단순 supervised 모델조차 selection 엣지가 없다.
- supervised_ranker가 **equal_weight로 퇴화**(byte-identical)한 것이 무신호의 추가 증거.

---

## 4. 노하우 / 방법론 교훈 (재사용 가치 최상)

이번 연구의 진짜 자산은 "수익 모델"이 아니라 **거짓 알파를 만들지 않는 신뢰성 있는 검증 방법론**이다.

### 4.1 정직성 설계 (가장 중요)
- **2트랙 분리**: 엔지니어링(게이트 가능) vs 알파(연구 결과, 미보장). "문서화된 음성"도 정당한 완료.
- **거짓 알파 방지(다중가설/과탐색)**: ① 1차 config + 후보 config 집합을 결과 보기 전 **pre-register** ② 시도 수 `M` 기록 + Bonferroni/BH 보정 ③ **n_folds≥5 power floor** — 미만이면 알파 "주장 금지"(advisory-only). 작은 N에서 "과반 fold 우세"는 동전던지기임을 정량적으로 차단.
- **shuffle/permutation 테스트**: rank_score AND 모든 feature를 timestamp 내 overwrite-shuffle → 선택 신호 파괴 후에도 엣지가 남으면 그건 누수/데이터마이닝. (이게 명목 3/5 우세를 깨뜨림)
- **supervised-ranker를 falsifiable floor로**: "RL이 단순 ranker도 못 이기면 RL 포기" — "왜 RL인가"를 경험적으로 검증. RL의 정당성 자체를 falsifiable하게.

### 4.2 누수(look-ahead) 차단
- **T+1 체결 계약**: 결정=bar close@T, 체결=차기봉(T+1) `fill_price`. env가 같은 봉 체결하던 버그 수정.
- **as-of backward join**: `merge_asof(direction="backward")` — 관측 없으면 NaN, 미래값 절대 fill 금지.
- **expanding-window holdout**: fold N 학습 → disjoint·strictly-later fold N+1 평가. 런타임 hard guard.
- **leakage canary(2종)**: ① 미래 컬럼 주입 시 결과 불변(backward-only 증명) ② fill_price 손상 시 결과 변동(canary가 실제로 누수를 잡음). + **어댑터-레벨 canary**(SB3 wrapper 별도).
- **causal feature**: trailing 윈도우(예 trade_strength_avg_n)는 ≤T만 사용, 미래행 추가에도 불변.

### 4.3 데이터/환경 노하우
- **인코딩**: DB 한글 컬럼은 **UTF-8**(cp949 아님). 콘솔 표시 깨짐은 artifact일 뿐.
- **종목코드 선행 0**: `000250`은 int 파싱 시 `250`으로 깨짐 → `symbol_norm` 헬퍼(전자리수만 zfill(6))로 보존. DB 테이블명 매칭에 필수.
- **종목별 기록일 disjoint**: cross-symbol panel은 **같은 세션일 공유 종목**으로만 구성. (co-dated가 아니면 전부 NaN)
- **n_folds는 시간축 분할**: 종목 수가 아니라 시간창을 넓혀 n_folds≥5 달성 가능(full-universe 없이도 비자문 검정 가능 — 이번 핵심 통찰).
- **gate-up scale**: smoke fixture → 1종목 30분 → 소수 종목 → full. DB 풀스캔 금지.

### 4.4 학습 재현성
- **결정론 핀**: `torch.use_deterministic_algorithms(True)`, `set_num_threads(1)`, `device=cpu`, 시드 고정, `atol=1e-6/rtol=1e-5` 재현 검증.
- **action masking**: 포트폴리오 행동공간은 대부분-무효 → 마스킹 없는 PPO는 비효율. `action_mask()` → 어댑터 `action_masks()` → (필요 시) MaskablePPO.

### 4.5 운영 제약 (지킴)
- 일반 git commit(한글), 조건식 `eval` 금지(AST whitelist), webui 신규 `/api` 금지·SSR marker 보존, `rl_runs`/`.omx` 비커밋, `py -3.11`(기본 3.13은 gymnasium/sb3 미설치).

---

## 5. (의도적으로 미실행) Stage D full-universe
- full-universe(2427종목) **multi-hour RL 학습**은 실행하지 않았다. 이유: 비자문 신호검정이 **음성**이라(단순 ranker조차 엣지 없음) ROI가 없음. 하니스(`full_universe.py`)는 검증·준비됨 — 신호 방향이 바뀌면 즉시 launch 가능(`nohup … full_universe --resume &`).

---

## 6. 검증된 인프라 인벤토리 (재시작 준비 상태)

> **질문 답변: 인프라는 충분하다.** 다음 연구는 신호/데이터 레이어만 교체하고 아래를 재사용하면 된다.

### 6.1 데이터 레이어 ✅
| 모듈 | 기능 | 상태 |
|---|---|---|
| `finetune/qlib_stom_pipeline.py` `export-stom-rl` | DB → 18 canonical feature CSV (UTF-8, 결측/스케일 처리) | ✅ |
| `stom_rl/panel_join.py` | 다종목 as-of(backward) 시간동기화 panel + 메모리 산식 | ✅ |
| `stom_rl/candidate_gen.py` | panel+rule → candidate CSV (T+1 fill, per-symbol rank) | ✅ |
| `stom_rl/condition_screener.py` | AST whitelist 조건식 평가 (eval 금지) + rule JSON | ✅ |
| `stom_rl/full_universe.py` | per-session enumeration + checkpoint/resume 러너 | ✅ |
| `stom_rl/symbol_norm.py` | 종목코드 정규화(zfill6) | ✅ |

### 6.2 환경·회계 ✅
| 모듈 | 기능 |
|---|---|
| `stom_rl/portfolio_env.py` | fixed top-K/Discrete, action_mask, **T+1 fill**, **cost-aware reward(λ·turnover)**, invalid penalty |
| `stom_rl/accounting.py` | cash/holding/NAV 회계 invariant |
| `stom_rl/risk_gate.py` | max DD/연속손실/일일거래/비중 cap |

### 6.3 학습 ✅
| 모듈 | 기능 |
|---|---|
| `stom_rl/portfolio_sb3_adapter.py` | PortfolioEnv→Gymnasium (check_env 통과, `action_masks()`) |
| `stom_rl/portfolio_sb3_train.py` | 실제 SB3 PPO/DQN 학습 + 결정론 핀 + masked obs-decode PolicyFn |
| `stom_rl/sb3_smoke.py` | 단일종목 SB3 학습 scaffold (재사용 패턴) |

### 6.4 평가·검증 ✅ (가장 가치 높음)
| 모듈 | 기능 |
|---|---|
| `stom_rl/portfolio_walk_forward.py` | expanding-window **holdout** + 5종 baseline + **supervised_ranker** + **shuffle 테스트** + leakage canary + `_fit_policy`/`TRAINED_POLICY_FACTORIES` seam |
| `stom_rl/paper_replay.py` | read-only 재생 + blocked-action reason codes |

### 6.5 시각화 ✅
| 모듈 | 기능 |
|---|---|
| `stom_rl/rl_events.py` | step별 live event(NAV=equity) JSONL |
| `webui/rl_dashboard.py` + `RLLabTab.svelte` | `/rl` 대시보드 + 실시간 follow(1.5s)/replay |

### 6.6 테스트 ✅
- `tests/test_stom_rl_*.py` **150 passed** (py -3.11). 누수 canary·holdout·결정론·계약·shuffle 전부 포함.

### 6.7 다음 연구에 "추가로 필요한 것" (현재 없음)
- `sb3-contrib`(MaskablePPO) — **미설치**. 마스킹 RL이 필요해지면 `pip install sb3-contrib` (트리거는 이미 발동 기록됨).
- 새 신호 소스(분/일봉, 펀더멘털 등) — **이게 진짜 다음 작업**이지 인프라 부족이 아님.

---

## 7. 다음 연구 로드맵 (재시작 — RL이 아니라 신호 우선)

신호 부재가 증명됐으므로, 우선순위는 **알고리즘이 아니라 신호/데이터**다.

1. **보유 horizon 확대** — 1초 churn은 비용에 묶임. 분/시간/일 단위 의사결정으로 비용 장벽 회피. (env step/reward를 더 긴 horizon으로)
2. **신호/feature 확장** — 1초 호가 밖 신호: 분/일봉 기술지표, 펀더멘털, 섹터/시장 컨텍스트, 뉴스. C-0 패턴으로 가용성 먼저 probe.
3. **값싼 ranker로 신호 유무 먼저 검정** — 새 feature/horizon에서 `portfolio_walk_forward`의 supervised_ranker가 n_folds≥5·shuffle·비용 하에서 **equal_weight를 이기는지** 먼저 확인. (RL보다 100배 싸고, 이번에 만든 falsifiable floor)
4. **ranker가 엣지를 내면** → 그때 MaskablePPO(sb3-contrib) deep-RL 투입. 어댑터·seam·holdout 전부 준비됨.
5. **full-universe** — 신호가 확인된 뒤 `full_universe.py`로 전체 종목 백그라운드 검증.

> 원칙: **"알파를 못 이기면 멈춘다"는 게이트는 그대로 유지.** 이번에 만든 pre-registration·multiplicity·shuffle·ranker-floor가 다음 연구에서도 거짓양성을 막는다.

---

## 8. 부록

### 8.1 커밋 체인 (브랜치 feature/stom-rl-lab)
```
06e1038 baseline(Stage1+문서정리) → c18e0e6 P7 → 843a0f5 P7.5 → f791e99 P8 →
21405d3 P9 → 7107d24 P10 → 2464d55 P10.5 → 2709c7c P11 → 709d106 P12 →
95ff7f8 P13 → 3401730 P14 → 7fe3581 follow-upA → 0a9a67e P16 → b09857f P17(cost-aware) →
fca9e85 live events → fe632cb C-0 → 3976403 C(14→18) → 84c91e9 A(adapter) →
d2104cc B(SB3 train) → dd5fd7a E(verdict) → ca74c78 D(signal test+shuffle)
```

### 8.2 핵심 재현 명령 (py -3.11)
```powershell
# 전체 테스트
py -3.11 -m pytest tests/test_stom_rl_*.py -q          # 150 passed

# 신호검정 재현 (비자문, n_folds=5)
py -3.11 -m stom_rl.candidate_gen --db _database\stock_tick_back.db --tables <co-dated> --session <YYYYMMDD> --rules stom_rl\rules\buy_demand_pressure.json --output <csv>
py -3.11 -m stom_rl.portfolio_walk_forward --candidate-csv <csv> --n-folds 5 --output-dir <dir>   # + shuffle 옵션

# 대시보드
$env:KRONOS_WEBUI_PORT="5070"; $env:KRONOS_V2_DIST="1"; py -3.11 webui\run.py   # /rl
```

### 8.3 관련 문서
- 설계/핸드오프: `docs/stom_rl_portfolio_design_handoff_2026-05-25.md`
- 실행 연구계획: `docs/stom_rl_rl_execution_research_plan_2026-05-25.md`
- deep-RL 계획(합의): `.omx/plans/ralplan-stom-rl-deep-rl-2026-05-27.md`
- C-0 probe: `docs/stom_rl_page_c0_feature_probe_2026-05-27.md`
- cost-aware: `docs/stom_rl_cost_aware_policy_2026-05-26.md`
- deep-RL verdict: `docs/stom_rl_deep_rl_verdict_2026-05-27.md`
- 신호검정: `docs/stom_rl_signal_test_2026-05-27.md`

---

## 9. 한 줄 결론

**수익 모델은 아직 없다(이 데이터엔 알파가 없음을 엄정히 증명).** 그러나 **거짓 알파를 만들지 않는 신뢰성 있는 RL 연구 인프라는 완성됐고, 재시작 준비는 충분하다.** 다음은 알고리즘이 아니라 **신호/데이터(긴 horizon·풍부한 feature)** 를 바꿔, 값싼 ranker로 신호 유무를 먼저 검정한 뒤, 엣지가 확인되면 준비된 deep-RL 하니스로 진입하는 것이다.
