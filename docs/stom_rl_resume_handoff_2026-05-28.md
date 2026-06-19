# STOM RL 랩 — 마스터 재개(RESUME) 핸드오프 (자립형)

- 작성일: 2026-05-28
- **목적: 이 문서 하나만 읽으면 새 대화/새 클론에서 위 작업 전체를 그대로 이어갈 수 있다.** 재현에 필요한 gitignored 스크립트 소스를 §9에 전부 내장했고, DB에서 모든 산출물을 재생성하는 레시피를 §7에 담았다.
- 브랜치: `feature/stom-rl-lab` · 최신 커밋: `5c56a47`
- 데이터(유일): `D:\Chanil_Park\Project\Programming\Kronos\_database\stock_tick_back.db`
  - 1초봉, 개장 **09:00–09:30만**, 이벤트 트리거 기록(희소), 28GB, 2427개 종목 테이블.
  - **UTF-8 한글 컬럼**(cp949 아님). 종목코드 **선행 0 보존**(예: `000250` — int 변환 금지).
  - `amount`=초당거래대금(per-second) → 리샘플 시 **SUM** 집계.

---

## 0. 한 줄 현황 (TL;DR)

**강화학습(RL)은 우상향 곡선을 못 만든다(인트라데이 알파 부재 — 1초·1분·세션 3중 shuffle-NO). 우상향 곡선을 만드는 것은 RL이 아니라 "시초 갭상승 룰 전략"이며, 사용자 실비용 23bp + 체결 de-idealization(최악 SL gap-through)까지 견디며 검증됨(ts_imb 최악 +0.81%/trade, breakeven 대비 ~4×). 곡선은 PNG + 대시보드 run 5개로 시각화 완료. 남은 한계: 진짜 큐/부분체결 replay는 L2 데이터 부재로 불가, 2022는 소표본 약세(다중비교 보정 시 비유의).**

---

## 1. 이 문서 사용법 (재개 프로토콜)

새 대화 첫 프롬프트로 아래를 그대로 쓰면 된다:
```
docs/stom_rl_resume_handoff_2026-05-28.md 읽고 STOM RL 랩 이어서 진행.
```
그 다음 §2(맥락) → §3(히스토리) → §4(검증수치) → §6(파일) → §7(재현) 순으로 읽으면 전체 작업이 복원된다. **§11 정직성 가드레일을 반드시 지킬 것.**

---

## 2. 사용자 · 전략 · 비용 (불변 사실)

- 한국 퀀트 트레이더(parkchanil77@naver.com). 전략 = **"시초 급등 / 9시 시초 갭 상승"**(opening gap-up momentum).
- **전략 스펙(사용자 지정·확정)**:
  - 진입: 시초 `등락율` ≥ **2%**(갭상승).
  - 청산: **TP(목표수익) / SL(손절) 또는 09:25 시간청산**. PRIMARY = **TP5% / SL1% / 09:25**.
- **실제 왕복 체결비용 = 23bp** = 매수 수수료 0.015% + 매도 수수료 0.015% + 증권거래세 0.20%(매도측). (사용자가 명시 확정.)
- 사용자가 원한 것: **유튜브 NEAT 영상 스크린샷처럼 "꾸준히 우상향하는 수익 곡선"**, 실거래 직전 상태인지.
- **데이터는 위 DB 단 하나**(다른 데이터 없음). universe = STOM이 트리거한 종목 = **사용자 실거래 대상과 일치** → 배포 관점에서 트리거-universe는 편향 아님.

---

## 3. 프로젝트 히스토리 (무엇을 시도→무엇이 실패/성공했나)

이 순서가 "위 대화"의 핵심 논리 흐름이다.

