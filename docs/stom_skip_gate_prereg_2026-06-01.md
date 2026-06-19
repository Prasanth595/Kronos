# STOM ① Skip-Gate 사전등록 — 2026-06-01

## 정직성 선언

- 이 실험은 **갭상승 ts_imb RULE 전략 위의 진입/스킵 게이트**이다.
- **강화학습/RL 알파가 아니다.** 기존 RL 선택·타이밍·PPO 트랙은 prior 문서에서 닫혔다.
- 모든 결과는 `_database/stock_tick_back.db` 기반 백테스트/시뮬레이션이며, 라이브 포워드·L2 큐·실주문 검증이 아니다.

## 질문

기존 `ts_imb` 갭상승 룰이 진입시키는 각 트레이드에 대해, 진입 시점 causal microstructure만 보고 일부를 **스킵**하면:

> 23bp 비용 + marketable fill 반영 후 take-all baseline 대비 incremental net이 양수인가?

## Primary Target

- Label/target: `stom_rl.marketable_fill.simulate_rule_from_entry(..., entry_idx=0, cost_bps=23)`의 realized net `%`
- Baseline: 모든 `ts_imb` instance를 진입
- Policy:
  - take: realized net 반영
  - skip: 0% 반영
  - incremental = policy - baseline = skipped trade에서는 `-net`, taken trade에서는 `0`

## 금지된 판정

- SL label AUC만으로 GO 금지
- SL-heavy slice 식별만으로 수익성 주장 금지
- 누적곡선/복리 paper replay를 기대수익처럼 해석 금지

## Drift Trap Guard

GO가 되려면 primary test split에서 모델이 스킵한 slice의 realized marketable net 평균이 **0 미만**이어야 한다.

즉, “SL이 많다”가 아니라 “실제로 비용차감 후 돈을 잃는 slice를 스킵했다”가 필요하다.

## Model / Policy

- Features: `stom_rl.microstructure_features.FEATURE_NAMES`
- Snapshot: entry window, 기본 `entry_window_sec=5`
- Models:
  - `ridge`
  - `HistGradientBoostingRegressor`
- Skip fraction grid:
  - `[0.10, 0.20, 0.30, 0.40]`
- Selection:
  - 각 train split에서 predicted net 하위 fraction별 train incremental mean을 계산
  - train incremental mean이 가장 큰 skip fraction 하나를 선택
  - test split에서는 해당 fraction만 적용

## Walk-Forward

- Dates are purged:
  - train: strictly earlier than boundary date
  - test: strictly later than boundary date
  - boundary date itself is embargoed
- Boundaries: `[0.5, 0.6, 0.7, 0.8, 0.9]`
- Primary boundary: `0.7`

## GO / NO-GO Criteria

Primary model GO requires all:

1. primary boundary incremental bootstrap CI lower bound > 0
2. Deflated Sharpe Ratio `>= 0.95`
3. skipped-slice realized marketable net mean < 0
4. same model has positive incremental mean on at least 3 of 5 boundaries
5. negative feature-shuffle control is NO-GO

If any condition fails, verdict is `NO-GO` or `INCONCLUSIVE`, not GO.

## Controls

### Positive control

Synthetic money-losing low-score slice must produce GO.

### Negative control

Feature-shuffled/noise relation must produce NO-GO.

### Drift-trap control

Predictive score that selects “weaker” but still positive-net trades must remain NO-GO.

## Implementation Files

- `stom_rl/skip_gate.py`
- `tests/test_stom_rl_skip_gate.py`

## Commands

Targeted tests:

```powershell
py -3.11 -m pytest tests/test_stom_rl_skip_gate.py tests/test_stom_rl_sl_predictor.py tests/test_stom_rl_marketable_fill.py tests/test_stom_rl_timing_gate.py -q
```

Smoke extraction:

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.skip_gate --db-path _database/stock_tick_back.db --max-symbols 5 --output-dir .omx/artifacts/skip_gate_smoke
```

Full run:

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.skip_gate --db-path _database/stock_tick_back.db --output-dir .omx/artifacts/skip_gate
```
