# STOM RL 랩 — 마스터 재개(RESUME) 핸드오프 2026-06-01 (최신 앵커)

- 작성일: **2026-06-01 KST**
- 저장소: `D:\Chanil_Park\Project\Programming\Kronos` / 브랜치: `feature/stom-rl-lab` / HEAD: `7adc190` (**로컬만 — push 미실시**)
- **목적: 새 대화에서 이 문서 하나만 읽고 STOM RL 랩 전체를 그대로 이어간다.** 이전 앵커(`stom_rl_resume_handoff_2026-05-28.md`, `stom_rl_resume_commit_2026-05-29.md`, `stom_rl_session_progress_2026-05-29.md`)를 **대체**한다.
- 데이터(유일): `_database/stock_tick_back.db` — 1초봉, 개장 **09:00–09:30만**, 이벤트 트리거(희소), UTF-8 한글 컬럼, 종목코드 **선행 0 보존**. `초당거래대금`=**백만원 단위(×1e6)**. KRX 09:00봉은 단일가 동시호가 print(O=H=L=C, 거래량 ~30분 누적)이라 연속거래봉 취급 금지.

---

## 0. 한 줄 현황 (TL;DR)

**RL/딥러닝은 이 데이터에서 방향성 수익을 못 낸다 — 선택(shuffle 무알파)·타이밍(P1b NO-GO)·학습된 PPO 100k(전체 2,730ep서 buy-and-hold 미달) 전부 적대검정으로 닫혔다. 수익 축은 RL이 아니라 "시초 갭상승 ts_imb 룰 전략"이며, full universe·전 연도·최악체결·마켓에이블 스프레드·유동성·운영정책 replay까지 통과(마켓에이블 de-idealized +0.884%/trade). 1초봉은 "알파"가 아니라 "비용·리스크·체결 진실 레이어"로 확정. 현재 단 하나 살아있는 알파-인접 실험 = ① skip-gate(SL예측 게이트가 GO 줘서 빌드 정당화됨, 사전확률 ~20–30%, "드리프트 트랩" 가드 필수). 실거래 수익은 여전히 0 — 전부 백테스트/시뮬.**

---

## 1. 재개 프로토콜 (새 대화 첫 행동)

새 대화 첫 프롬프트:
```
D:\Chanil_Park\Project\Programming\Kronos 에서 이어서 진행.
docs/stom_rl_resume_handoff_2026-06-01.md 를 읽고 그 문서 기준으로 STOM RL 랩을 재개하세요.
정직성: RL 알파 부재는 검증 완료 — 갭상승 룰 곡선을 RL이라 부르지 마세요. 모든 양수치는 in-sample/triggered-subset/라이브 없음.
```
최소 확인:
```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
git branch --show-current      # feature/stom-rl-lab
git rev-parse --short HEAD      # 7adc190 또는 이후
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_sl_predictor.py -q   # 통과 확인
```
전체 게이트 스위트(14파일)는 **224 passed**(§6 명령).

---

## 2. 사용자 · 전략 · 비용 (불변)

- 한국 퀀트 트레이더(parkchanil77@naver.com). 전략 = **"시초 급등 / 9시 시초 갭 상승"**(opening gap-up momentum).
- 스펙: 진입 시초 `등락율` ≥ **2%**, 청산 **TP / SL 또는 09:25**. PRIMARY = **TP5% / SL1% / 09:25**.
- 실제 왕복비용 = **23bp**(매수 0.015% + 매도 0.015% + 증권거래세 0.20%). 비용은 flat 가산적: `net@c = net@25 + (25−c)/100`.
- universe = STOM 트리거 종목 = **사용자 실거래 대상과 일치**(배포 관점 편향 아님). 단 전체 시장 갭상승은 아님(일반화 미입증).
- 원했던 것: 유튜브 NEAT 영상처럼 "꾸준히 우상향 곡선", 실거래 직전 상태인지.

---

## 3. 진입 필터 정의 (`stom_rl/gap_up_backtest.py`)
- `none`: 2% 갭만. `ts`: 체결강도 ≥ 100. **`ts_imb`(주력): 체결강도 ≥ 100 AND 호가 imbalance(매수총잔량/(매수+매도)) ≥ 0.5.**
- 체결모드 `fill_mode`: `idealized`(정확레벨) / `realized`(실제 크로싱가) / `sl_gap_stress`(SL 관통 최악). + `marketable`(buy@ask/sell@bid, 스프레드 2회 — `marketable_fill.py`).