1. **RL 포트폴리오 선택(cross-sectional PPO/DQN)** 시도 → **인트라데이 선택 알파 부재**.
   - 1초 horizon: shuffle 검정 NO. 1분 horizon: NO. 세션바(일봉 proxy): NO.
   - 결론: 제약은 알고리즘이 아니라 **신호/데이터**. RL NAV는 우상향하지 않음.
   - 교훈(사용자에게 한 약속): **안 맞는 프레임에 데이터를 욱여넣어 거짓 결론 내지 않는다.**
2. **전략 reframe**: 사용자의 실제 전략(시초 갭상승)은 이 데이터와 **맞음** → 룰 백테스트로 전환.
3. **갭상승 룰 백테스트(필터 전)**: 고정 TP/SL 그리드, 임의 25bp → **0/16 OOS 음수**(엣지가 비용에 먹힘). [48bbdef]
4. **현실 비용모델 + 진입필터(체결강도/호가) + cost sweep** → **필터 시 OOS 양수**(첫 긍정 신호). [bf767d7]
5. **레짐 robustness + 슬리피지 검증** → 매년·5경계 OOS 양수, 38bp 슬리피지 생존. [c80a9c9]
6. **사용자 실비용 23bp 확정** → 전 필터 양수, ts_imb +0.9%/trade. [d87dd00]
7. **우상향 곡선 시각화(PNG + 대시보드 run) + 체결 de-idealization(realized/SL gap-through) 게이트** → ts_imb 최악에도 +0.81%/trade. [e5d89c2]
8. **2022 약세를 다중비교 보정으로 검정** → 소표본 변동성(레짐 실패 아님). [5c56a47]

---

## 4. 검증된 수치 (확정 결과)

### 4-A. RL 알파 부재 (3중)
1초·1분·세션프록시 전부 shuffle 검정 NO. 근거: `docs/stom_rl_deep_rl_verdict_2026-05-27.md`, `stom_rl_signal_test_2026-05-27.md`, `stom_rl_1min_signal_verdict_2026-05-27.md`, `stom_rl_story_b1_session_proxy_verdict_2026-05-27.md`.

### 4-B. 진입필터 정의 (`stom_rl/gap_up_backtest.py`)
- `none`: 2% 갭만.
- `ts`: **체결강도 ≥ 100**(STOM "at par").
- `ts_imb`: 체결강도 ≥ 100 **AND** 호가 imbalance(매수총잔량/(매수+매도)) ≥ 0.5.

### 4-C. 실비용 23bp 기대값 (idealized, TP5/SL1)
| 필터 | N | @23bp/trade | de-idealized | breakeven | 여유 |
|---|---:|---:|---:|---:|---:|
| none | 1349 | +0.246% | +0.206% | 42.7bp | 1.9× |
| +ts | 425 | +0.633% | +0.593% | 82.7bp | 3.6× |
| **+ts_imb** | 235 | **+0.952%** | **+0.912%** | 116.6bp | **5.1×** |

### 4-D. 누적 equity 곡선 (build_equity_curve, @23bp, TP5/SL1, idealized 캐시)
| 필터 | N | 누적%(비복리) | exp/trade | 승률 | 최대낙폭 | 최장연패 |
|---|---:|---:|---:|---:|---:|---:|
| UNFILTERED | 1349 | +332.2% | +0.246% | 29% | −26.0% | 17 |
| +ts | 425 | +269.0% | +0.633% | 36% | −19.3% | 12 |
| **+ts_imb** | 235 | **+223.6%** | +0.952% | 42% | **−15.7%** | **9** |
→ ts_imb가 가장 매끈한 우상향.

### 4-E. 체결 de-idealization (ts_imb @23bp) — 핵심 견고성 검증
| 체결모드 | exp/trade | vs idealized | 누적 NAV(시작 1M) | 최대낙폭 |
|---|---:|---:|---:|---:|
| idealized(낙관) | +0.952% | — | 3,236,073 (+223.6%) | −16.1% |
| realized(현실) | +0.906% | −0.045%p | 3,130,059 (+213.0%) | −20.0% |
| **sl_gap_stress(최악)** | **+0.811%** | −0.140%p | 2,906,596 (+190.7%) | −20.5% |
→ 최악 체결에도 +0.81%, breakeven 116.6bp 대비 ~4× 여유.

