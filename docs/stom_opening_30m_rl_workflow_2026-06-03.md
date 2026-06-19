# STOM Opening 30M RL Workflow preregistration / handoff — 2026-06-03

## Verdict boundary

This document preregisters the opening-30-minute RL workflow as an **RL EXPERIMENT** only.
It is research evidence, **not live-ready**, not broker-ready, and not a usable trading model.

The `ts_imb RULE baseline` remains the mainline opening gap-up rule baseline. The RL track may only be compared against it; it must not relabel the rule curve as reinforcement learning.

Current default cost is **23bp** round trip with marketable-fill interpretation where applicable.

## Hypothesis

Opening continuation may be better explained by:

```text
participant proxy pressure
+ orderbook persistence
+ overheat / upper-wick exhaustion
+ cost and slippage
```

The model must treat participant data as **proxy evidence** only. It must not claim that it identified actual foreign, institution, retail, or big-money actors.

## Data bounds

| Item | Bound |
|---|---|
| Window | 09:00:00–09:30:00 only |
| Decision data | causal rows at or before the decision second |
| Symbols | preserve leading-zero codes such as `000250` |
| Investor-class flow | optional only; if unavailable or delayed, mark missing / not causal |
| Dashboard | read-only evidence viewer |

The 09:00 auction print must not be treated as a continuous-trading tick unless the source data explicitly supports that interpretation.

## Split protocol

- Build deterministic opening episode manifests before training.
- Use chronological train/eval/OOS split metadata.
- Refuse split overlap.
- Do not tune on OOS after seeing outcomes.
- Any GO_CANDIDATE requires OOS evidence plus negative control and feature-ablation checks.

## Model family

First model family:

```text
Stable-Baselines3 DQN
action space: hold / market_buy / market_exit
fixed-entry / exit-first smoke path
```

If the local Windows SB3/Torch import is unavailable, the training stage must record `skipped_sb3_unavailable` rather than pretending a model was produced.

## Required controls

The workflow is blocked unless all relevant controls are recorded:

1. `negative control` / shuffled participant context.
2. Feature ablation: full context vs no participant-pressure.
3. Feature ablation: full context vs no orderbook-persistence.
4. Overheat/upper-wick penalty ablation.
5. No-trade, buy-and-hold, and `ts_imb RULE baseline` comparisons.
6. 23bp cost gate.
7. OOS split metadata.

Failure of controls or cost gate keeps the verdict at **NO-GO**.

## GO / NO-GO criteria

The workflow can only become GO_CANDIDATE if all are true:

1. RL mean return beats no-trade, buy-and-hold, and `ts_imb RULE baseline` after 23bp cost.
2. Negative controls remain NO-GO.
3. Feature ablations prove participant/orderbook context adds incremental value.
4. OOS split exists and has no overlap with train/eval.
5. Drawdown/trade-count gates are sane.
6. Dashboard still labels the result **RL EXPERIMENT**, **NO-GO** when failed, and **not live-ready**.

Otherwise the result is **NO-GO** or INCONCLUSIVE.

## Dashboard interpretation

The dashboard must show:

- `OPENING 30M RL WORKFLOW`
- `PARTICIPANT PROXY EVIDENCE`
- `ORDERBOOK PERSISTENCE`
- proxy availability and missing proxy columns
- feature ablation status
- baseline/cost/control failures
- `NO-GO`, `not live-ready`, `23bp`, and `ts_imb RULE baseline`

Visual curves are evidence summaries only. They are not profitability proof.

## Prior NO-GO guardrails preserved

- skip-gate result remains **NO-GO** unless a new preregistered hypothesis and evidence overturn it.
- state-exit result remains **NO-GO** unless a new preregistered hypothesis and evidence overturn it.
- Earlier PPO/plain RL candidates remain research-only and not live-ready.

## Exact commands

### Workflow dry-run

```powershell
py -3.11 -m stom_rl.opening_30m_rl_workflow --run-id opening_30m_rl_workflow --output-dir webui/rl_runs/opening_30m_rl_workflow --no-write
```

### Tiny fixture smoke

```powershell
py -3.11 -m pytest tests/test_stom_rl_opening_workflow_runner.py tests/test_stom_rl_opening_training.py tests/test_stom_rl_opening_artifacts.py -q
```

### End-to-end fixture smoke

```powershell
py -3.11 -m pytest tests/test_stom_rl_opening_workflow_e2e.py -q
```

### Dashboard API test

```powershell
py -3.11 -m pytest tests/test_stom_rl_opening_dashboard_api.py tests/test_stom_rl_opening_progress.py tests/test_stom_rl_participant_dashboard.py -q
```

### Frontend build

```powershell
powershell -NoProfile -Command 'Push-Location webui/v2_src; npm run build; $code=$LASTEXITCODE; Pop-Location; exit $code'
```

### Current focused regression

```powershell
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_stom_rl_dashboard_tab.py tests/test_stom_rl_participant_dashboard.py -q
```

### Opening workflow regression

```powershell
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_stom_rl_dashboard_tab.py tests/test_stom_rl_orderbook_env.py tests/test_stom_rl_orderbook_sb3.py tests/test_stom_rl_opening_workflow_contract.py tests/test_stom_rl_opening_workflow_runner.py tests/test_stom_rl_opening_workflow_e2e.py -q
```

## Handoff

Next work should run the end-to-end fixture smoke, then final verification. Do not claim a profitable or usable model from the current workflow. The current deliverable is a falsifiable research workflow and dashboard evidence surface.
