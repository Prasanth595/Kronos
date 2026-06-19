# STOM RL 랩 — 2026-05-29 세션 진행/재개 핸드오프 (최종: A→D 완료)

- 갱신일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab` / HEAD: `f159840`
- 상위 마스터 앵커: `docs/stom_rl_resume_commit_2026-05-29.md`
- 목적: 이 세션에서 완료한 Page A·RL트랙(R0/R1/R1b)·B·C·D를 다음 대화가 그대로 이어가게 한다.

---

## 0. 한 줄 현황

**이 환경에서 가능한 전체 로드맵(A→D)이 완료됐다.** 시초 갭상승 `ts_imb` **룰 전략(RULE, NOT RL)**은 백테스트에서 견고하게 검증됐고(전 universe·전 연도·최악체결·유동성·운영정책 replay 통과), **RL은 근거를 갖고 폐기**됐다. 남은 단계는 **실시간 피드가 필요한 진짜 forward(환경 밖)**와 **E broker(승인 전 금지)**뿐이다. **실거래 수익은 아직 0 — 전부 검증/시뮬레이션.**

---

## 1. 이 세션 커밋 (base `0402208` 위, 시간순)

| 커밋 | 내용 |
|---|---|
| `4a0937a` | Page A 사이징/리스크 설계 + RL 타당성 딥리서치(R0) |
| `dd039c8` | R1 oracle-exit 천장 테스트 |
| `f082992` | R1b 인과적 청산 baseline — 청산 RL 게이트 종결 |
| `2b069fa` | Page B full universe 재검증 PASS + 세션 핸드오프 |
| `cfa5fd5` | Page C 유동성/슬리피지 + gap-through 꼬리 (둘 다 PASS) |
| `f159840` | Page D 동결정책 paper replay + deadlock 수정 |

전체 게이트 테스트: **162 passed** (7개 파일). 각 페이지 code-reviewer APPROVE. (로컬 커밋만 — push 미실시.)

---

## 2. 핵심 결론 (정직성 가드레일: RULE strategy, NOT reinforcement learning)

1. **Page A** (`gap_up_risk_sizing.py`): `ts_imb`를 **f=10%/회·동시보유 3·일손실 -3%**로 사이징. 1R=계좌 0.123%, 최장연패 9에도 누적 -0.55~-1.1%, 계좌 MDD 순차 -1.6~-2.0%. Kelly 퇴화(full≈22배)라 낙폭 기준 사이징.
2. **R0 딥리서치** (105 에이전트 적대적 검증): 비용차감 OOS 수익 RL 사례 **0건**. RL은 알파원 아님.
3. **R1 천장 + R1b 인과 baseline** (`exit_oracle.py`/`exit_baselines.py`): 완전예지 청산 여지는 크나(capture 17.8%) 인과적으로 포착 불가 — 어떤 인과 변형도 고정 TP5/SL1 못 이김(IS최적 trail_1 OOS -0.71%, DSR 0.931<0.95). **→ 청산 RL(R3) 폐기.**
4. **Page B** (`gap_up_backtest.py --max-symbols 0`): full universe 2314종목·29139 instance. ts_imb 전 연도 양수, **2022 +0.742%로 해소**(소표본 노이즈 확정), breakeven OOS 98bp.
5. **Page C** (`liquidity_model.py`): 유동성 PASS — 1억 계좌 주문이 1초거래대금의 1.6%, 100% feasible, 슬리피지 <3bp. gap-through PASS — full-universe sl_gap_stress도 전 연도 양수(2022 +0.603), breakeven OOS 81bp. (단위 발견: `초당거래대금`은 **백만원** 단위 → ×1e6.)
6. **Page D** (`paper_sim.py`): 동결정책 시간순 replay. 정책 정상 작동·저낙폭(낙관/비관 체결 모두 양수, MDD -0.7~-3.1%). **deadlock 발견·수정**: 7연패 f=0 halt가 영구동결 → 서킷브레이커(쿨다운+streak 리셋). 헤드라인 수익(+396~612%)은 복리×replay 낙관 상한이지 미래 기대치 아님.

---

## 3. 페이지 로드맵 (최종)

| 페이지 | 상태 |
|---|---|
| A 사이징 / R0 딥리서치 / R1·R1b(RL 청산 폐기) / B full universe / C 유동성+꼬리 / D replay | ✅ **완료** |
| R2 메타라벨링(진입 필터) | ⬜ 선택·저우선(진입 알파 부재 이미 검증) |
| R3 offline RL 청산 | ❌ 폐기(R1b 게이트 실패) |
| **진짜 forward/paper (실시간 피드)** | ⬜ **다음 — 환경 밖**(실시간 데이터 연동 필요) |
| E broker/order 연동 | 🔒 명시 승인 전 금지 |

---

## 4. 재개 검증 + 산출물 지도

### 4.1 핵심 테스트 (기대: 162 passed)
```powershell
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_gap_up_dashboard_publish.py tests/test_stom_rl_gap_up_risk_sizing.py tests/test_stom_rl_exit_oracle.py tests/test_stom_rl_exit_baselines.py tests/test_stom_rl_liquidity_model.py tests/test_stom_rl_paper_sim.py -q
```

### 4.2 커밋된 핵심 모듈 (이 세션)
`gap_up_risk_sizing.py`(A) · `exit_oracle.py`(R1) · `exit_baselines.py`(R1b) · `liquidity_model.py`(C) · `paper_sim.py`(D). (기존: `gap_up_backtest.py`, `gap_up_dashboard_publish.py`.)

### 4.3 커밋된 문서 (이 세션, `docs/`)
`stom_rl_gap_up_risk_sizing_2026-05-29.md`(A) · `stom_rl_rl_feasibility_research_2026-05-29.md`(R0) · `stom_rl_oracle_exit_ceiling_2026-05-29.md`(R1) · `stom_rl_exit_baseline_2026-05-29.md`(R1b) · `stom_rl_gap_up_full_universe_2026-05-29.md`(B) · `stom_rl_liquidity_slippage_2026-05-29.md`(C) · `stom_rl_paper_replay_2026-05-29.md`(D) · 이 문서.

### 4.4 gitignored 산출물 (필요 시 재생성)
`.omx/artifacts/` 하위: `gap_up_full/`(B, idealized) · `gap_up_full_stress/`(C 꼬리, sl_gap_stress) · `oracle_exit/`(R1) · `exit_baselines/`(R1b) · `liquidity/`(C) · `paper_sim/`(D). 재생성 명령은 각 페이지 문서의 "재현 명령" 절 참조. (full-universe 백테스트는 ~수십분~장시간; UTF-8 강제 `py -3.11 -X utf8`.)

---

## 5. 다음 대화 첫 행동

1. 이 문서 + `docs/stom_rl_resume_commit_2026-05-29.md` 읽기.
2. `git branch --show-current`(feature/stom-rl-lab), `git log --oneline -8`, §4.1 테스트(기대 `162 passed`) 확인.
3. 진행 방향 결정:
   - **실전 지향이면**: 진짜 forward는 *실시간 시세 피드* 연동이 필요(과거 DB replay로는 근사까지만) → 환경/데이터소스 확인부터. 그 전엔 E(실주문) 금지.
   - **추가 검증이면**: R2 메타라벨링(진입 필터, 저우선) 또는 paper_sim 서킷브레이커를 "probe 사이즈 복귀"로 보수화하는 변형.
4. 모든 표현은 **"RULE strategy, NOT reinforcement learning"** 유지.

---

## 6. 정직성 가드레일 (불변)

- 갭상승 곡선을 RL이라 부르지 않는다. 누적은 비복리 per-trade % / fixed-notional; **paper replay 헤드라인(+수백%)은 복리×시뮬레이션 낙관 상한이지 미래 수익 예측이 아니다.**
- "실거래 준비 완료" 미선언. 실주문 전 진짜 forward(실시간) 필요. E는 명시 승인 전 금지.
- 2022 약세는 소표본 노이즈(idealized·stress 양쪽 대표본에서 +로 해소 확인). 레짐 붕괴 단정 금지.
- DB는 triggered-subset → 시장 전체 일반화 미입증. L2 큐포지션 없음 → 진짜 체결 realism 한계.