### 4-F. 연도별 ts_imb (@23bp, mean_net %/trade)
| 모드 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| idealized | +0.09 | +1.45 | +1.10 | +1.00 | +0.91 |
| realized | **−0.01** | +1.50 | +1.02 | +0.93 | +0.90 |
| sl_gap_stress | **−0.05** | +1.32 | +0.96 | +0.85 | +0.76 |

### 4-G. 필터 강도 × 최악체결 (sl_gap_stress) — 필터가 안전마진
| 필터 | idealized exp | sl_gap_stress exp | sl_gap_stress 최대낙폭 |
|---|---:|---:|---:|
| none | +0.226 | +0.058 | **−65.2%** |
| ts | +0.613 | +0.437 | −30.0% |
| **ts_imb** | +0.932 | **+0.791** | −20.9% |
(이 표는 @25bp 캐시 기준; @23bp는 각 +0.02. 비교·낙폭 결론 동일.)

---

## 5. 정직한 한계

1. **게이트 3 (진짜 큐·부분체결 paper replay) 불가**: L2 큐포지션 데이터가 DB에 없음(매수/매도총잔량 합계만). realized/sl_gap_stress 체결 + 슬리피지 38bp 스윕이 **우리 데이터로 가능한 체결현실성 상한**. 가짜 큐 시뮬은 만들지 않는다. (`stom_rl/paper_replay.py`는 PortfolioEnv용이라 갭상승 룰엔 부적합.)
2. **2022 약세**(ts_imb realized −0.01 / 최악 −0.05): N=39 소표본, SE ±0.40%/trade, 95% CI가 0 포함 → **단독 음수 아님**. vs 2023~26 Welch t=2.27~2.35(uncorrected) 이나 "5년 중 최약" 사후지목 → **Bonferroni 임계 ~2.6 기준 비유의**. 승률 26% > 손익분기 ~20.5% → 구조 안 깨짐. **소표본 변동성, 레짐 실패 아님.** 단 단일 연도는 변동성만으로 flat~음수 가능 → 사이징/낙폭관리 필수.
3. 곡선은 **비복리 per-trade % 합**(고정 노셔널 가정). "연수익률"/"복리 계좌곡선"으로 과장 금지. 손익은 소수 TP가 캐리하는 꼬리 의존.

---

## 6. 파일 인벤토리 (커밋됨 vs gitignored)

### 커밋된 소스 (진짜 산출물 — git에 있음)
| 경로 | 내용 |
|---|---|
| `stom_rl/gap_up_backtest.py` | 갭상승 백테스트 엔진. `simulate_trade(fill_mode=...)`, `--fill-mode {idealized,realized,sl_gap_stress}`, `--regime-analysis`, `--cost-bps`, `--max-symbols`, `--artifacts-dir`. |
| `stom_rl/gap_up_dashboard_publish.py` | 곡선을 대시보드 `portfolio_paper` run으로 발행. |
| `tests/test_stom_rl_gap_up_backtest.py` | 백테스트 테스트(41). |
| `tests/test_stom_rl_gap_up_dashboard_publish.py` | 발행 테스트(6). |
| `docs/stom_rl_gap_up_*.md`, `docs/stom_rl_deep_rl_verdict_*.md` 등 | 결과 문서들(§13). |
| `webui/rl_dashboard.py`, `webui/app.py` | 대시보드 read-only API(`/api/rl/*`). |
| `stom_rl/rl_events.py` | `RlLiveEvent`/`RlLiveEventWriter`/`summarize_live_events`(발행이 재사용). |

**테스트 47 passed**(41+6). 재현: `py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_gap_up_dashboard_publish.py -q`