---

## 4. 전체 진행 맵 (무엇이 검정/완료됐나)

### 4-A. RL/딥러닝 트랙 — 전부 닫힘 (근거 있는 폐기)
| 게이트 | 결과 | 문서 |
|---|---|---|
| 교차종목 **선택** 알파 (shuffle null) | ❌ 1초·1분·세션 전부 shuffle 미통과 | `stom_rl_deep_rl_verdict_2026-05-27.md` |
| R0 딥리서치(105 에이전트) | ❌ 비용차감 OOS 수익 RL 사례 0건 | `stom_rl_rl_feasibility_research_2026-05-29.md` |
| R1 oracle-exit 천장 / R1b 인과 청산 | ❌ capture 17.8% 있으나 인과적 포착 불가, DSR 0.931<0.95 → 청산 RL 폐기 | `stom_rl_oracle_exit_ceiling_*`, `stom_rl_exit_baseline_*` |
| P0+P1 예측 프로브 | ⚠️ microstructure가 60s forward를 IC≈0.10로 예측(robust)하나 조건부 | `stom_rl_predictability_gate_2026-05-30.md` |
| **P1b 타이밍 게이트**(마켓에이블·paired) | ❌ **결정적 NO-GO** — 룰 고정 09:00보다 −0.38~−0.46%/trade 나쁨(N=5,173, DSR=0) | `stom_rl_timing_gate_2026-05-30.md` |
| **PPO 100k 전체 재평가**(2,730 ep) | ❌ avg +0.165%/ep, **median −0.276%**, hit 31%, MDD −74%, buy-and-hold(+0.513%) 미달, cost gate 미통과 — **소표본 +1.0% 환상 확정** | `stom_ppo_full_eval_2026-05-31.md` |

### 4-B. RULE 갭상승 트랙 — 검증 통과 (수익 축)
| 페이지 | 결과 | 문서 |
|---|---|---|
| 비용모델+필터+cost sweep | 필터 시 OOS 양수(첫 긍정) | `stom_rl_gap_up_cost_filter_2026-05-27.md` |
| 레짐/슬리피지 + 실비용 23bp | 매년·5경계 양수, ts_imb +0.9%/trade | `stom_rl_gap_up_regime_validation_*`, `..._realcost_2026-05-28.md` |
| 체결 de-idealization(fill_mode) | ts_imb 최악(sl_gap_stress) +0.811%/trade, breakeven 대비 ~4× | `stom_rl_gap_up_fillmode_2026-05-28.md` |
| Page A 사이징/리스크 | f=10%/회·동시보유3·일손실−3%, 1R=계좌 0.123%, 계좌 MDD −1.6~−2.0% | `stom_rl_gap_up_risk_sizing_2026-05-29.md` |
| **Page B full universe** | **2314종목·29139 instance, 전 연도 양수, 2022 +0.742%로 해소(소표본 노이즈 확정), breakeven OOS 98bp** | `stom_rl_gap_up_full_universe_2026-05-29.md` |
| Page C 유동성+gap-through 꼬리 | 유동성 PASS·sl_gap_stress 전 연도 양수(breakeven OOS 81bp) | `stom_rl_liquidity_slippage_2026-05-29.md` |
| Page D 동결정책 paper replay | 정책 작동·저낙폭, deadlock 수정(서킷브레이커) | `stom_rl_paper_replay_2026-05-29.md` |
| **마켓에이블 체결 확정** | **full N=5,173 룰 net +0.884%/trade**(buy@ask/sell@bid, 스프레드 2회) | `marketable_fill.py`, 데이터레이어 §2 |

### 4-C. 데이터 레이어 평가 + 살아남은 4 실험 (현재 작업면)
상위 문서: **`docs/stom_data_layer_assessment_2026-05-30.md`** (10-에이전트 적대패널). 결론: **1초봉은 알파 아님 = 비용/리스크/체결 진실 레이어**(검정으로 닫힌 문). 살아남은 실험:

| # | 실험 | 상태 | 결과 |
|---|---|---|---|
| ② 초당흐름 재구성(용량 정직화) | ✅ 완료 | 용량 헤드룸 **~49× 과대** 정정(09:00 동시호가 누적이 분모 오염), 조건부 PASS로 강등. `liquidity_recon.py` |
| ③ SL예측 선행 분류기(싼 디리스커) | ✅ 완료 | **PREDICTABLE → GO**: entry AUC 0.60·path30 0.66–0.68, symbol-disjoint 0.61–0.67, 4모델 사전등록 통과. **단 "리스크(하방변동성) 예측"이지 방향성 알파 아님.** `sl_predictor.py` |
| **① skip-gate(진입/스킵 이진)** | ⬜ **다음 (빌드 정당화됨)** | ③가 전제(조건 걸 신호 존재) 통과 → 유일한 진짜 미검정 알파-인접 레버. 사전확률 ~20–30%. |
| ④ 상태조건 청산 | ⬜ ① 이후 | path30 lift로 사전확률 소폭↑, 단 갭상승 평균회귀 반대 구조 그대로 |

---

## 5. ① skip-gate — 다음 작업 상세 (가장 중요)

**무엇**: 진입 시점에 "이 트레이드를 *진입할지 스킵할지*" 이진 결정하는 baseline-relative 게이트. 타이밍(언제 진입)이 아니라 진입/스킵.

**왜 살아남았나**: ③ SL예측이 진입 microstructure로 하방변동성을 AUC 0.60·강건하게 가른다 → "예측-최악 슬라이스를 스킵해 트레이드당 net을 올린다"는 전제가 기각되지 않음. 두 적대패널 모두 #1 갭으로 지목. `timing_gate.py`는 t=0 무조건 진입만 호출(스킵 메커니즘 부재) → 미검정.

**치명적 함정 = "드리프트 트랩"** (P1을 GO→NO-GO로 뒤집은 바로 그것): forward 드리프트가 대체로 양수라, SL로 끝나는 트레이드조차 *비용차감 net이 음수가 아닐* 수 있다. AUC 0.60 SL예측은 "SL 많은 슬라이스 식별"일 뿐, 그 슬라이스를 스킵해 **돈이 남는지**는 별개. SL 라벨은 *최종* 이유라 net 부호와 1:1 아님(SL도 도중 +α 후 반전 가능).

**설계 가드(사전등록 필수)**:
1. 결정변수 = **비용차감(23bp+마켓에이블) baseline-relative net** (드리프트 상쇄). 스킵 슬라이스의 net이 *0 미만*이어야 스킵이 정당.
2. purged walk-forward(이전 세션 train→이후 test) + per-boundary(5경계) + 세션 부트스트랩 CI + DSR(시도 컷 수 반영, ≥0.95).
3. positive/negative control로 게이트 검출력 먼저 입증(③·P1 패턴).
4. full universe N=5,173, symbol-disjoint 확인. 사전등록 후 단일 실행(P1식 artifact 방지).
구현 출발점: `stom_rl/sl_predictor.py`(피처·라벨·walk-forward 재사용), `marketable_fill.py`(net), `gap_up_backtest.py`(인스턴스).

---

## 6. 재현 / 검증 명령

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
# 전체 게이트 스위트 (기대: 224 passed)
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_gap_up_dashboard_publish.py `
  tests/test_stom_rl_gap_up_risk_sizing.py tests/test_stom_rl_exit_oracle.py tests/test_stom_rl_exit_baselines.py `
  tests/test_stom_rl_liquidity_model.py tests/test_stom_rl_paper_sim.py tests/test_stom_rl_sl_predictor.py `
  tests/test_stom_rl_liquidity_recon.py tests/test_stom_rl_condition_screener.py tests/test_stom_rl_marketable_fill.py `
  tests/test_stom_rl_timing_gate.py tests/test_stom_rl_predictability_probe.py tests/test_stom_rl_full_universe.py -q

