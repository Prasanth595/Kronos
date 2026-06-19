# STOM tick-data PPO opening-trade candidate — autoresearch-goal result

Date: 2026-06-01 KST
Workflow: `$autoresearch-goal`
Mission slug: `stom-tick-data-rl-opening-trade-candidate-model`

## Conclusion

A small Stable-Baselines3 PPO candidate was trained and evaluated on the tick-derived opening-trade episode manifest.

**Verdict: `NO-GO_USABLE_MODEL`.**

This is a historical RL experiment record, not a usable trading model. The 500-episode OOS evaluation failed the cost/drawdown gate, and this run did not establish superiority over the `ts_imb` RULE baseline, no-trade, or buy-and-hold under the 23bp round-trip cost assumption.

## Experiment contract

| Item | Value |
|---|---|
| Model family | Stable-Baselines3 PPO |
| Training timesteps | 5000 |
| Manifest | `webui/rl_runs/stom_1s_2025_episode_manifest/episode_manifest.json` |
| Train split | manifest `train` |
| Eval split | manifest `test` |
| Cost | 23bp round trip |
| Model artifact | `.omx/artifacts/autoresearch_goal/stom_opening_ppo_5k/ppo_model.zip` |
| Smoke summary | `.omx/artifacts/autoresearch_goal/stom_opening_ppo_5k/sb3_smoke_summary.json` |

## Commands

### Training plus 200-episode smoke evaluation

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.sb3_smoke `
  --manifest webui/rl_runs/stom_1s_2025_episode_manifest/episode_manifest.json `
  --output-dir .omx/artifacts/autoresearch_goal/stom_opening_ppo_5k `
  --algorithms ppo `
  --total-timesteps 5000 `
  --max-eval-episodes 200 `
  --max-eval-steps-per-episode 2048 `
  --cost-bps 23 `
  --device auto `
  --no-live-events
```

### 500-episode OOS evaluation

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.sb3_eval `
  --model-dir .omx/artifacts/autoresearch_goal/stom_opening_ppo_5k `
  --algorithms ppo `
  --eval-episodes 500 `
  --max-eval-steps-per-episode 2048 `
  --output-dir .omx/artifacts/autoresearch_goal/stom_opening_ppo_5k_eval500 `
  --manifest webui/rl_runs/stom_1s_2025_episode_manifest/episode_manifest.json `
  --cost-bps 23 `
  --device cpu `
  --no-live-events `
  --source-run stom_opening_ppo_5k
```

## Results

### 200-episode smoke evaluation

| Metric | Value |
|---|---:|
| avg episode net | 0.965772% |
| median episode net | 0.784546% |
| hit rate | 0.660 |
| max drawdown | -19.276049% |
| passes cost gate | True |

### 500-episode OOS evaluation

| Metric | Value |
|---|---:|
| episodes | 500 |
| trades | 501 |
| avg episode net | 0.528793% |
| median episode net | 0.284910% |
| avg trade net | 0.527787% |
| hit rate | 0.563 |
| max drawdown | -30.641114% |
| passes cost gate | False |

Action counts on the 500-episode eval:

```text
{'hold': 590067, 'sell': 704, 'buy': 519}
invalid_action_count=721, invalid_action_rate=0.001219
```

## Interpretation boundaries

- This is an `RL EXPERIMENT`, not the mainline strategy.
- Do not call this a live-ready, profitable, or broker-ready model.
- The `ts_imb` opening gap-up curve remains a RULE baseline, not RL.
- Promotion would require OOS superiority over no-trade, buy-and-hold, and the `ts_imb` RULE baseline after 23bp costs, with acceptable drawdown and negative/shuffle controls.
- Later June 2026 docs supersede this candidate with stricter OOS/baseline/control requirements and keep RL candidates in `NO-GO` or research-only status.

## Follow-up requirements before any future PPO/DQN claim

1. Run the full test split or a preregistered bounded OOS split.
2. Include deterministic negative/shuffle controls.
3. Compare paired OOS net against no-trade, buy-and-hold, and `ts_imb` RULE baseline under the same 23bp cost assumption.
4. Surface max drawdown, trade count, invalid action rate, and failure reasons in docs and dashboard.