### gitignored (커밋 안 됨 — §7로 재생성, 스크립트는 §9에 내장)
- `.omx/` 전체 (line 82 .gitignore): `instances.json` 캐시, `build_equity_curve.py`, `fill_mode_compare.py`, `gap_up_{idealized,realized,sl_gap_stress}/`, `equity_curve.png`.
- `webui/rl_runs/` 전체 (line 64): 발행된 run 5개(`gap_up_ts_imb_equity`, `..._realized`, `..._sl_gap_stress`, `gap_up_ts_equity`, `gap_up_none_equity`).
- 비용은 **flat 가산적**: `net@c = net@25 + (25−c)/100`(per-trade %). 캐시(25bp)→23bp는 `+0.02%p`만 가산.

---

## 7. 전체 재현 레시피 (새 클론에서 0부터)

전제: `_database/stock_tick_back.db` 존재, Python `py -3.11`, 의존성 설치(`pip install -r requirements.txt`).

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos

# 1) 테스트 통과 확인 (47)
py -3.11 -m pytest tests\test_stom_rl_gap_up_backtest.py tests\test_stom_rl_gap_up_dashboard_publish.py -q

# 2) idealized 캐시 + 레짐분석 재생성 (instances.json @25bp 작성, ~7분/120종목)
py -3.11 stom_rl\gap_up_backtest.py --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_backtest

# 3) realized / sl_gap_stress 캐시 (de-idealization 비교용)
py -3.11 stom_rl\gap_up_backtest.py --fill-mode realized      --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_realized
py -3.11 stom_rl\gap_up_backtest.py --fill-mode sl_gap_stress --regime-analysis --regime-cost-bps 23 --max-symbols 120 --artifacts-dir .omx\artifacts\gap_up_sl_gap_stress
# (idealized 비교본도 같은 dir 규칙으로: --artifacts-dir .omx\artifacts\gap_up_idealized)

# 4) §9의 두 스크립트를 해당 경로에 생성 후:
py -3.11 .omx\artifacts\gap_up_backtest\build_equity_curve.py --png   # 곡선 콘솔+PNG
py -3.11 .omx\artifacts\gap_up_backtest\fill_mode_compare.py          # 3모드 비교표

# 5) 대시보드 run 발행 (5개)
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter none   --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter ts     --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --filter ts_imb --cost-bps 23
py -3.11 -m stom_rl.gap_up_dashboard_publish --instances .omx\artifacts\gap_up_realized\instances.json      --filter ts_imb --cost-bps 23 --run-name gap_up_ts_imb_realized
py -3.11 -m stom_rl.gap_up_dashboard_publish --instances .omx\artifacts\gap_up_sl_gap_stress\instances.json --filter ts_imb --cost-bps 23 --run-name gap_up_ts_imb_sl_gap_stress
```

> `--max-symbols 0` = full universe(2400+종목, 매우 느림). 검증엔 120으로 충분(1349 인스턴스/115종목 = 위 모든 수치의 universe). 비용은 가산적이라 `--cost-bps`를 굳이 23으로 안 줘도 캐시 @25bp에서 환산 가능.

`instances.json` 레코드 키: `tp5_sl1_net_pct`(외 TP/SL 조합 `*_net_pct`/`*_reason`, @해당 cost·fill_mode), `pass_ts`, `pass_ts_imb`, `entry_change_rate`, `entry_price`, `entry_trade_strength`, `entry_sec_amount`, `entry_bid_ask_imbalance`, `baseline_net_pct`, `session`(YYYYMMDD str), `symbol`, `split`.

---

## 8. 대시보드 (발행 + 서버)

- 발행물: `webui/rl_runs/<run_name>/` 3파일 — `portfolio_paper_summary.json`(감지 anchor, 파일명 기반), `rl_live_events.jsonl`(거래당 1 event, `equity`=NAV → follow/replay 곡선), `rl_live_summary.json`.
- 정직 라벨(필수): `algorithm="rule:gap_up_<filter>"`, config `is_reinforcement_learning=false`, info `note="RULE strategy backtest, not an RL policy"`.
- URL: `http://127.0.0.1:5070/rl` → run 선택 → NAV 곡선. 5개 run final_nav: ts_imb_equity 3.24M / realized 3.13M / sl_gap_stress 2.91M / ts 3.69M / none 4.32M.
- **서버 기동(헤드리스)**: 리로더 OFF라 **코드/신규 run 인식하려면 재시작 필요**. 5070 리슨 PID kill 후:
  ```powershell
  $env:KRONOS_WEBUI_PORT='5070'; $env:KRONOS_WEBUI_OPEN_BROWSER='0'; $env:KRONOS_WEBUI_RELOAD='0'; py -3.11 webui\run.py
  ```
  감지는 `portfolio_paper_summary.json` 파일명 기반. 서버가 run을 `artifact_type=unknown`으로 주면 stale → 재시작.