# 무거운 재생성 (UTF-8 강제, 장시간)
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 stom_rl/gap_up_backtest.py --max-symbols 0 --regime-analysis --regime-cost-bps 23 --artifacts-dir .omx/artifacts/gap_up_full   # Page B full
py -3.11 -X utf8 -m stom_rl.sl_predictor          # ③ SL예측 게이트 (~88분)
py -3.11 -X utf8 -m stom_rl.liquidity_recon       # ② 용량 재구성
py -3.11 -X utf8 .omx/ppo_full_eval.py 0          # PPO 100k 전체 재평가 (checkpoint-resumable)
```

---

## 7. 신규 모듈 인벤토리 (이 트랙, 전부 커밋됨)
`gap_up_backtest.py`(엔진·fill_mode) · `gap_up_dashboard_publish.py` · `gap_up_risk_sizing.py`(A) · `exit_oracle.py`(R1) · `exit_baselines.py`(R1b) · `liquidity_model.py`(C) · `paper_sim.py`(D) · `marketable_fill.py`(마켓에이블 체결) · `microstructure_features.py`(인과피처) · `predictability_probe.py`(P0/P1) · `timing_gate.py`(P1b) · `liquidity_recon.py`(②) · `sl_predictor.py`(③) · `condition_screener.py`. 분석 스크립트: `.omx/ppo_full_eval.py`. 곡선 빌더(gitignored, 소스는 `stom_rl_resume_handoff_2026-05-28.md` §9): `.omx/artifacts/gap_up_backtest/build_equity_curve.py`, `fill_mode_compare.py`.

gitignored 산출물(`.omx/artifacts/`, `webui/rl_runs/`): 각 페이지 문서 "재현" 절로 재생성. 대시보드 run 5개(`gap_up_ts_imb_equity`/`_realized`/`_sl_gap_stress`/`gap_up_ts_equity`/`gap_up_none_equity`)는 `gap_up_dashboard_publish.py`로 재발행.

---

## 8. 정직성 가드레일 (불변 — 재개 시 필수)
1. 갭상승 룰 곡선을 **"강화학습/RL"이라 부르지 않는다.** RL은 선택·타이밍·학습정책 전부 적대검정으로 닫힘.
2. 누적곡선은 **비복리 per-trade % / fixed-notional**. paper replay 헤드라인(+수백%)은 복리×시뮬 낙관 상한이지 미래 기대 아님. avg per-episode/per-trade가 정직한 1회 기대.
3. 모든 양수치는 **in-sample / triggered-subset(STOM 기록 세션만) / 라이브 포워드 없음 / L2 큐 없음** → 기대 실거래 수익 아님, 수익 보장 아님.
4. SL예측 GO = "리스크 식별 가능"이지 "수익 식별 가능"이 아님. ①에서 *비용차감 net 부호*로 드리프트 트랩 정면 검정 전까지 ① 수익성 단정 금지.
5. "실거래 준비 완료" 미선언. 진짜 forward(실시간 피드, 환경 밖) 필요. **E broker/실주문은 명시 승인 전 금지.**
6. 단일 게이트 통과는 전체 조사서 시도한 컷 수에 비례해 의심(다중비교). 2022 약세는 대표본서 +로 해소된 소표본 노이즈 — 레짐 붕괴 단정 금지.

---

## 9. 다음 결정 트리
- **A. ① skip-gate 빌드(권장·다음)**: §5 가드로 사전등록 → 단일 실행. 통과 시 처음으로 룰 위 *증분* 알파 후보 확보. 실패해도 정직성↑.
- **B. ④ 상태조건 청산**: ① 이후. path30 예측 활용, 단 평균회귀 반대 구조 — 잔혹 deflate, 후보 ≤5.
- **C. 진짜 forward/paper(실시간)**: 환경 밖 데이터소스 연동 필요. 그 전엔 E 금지.
- **D. 사이징 실거래화**: Page A 룰을 실계좌 파라미터로 구체화(승률 41~51%·최장연패 9·계좌 MDD ~2% 반영).

## 10. 문서 읽기 순서
1. (본문) 이 파일 ← 최신 마스터 앵커
2. `docs/stom_data_layer_assessment_2026-05-30.md` — 1초봉 역할 확정 + 살아남은 4실험
3. `docs/stom_sl_predictor_gate_2026-05-30.md` — ③ SL예측 GO(다음 ①의 전제)
4. `docs/stom_ppo_full_eval_2026-05-31.md` — PPO 100k 소표본 환상 확정
5. `docs/stom_rl_timing_gate_2026-05-30.md` — P1b 타이밍 NO-GO
6. `docs/stom_rl_session_progress_2026-05-29.md` — A→D 페이지 완료 상세
7. `docs/stom_rl_resume_handoff_2026-05-28.md` — 곡선 빌더 소스(§9) + 초기 검증
