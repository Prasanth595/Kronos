# Page B — full universe 재검증 결과

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_session_progress_2026-05-29.md`, `docs/stom_rl_resume_commit_2026-05-29.md`
- 실행: `gap_up_backtest.py --max-symbols 0 --regime-analysis --regime-cost-bps 23` → `.omx/artifacts/gap_up_full/`
- 대상: **시초 갭상승 `ts_imb` 룰 — RULE strategy, NOT reinforcement learning.**

---

## 0. 한 줄 결론 (PASS)

**ts_imb 엣지는 전체 universe(2314종목·29,139 instance·2022-03~2026-02)에서 살아남았다. 전 연도(2022~2026) 비용 후 양수이고, bounded-120에서 약했던 2022가 +0.742%로 해소되어 "소표본 노이즈" 해석이 확정됐다. breakeven ~98bp는 23bp 비용의 약 4배, OOS는 경계 전반에서 안정, 슬리피지 +20bp 추가에도 양수.** 기대값은 bounded보다 다소 희석(+0.95%→약 +0.80%/trade)됐으나 강건한 양수다.

---

## 1. bounded-120 vs full-universe 비교 (ts_imb, 23bp)

| 지표 | bounded-120 (문서값) | **full-universe** | 판정 |
|---|---:|---:|---|
| 종목 수 | 120 | **2314** | ~19x |
| ts_imb N | 235 | **5175** | ~22x |
| 기대값/trade @23bp | +0.952%(ideal) | **OOS +0.750% / 연도평균 +0.74~0.92%** | 양수 유지(희석) |
| breakeven (IS/OOS) | 116.6bp(OOS) | **+107.0 / +98.0bp** | 비용의 ~4x |
| 2022 | +0.09%(N=39, 약세) | **+0.742%(N=861)** | ✅ 해소 |
| 전 연도 양수 | 아니오(2022 flat) | **예 (5/5년)** | ✅ |
| 슬리피지 +20bp(=43bp) | — | **+0.606%** | ✅ 생존 |

> 비용 주의: 그리드/baseline 헤드라인은 엔진 기본 25bp로 출력됐고, 위 ts_imb 수치는 cost-sweep/regime 섹션의 **23bp 기준**값이다. breakeven은 비용 무관(총 gross edge).

---

## 2. 연도별 기대값 @23bp (전 연도 양수)

| 필터 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|
| none (N=29139) | +0.286 | +0.252 | +0.304 | +0.196 | +0.156 |
| ts (N=9576) | +0.491 | +0.485 | +0.631 | +0.605 | +0.607 |
| **ts_imb (N=5175)** | **+0.742** | **+0.924** | **+0.831** | **+0.744** | **+0.759** |

- ts_imb는 전 연도 +0.74% 이상. 필터 강도(none<ts<ts_imb)에 따라 기대값이 단조 증가 — 신호의 일관성.
- **2022 해소가 핵심**: bounded에서 N=39로 flat~음수였던 2022가 full에서 N=861, +0.742%. 레짐 붕괴가 아니라 소표본 변동성이었음이 대표본으로 확정.

## 3. OOS 안정성 (multi-boundary, ts_imb @23bp)

| IS 비중 | 경계일 | OOS 기대값 |
|---|---|---:|
| 0.50 | 20240304 | +0.788 |
| 0.60 | 20240722 | +0.784 |
| 0.70 | 20241213 | +0.750 |
| 0.80 | 20250513 | +0.796 |
| 0.90 | 20250925 | +0.828 |

→ 경계를 어디로 옮겨도 OOS +0.75~0.83%. 단일 holdout 우연이 아님.

## 4. 슬리피지 민감도 (ts_imb)

| 추가 슬리피지 | 총비용 | net |
|---|---:|---:|
| 0bp | 23bp | +0.806 |
| 5bp | 28bp | +0.756 |
| 10bp | 33bp | +0.706 |
| 20bp | 43bp | +0.606 |

→ 비현실적으로 큰 43bp에도 +0.606%. 비용 강건.

---

## 5. 정직성 캐비엇 (유지)

1. **여전히 triggered-subset DB**: universe는 DB가 기록한 세션(어떤 STOM 조건을 만족해 기록됨)이라, 전체 시장의 모든 2% 갭상승의 무작위 표본이 아니다. **DB trigger 우주 밖 일반화는 여전히 미입증.**
2. 2314종목(필수 컬럼 결측 등으로 일부 테이블 정직하게 skip). instance 29139.
3. 이 run은 idealized 체결. realized는 약 −0.04%p 낮음(여전히 양수).
4. 기대값 희석(+0.95→+0.80): bounded-120이 다소 우호적 부분집합이었음. 결론은 "엣지 유지", 과장 금지.

---

## 6. 재현 명령

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 stom_rl/gap_up_backtest.py --max-symbols 0 --regime-analysis --regime-cost-bps 23 --artifacts-dir .omx/artifacts/gap_up_full
# 결과 -> .omx/artifacts/gap_up_full/{summary,instances,regime_analysis}.json
```
핵심 출력(2026-05-29): `instances=29139 symbols=2314 dates=20220323->20260227`; ts_imb breakeven IS/OOS +107.0/+98.0bp; 연도별 +0.742~+0.924.

---

## 7. 페이지 트랙 갱신

| 페이지 | 상태 |
|---|---|
| Page A 사이징 / R0·R1·R1b (RL 청산 폐기) | ✅ 완료 |
| **B full universe 재검증** | ✅ **완료 — 엣지 유지, 2022 해소(PASS)** |
| **C 유동성/슬리피지·gap-through 꼬리 정밀** | ⬜ **다음 권고** |
| D read-only paper/forward → E broker | 이후 (E 승인 전 금지) |

검증: 전체 게이트 138 passed(이 run은 기존 엔진 재사용, 새 코드 없음). 수치는 `.omx/artifacts/gap_up_full/summary.json`에 영속.