---

## 9. 내장 스크립트 소스 (gitignored이라 여기 보존 — 그대로 생성하면 됨)

### 9-A. `.omx/artifacts/gap_up_backtest/build_equity_curve.py`
```python
"""시초 갭상승 누적 equity 곡선 빌더 (캐시 instances.json에서 즉시, DB 재실행 불필요).

usage:
    py -3.11 .omx/artifacts/gap_up_backtest/build_equity_curve.py            # 콘솔 요약 + ASCII
    py -3.11 .omx/artifacts/gap_up_backtest/build_equity_curve.py --png      # PNG도 저장(matplotlib 필요)
입력: .omx/artifacts/gap_up_backtest/instances.json (per-TP/SL net_pct@25bp, pass_ts, pass_ts_imb, session, symbol)
비용: 캐시 net은 25bp 기준 -> 23bp는 +0.02%p 가산. 룰 전략 곡선(강화학습 아님), 비복리 per-trade % 단순합.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(HERE, "instances.json")
KEY = "tp5_sl1_net_pct"
SHIFT = 0.02  # 25bp -> 23bp
FILTERS = [("none", "UNFILTERED(2%갭만)"), ("pass_ts", "+체결강도(ts)"),
           ("pass_ts_imb", "+체결강도+호가(ts_imb)")]


def build(flt):
    inst = json.load(open(INST, encoding="utf-8-sig"))
    rows = [r for r in inst if flt == "none" or r.get(flt)]
    rows.sort(key=lambda r: (r["session"], r["symbol"]))
    eq = peak = mdd = 0.0
    wins = ls = mls = 0
    curve = []
    for r in rows:
        net = r[KEY] + SHIFT
        eq += net
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        if net > 0:
            wins += 1
            ls = 0
        else:
            ls += 1
            mls = max(mls, ls)
        curve.append((r["session"], eq))
    n = len(rows)
    stats = dict(n=n, cum=eq, exp=eq / n if n else 0, win=wins / n if n else 0,
                 maxdd=mdd, maxloss=mls)
    return stats, curve


def main():
    do_png = "--png" in sys.argv
    print(f"=== 시초 갭상승 누적 equity (룰 전략, NOT RL) | {KEY} @23bp ===")
    series = {}
    for flt, label in FILTERS:
        s, curve = build(flt)
        series[flt] = (label, curve)
        print(f"{label:22} N={s['n']:4d} cum={s['cum']:+7.1f}% "
              f"exp={s['exp']:+.3f}%/trade win={s['win']:.0%} "
              f"maxDD={s['maxdd']:+.1f}% maxLossStreak={s['maxloss']}")
    label, curve = series["pass_ts_imb"]
    print(f"\n-- {label} 곡선 (cum %), ~12 표본 --")
    step = max(1, len(curve) // 12)
    for i in range(0, len(curve), step):
        s, e = curve[i]
        print(f"   {s} t{i:3d}: {e:+7.1f} {'#' * int(max(0, e))}")
    s, e = curve[-1]
    print(f"   {s} t{len(curve)-1:3d}: {e:+7.1f} (final)")
    if do_png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for _f in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
            try:
                plt.rcParams["font.family"] = _f
                break
            except Exception:
                continue
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(11, 5))
        for flt, (label, curve) in series.items():
            ax.plot(range(len(curve)), [e for _, e in curve], label=label, lw=1.3)
        ax.set_title("시초 갭상승 누적 equity (룰 전략, NOT RL) TP5/SL1/09:25 @23bp")
        ax.set_xlabel("trade #")
        ax.set_ylabel("cumulative net % (비복리)")
        ax.legend()
        ax.grid(alpha=0.3)
        out = os.path.join(HERE, "equity_curve.png")
        fig.tight_layout()
        fig.savefig(out, dpi=120)
        print(f"\nPNG saved: {out}")


if __name__ == "__main__":
    main()
```

