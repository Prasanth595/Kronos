# Kronos Project Knowledge Base

**Generated:** 2026-06-03 KST
**Last reviewed:** 2026-06-03 KST, init-deep update mode
**Branch observed:** `feature/stom-rl-lab`
**Commit observed:** `943222b`

## Overview

Kronos is now a combined research/operations repo: core Kronos model code, STOM
1-second/tick data pipelines, rule/RL trading research, and the official Flask +
Svelte dashboard for inspection. Treat it as an experimental trading research
platform, not as a live-trading product.

## Current Direction

| Area | Current stance | Reason |
|---|---|---|
| `ts_imb` opening gap-up rule | Main research baseline | Prior docs show the strongest useful curve here; it is a RULE strategy, not RL. |
| Skip-gate / state-exit gates | Deprioritize unless new hypothesis is preregistered | Full-universe docs report `NO-GO`. |
| Plain PPO/DQN RL | Do not present as usable | Existing PPO/DQN/orderbook runs are `NO-GO` or research-only. |
| Orderbook RL | Keep as isolated experiment/falsification tool | Useful for testing action design and dashboard comparison, not live readiness. |
| Dashboard | Continue as evidence viewer | It should expose failure, baselines, costs, and split metadata clearly. |

## Structure

```text
Kronos/
+-- model/             # Kronos model/tokenizer implementation
+-- finetune/          # STOM/Qlib export, training, evaluation CLIs
+-- stom_rl/           # STOM rule/RL experiments, gates, backtests, readiness
+-- webui/             # Flask API and official dashboard adapters
+-- webui/v2_src/      # Svelte/Vite dashboard source (internal path name)
+-- tests/             # pytest coverage for model, STOM, web, dashboard
+-- docs/              # handoff, verdict, preregistration, result documents
+-- _database/         # local data; do not mutate casually
+-- .omx/artifacts/, webui/rl_runs/  # generated experiment artifacts
```

## Where To Look

| Task | Location | Notes |
|---|---|---|
| RL/orderbook environment | `stom_rl/orderbook_rl_env.py` | Marketable-fill, orderbook feature environment. |
| SB3 orderbook smoke | `stom_rl/orderbook_sb3_smoke.py` | Research-only DQN/PPO-style experiments. |
| Gap-up rule baseline | `stom_rl/gap_up_backtest.py` | Main `ts_imb` rule reference. |
| Skip/state gates | `stom_rl/skip_gate.py`, `stom_rl/state_exit_gate.py` | Existing full-universe `NO-GO` results. |
| RL dashboard backend | `webui/rl_dashboard.py`, `webui/app.py` | Read-only artifact/API layer. |
| RL dashboard frontend | `webui/v2_src/src/tabs/RLTradingTab.svelte` | Main RL/trading dashboard tab. |
| Latest direction docs | `docs/stom_rl_resume_commit_2026-05-29.md`, `docs/stom_state_exit_result_2026-06-02.md` | Re-read before changing strategy direction. |

## Trading Honesty Rules

- Do **not** call the gap-up `ts_imb` curve "reinforcement learning". It is a
  rule strategy unless a real RL policy produced it.
- Do **not** claim live-trading readiness, profitability, or broker readiness.
  Current work is local backtest/research/dashboard evidence only.
- Primary cost assumption is 23bp round trip unless a test/document explicitly
  states otherwise.
- For high-frequency/opening work, prefer marketable-fill accounting where
  possible (`buy@ask`, `sell@bid`) and label assumptions.
- Preserve leading-zero stock codes. Never coerce codes like `000250` to int.
- Treat local Korean DB columns and generated docs as UTF-8-sensitive.
- Negative/shuffle controls and OOS splits are not optional for alpha claims.
- If a model fails cost gate, baseline comparison, or drawdown gate, surface
  `NO-GO` plainly in docs and UI.

## Commands

```powershell
# Core RL/dashboard regression set
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_stom_rl_dashboard_tab.py tests/test_stom_rl_orderbook_env.py tests/test_stom_rl_orderbook_sb3.py -q

# Broader STOM rule/gate checks
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_skip_gate.py tests/test_stom_rl_state_exit_gate.py tests/test_stom_rl_marketable_fill.py -q

# Svelte dashboard build/check
cd webui/v2_src
npm run build
```

## Status Hygiene

- Keep source/docs changes separate from generated outputs.
- Treat `.omc/`, `.codegraph/`, `.omx/artifacts/`, `webui/rl_runs/`, and
  frontend dist assets as generated/session state unless explicitly requested.
- If committing later, review untracked files carefully before staging.
- `webui/v2_src` expects Node 20 or 22 and npm 9+ per `package.json`.

## Gotchas

- `webui/rl_runs/`, `.omx/artifacts/`, `finetune/outputs/`, and large CSV/DB
  directories are generated data. Use them as evidence; do not design from one
  cherry-picked artifact.
- `webui/v2_src` is a separate frontend project with its own package scripts.
- `webui/app.py` is broad and central; API changes need targeted tests.
- Existing docs intentionally use `NO-GO` heavily. Treat those as guardrails,
  not as failure to hide.
