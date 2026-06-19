# STOM state-conditioned early-exit gate preregistration — 2026-06-01

## Hypothesis

This is **not reinforcement learning**. It is a supervised RULE/risk-control gate for trades that have already entered through the `ts_imb` opening-gap rule.

At the 30-second checkpoint, evaluate whether `exit_now` by marketable sell is better than `continue_baseline` through the original TP5/SL1/09:25 baseline exit.

## Experiment contract

| Item | Preregistered value |
|---|---|
| Universe | STOM full-universe `ts_imb` triggered subset |
| Baseline | Original TP5% / SL1% / 09:25 exit rule |
| Fill/cost | Entry buy@ask, exit sell@bid, 23bp round-trip cost |
| Checkpoint | 30 seconds after open for trades still open at the checkpoint |
| Denominator | Primary metric per original trade; trades already closed before 30 seconds get incremental delta `0` |
| Action | `exit_now` vs `continue_baseline` |
| Target | `early_exit_now_net_pct - baseline_continue_net_pct` |
| Primary model | `gbm` only for final GO |
| Diagnostic model | `ridge` diagnostic-only |
| Walk-forward | Date-purged split, primary boundary `0.7` |
| Robustness boundaries | `[0.5, 0.6, 0.7, 0.8, 0.9]` |
| Exit fraction grid | `[0.10, 0.20, 0.30, 0.40]`, selected on train only |
| Controls | Planted positive control, 5 deterministic shuffled-feature negatives, SL-proxy trap, leakage-invariance audit |

## GO criteria

A `GO` requires all of the following:

1. Primary incremental mean CI lower bound is greater than `0` per original trade.
2. DSR is at least `0.95`.
3. Exited-slice paired delta mean is greater than `0`.
4. Policy mean net is greater than baseline mean net.
5. At least 3 of 5 robustness boundaries have positive incremental mean for the primary model family.
6. All 5 shuffled-feature negative controls remain `NO-GO`.
7. `n_checkpoint_eligible_test_trades >= 500` and `n_policy_exits >= 50`.
8. Post-checkpoint leakage-invariance test passes.
9. The report states the boundary plainly: local backtest only, triggered subset only, no live forward result, no RL alpha claim.

Any failed criterion is `NO-GO` or `INCONCLUSIVE`.

## Implementation targets

- `stom_rl/state_exit_gate.py`
- `tests/test_stom_rl_state_exit_gate.py`
- `docs/stom_state_exit_result_2026-06-02.md`

## Planning references

- PRD: `.omx/plans/prd-stom-state-exit-2026-06-01.md`
- Test spec: `.omx/plans/test-spec-stom-state-exit-2026-06-01.md`

## Review notes

- `gbm` is the only primary model family that can produce a final GO; `ridge` remains diagnostic-only.
- Negative controls must use a deterministic 5-shuffle protocol.
- Outputs must report `n_original_test_trades`, `n_checkpoint_eligible_test_trades`, and `n_policy_exits` separately.
- Leakage checks must prove that post-checkpoint rows cannot alter checkpoint features.

## Later result link

The full-universe follow-up result is recorded in `docs/stom_state_exit_result_2026-06-02.md` and closed this gate as `NO-GO`.