### 9-B. `.omx/artifacts/gap_up_backtest/fill_mode_compare.py`
```python
"""3개 fill_mode(idealized/realized/sl_gap_stress) 비교 추출기.
각 모드의 .omx/artifacts/gap_up_<mode>/instances.json 에서 ts_imb TP5/SL1 기대값·승률·누적·exit-mix 계산.
(instances.json 의 tp5_sl1_net_pct 는 해당 모드 fill 로 이미 계산됨; @25bp 캐시면 23bp는 +0.02 가산해 읽을 것.)
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .omx/artifacts
MODES = ["idealized", "realized", "sl_gap_stress"]
KEY = "tp5_sl1_net_pct"
RKEY = "tp5_sl1_reason"


def load(mode):
    p = os.path.join(HERE, f"gap_up_{mode}", "instances.json")
    if not os.path.isfile(p):
        return None
    return json.load(open(p, encoding="utf-8-sig"))


def stats(rows, flt):
    sel = [r for r in rows if flt == "none" or r.get(flt)]
    sel.sort(key=lambda r: (r["session"], r["symbol"]))
    if not sel:
        return None
    nets = [r[KEY] for r in sel]
    n = len(nets)
    cum = peak = mdd = 0.0
    for v in nets:
        cum += v
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    wins = sum(1 for v in nets if v > 0)
    reasons = {}
    for r in sel:
        reasons[r.get(RKEY)] = reasons.get(r.get(RKEY), 0) + 1
    return dict(n=n, exp=sum(nets) / n, cum=cum, win=wins / n, mdd=mdd,
               sl=reasons.get("sl", 0) / n, tp=reasons.get("tp", 0) / n,
               time=reasons.get("time", 0) / n)


def main():
    print(f"=== fill_mode 비교 (ts_imb, {KEY}, 120종목 동일 universe) ===")
    avail = {m: load(m) for m in MODES}
    missing = [m for m, v in avail.items() if v is None]
    if missing:
        print("  아직 없음:", missing)
    for flt, label in [("pass_ts_imb", "ts_imb"), ("pass_ts", "ts"), ("none", "none")]:
        print(f"\n-- filter={label} --")
        print(f"  {'mode':14} {'N':>4} {'exp%/trade':>11} {'cum%':>8} {'win':>5} {'maxDD%':>7} {'tp/sl/time':>14}")
        for m in MODES:
            rows = avail.get(m)
            if rows is None:
                print(f"  {m:14} (pending)")
                continue
            s = stats(rows, flt)
            if s is None:
                print(f"  {m:14} n=0")
                continue
            print(f"  {m:14} {s['n']:>4} {s['exp']:>+11.3f} {s['cum']:>+8.1f} "
                  f"{s['win']:>5.0%} {s['mdd']:>+7.1f} "
                  f"{s['tp']:.0%}/{s['sl']:.0%}/{s['time']:.0%}")
    if not missing:
        si = stats(avail["idealized"], "pass_ts_imb")
        sr = stats(avail["realized"], "pass_ts_imb")
        ss = stats(avail["sl_gap_stress"], "pass_ts_imb")
        print("\n-- ts_imb de-idealization (per-trade %p delta vs idealized) --")
        print(f"  realized:      {sr['exp']-si['exp']:+.3f}%p  -> exp {sr['exp']:+.3f}%/trade")
        print(f"  sl_gap_stress: {ss['exp']-si['exp']:+.3f}%p  -> exp {ss['exp']:+.3f}%/trade (worst)")
        print(f"  idealized baseline: {si['exp']:+.3f}%/trade")
        print(f"  => worst-case {ss['exp']:+.3f}%/trade: {'SURVIVES (>0)' if ss['exp']>0 else 'FAILS (<=0)'}")


if __name__ == "__main__":
    main()
```

---

## 10. 커밋 맵 (이 작업의 git 이력)
| 커밋 | 내용 |
|---|---|
| `5c56a47` | docs: 2022 약세 다중비교 보정 → 소표본 변동성 결론 |
| `e5d89c2` | feat: 우상향 곡선 대시보드 발행 + 체결 de-idealization(fill_mode) 게이트 |
| `d87dd00` | docs: 실비용 23bp 확정(전 필터 양수, ts_imb +0.9%) |
| `c80a9c9` | feat: 레짐 robustness + 슬리피지 검증 |
| `bf767d7` | feat: 현실 비용모델 + 진입필터 + cost sweep(필터 시 OOS 양수) |
| `48bbdef` | feat: 갭상승 TP/SL/09:25 백테스트(필터 전 0/16) |

---

## 11. 정직성 가드레일 (재개 시 필수)
- 룰 전략 곡선을 **"강화학습/RL"이라 부르지 않는다**(RL 알파 부재 증명됨; 라벨 `rule:*`, `is_reinforcement_learning=false` 유지).
- 누적곡선은 **비복리 per-trade % 합** — 연수익률/복리 계좌곡선으로 과장 금지.
- 영상의 매끈한 곡선 = 보통 in-sample/과적합. 우리 곡선은 거칠지만 OOS·매년·5경계·체결 de-idealization 검증됨.
- 체결 현실성(realized/SL gap-through/슬리피지) 확정 전까지 "실거래 준비 완료"라 말하지 않는다.
- 2022 등 단일 연도 결과는 큰 오차(SE ±0.4%) — 다중비교 보정 후 판단.

---

## 12. 다음 할 일 (결정 트리)
- **A. 사이징/리스크 설계**: 승률 41~51%·TP5/SL1 비대칭·최장연패 9·최대낙폭 ~20% → 포지션 사이징·동시보유·일손실한도 룰 정하기(실거래 직전 가장 실질적).
- **B. universe 확장**: `--max-symbols 0`(full)로 재실행해 120종목→전체에서 수치 유지되는지.
- **C. 실주문 슬리피지/유동성 모델**: 갭상승 개장가 실제 체결가능 물량 가정 정교화.
- **D. (불가) 진짜 큐/부분체결 replay**: L2 데이터 확보 시에만.
- **E. 라이브 페이퍼**: 시점별 read-only 신호 생성기로 forward 검증(주문 미발행).

---

## 13. 관련 문서 읽기 순서
1. (본문) `docs/stom_rl_resume_handoff_2026-05-28.md` ← 이 파일(마스터)
2. `docs/stom_rl_gap_up_fillmode_2026-05-28.md` — 체결 de-idealization + 2022 분석
3. `docs/stom_rl_gap_up_realcost_2026-05-28.md` — 실비용 23bp 확정
4. `docs/stom_rl_gap_up_regime_validation_2026-05-28.md` — 레짐/슬리피지
5. `docs/stom_rl_gap_up_cost_filter_2026-05-27.md` — 비용모델+필터 첫 양수
6. `docs/stom_rl_gap_up_backtest_2026-05-27.md` — 필터 전 기준선(0/16)
7. `docs/stom_rl_deep_rl_verdict_2026-05-27.md` — RL 알파 부재 종합
