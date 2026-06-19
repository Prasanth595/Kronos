# Daily OHLCV Final Usage Handoff — 2026-06-14

## Verdict

`PASS` for the final Daily OHLCV research/evidence dashboard handoff.

The system is still **research-only**. It is not a live-trading program, not broker/order ready, not a profit claim, and not a deployable model claim. Current global locks remain:

| Gate | Current state | Meaning |
|---|---|---|
| D0 price basis | `unknown` / `UNKNOWN_CONFIRMED` | adjusted/raw/split/dividend basis is not independently verified. |
| D1 universe | `WATCH_HEURISTIC_UNIVERSE` | official/manual KRX common-equity validation is incomplete. |
| D3 baseline | `WATCH` | baselines are evidence, not model-build approval. |
| D4 RL | `RESEARCH_ONLY` | RL environment/telemetry exists, but policy underperforms D3 and remains diagnostic. |
| D5 gate | `NO-GO` | fresh OOS/walk-forward promotion is blocked. |
| D8/D9 registry | `RESEARCH_ONLY_BLOCKED` / `BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER` | registry is audit evidence only; paper-forward/live/order use is blocked. |
| Model build | `model_build_allowed=false` | remains false until D0/D1/D3/D5 gates pass. |
| Trading guardrail | `no live/broker/orders`, `no profit claim`, `23bp` default cost | must stay visible in docs/UI/API. |

## What users can do now

| Capability | Available? | How to use it | Boundary |
|---|---:|---|---|
| Inspect daily DB coverage and quality | Yes | Open Daily OHLCV D0 or call `/api/daily-ohlcv/db-summary`. | Price basis remains unknown; do not treat returns as decision-grade. |
| Inspect universe inclusion/exclusion | Yes | Open D1 or call `/api/daily-ohlcv/universe/preview`. | Universe is heuristic WATCH until official/manual KRX evidence is supplied. |
| Build/read dataset preview evidence | Yes | Open D2 or call `/api/daily-ohlcv/dataset/latest`; review split/leakage/invalid-bar status. | Dataset is research preview; upstream D0/D1 blockers propagate. |
| Compare D3 no-trade/shuffle/rule/supervised baselines | Yes | Open D3 or `/api/daily-ohlcv/prediction/latest`; compare net return, MDD, turnover, hit-rate, shuffle/no-trade deltas. | Baselines are not trading signals or profit proof. |
| Inspect D4 RL learning/reward/action/NAV diagnostics | Yes | Open D4 or `/api/daily-ohlcv/portfolio/latest`; use learning curve, reward stack, action distribution, invalid actions, turnover/drawdown, D3 overlay. | RL remains `RESEARCH_ONLY`; current policy underperforms the D3 baseline. |
| Inspect D5 walk-forward/OOS gate | Yes | Open D5 or `/api/daily-ohlcv/walk-forward/latest`; review folds, no-OOS-retuning, shuffle/no-trade controls, cost sensitivity, NO-GO reasons. | D5 is `NO-GO`; no model build or paper-forward promotion. |
| Use D6 decision cockpit and visual lab | Yes | Open D6 charts: decision cockpit, evidence flow, glossary, equity overlay, heatmap, scatter, universe breakdown, symbol preview. | Graphs explain evidence/failure only; they do not prove profitability. |
| Use D7 research lab diagnostics | Yes | Inspect feature/regime/correlation/failure/symbol guidance cards and plan next diagnostic artifacts. | Placeholder/diagnostic cards are not alpha claims. |
| Audit D8 registry hashes/drift/decision log | Yes | Open D8/D9 registry panel or `/api/daily-ohlcv/registry/latest`; compare config/data/code hashes, drift, drawdown, decision log, effective blockers. | Registry remains blocked; unsafe/malformed artifacts fail closed. |
| Paper-forward/live/broker/order use | No | Not supported. | `paper_forward_allowed=false`, `live_broker_order_allowed=false`; `no_live_broker_order_readiness=true` means explicitly not broker/order ready. |

## Page-by-page usage table

| Page | Current status | Main table/chart | Use it for | Do not use it for | Next evidence needed |
|---|---|---|---|---|---|
| D0 Daily DB Analysis | `PASS` with `PRICE_BASIS_UNKNOWN` | Table count, row count, date range, quality flags, split-like windows | Confirm DB coverage and why price-basis blocks downstream labels. | Claim adjusted/raw/total-return returns. | Independent adjusted/raw plus split/dividend/corporate-action proof. |
| D1 Universe Management | `WATCH_HEURISTIC_UNIVERSE` | Include/exclude counts, stockinfo matches, quarantine reasons, preview rows | Review candidate universe and quarantine ETF/ETN/fund/SPAC/REIT/preferred/unmatched rows. | Claim official KOSPI/KOSDAQ common-equity universe is final. | Official KRX metadata or manual reviewed CSV with required columns and audit trail. |
| D2 Dataset Builder | `PASS` as research preview | Dataset manifest, split chronology, leakage status, features/targets | Inspect ret_1d/3d/5d/20d labels and date-based split readiness. | Promote model training while D0/D1 remain blocked. | Rerun after D0/D1 verification; keep no-lookahead checks. |
| D3 Prediction / Top-K | `WATCH` | Baseline metrics, prediction rows, shuffle/no-trade/rule/supervised comparison | Compare frozen baselines under 23bp cost and controls. | Call Top-K/ranker output a tradable model. | Verified D0/D1 plus stronger preregistered D3 baseline that clears controls. |
| D4 Daily Portfolio RL | `RESEARCH_ONLY` | Learning curve, reward components, policy NAV, drawdown, action distribution, invalid actions, D3 overlay | Debug environment, reward, action mask, cost/turnover/concentration penalties, and policy failure modes. | Claim RL profitability or deploy the policy. | Reward/action redesign, preregistered hypotheses, D3-beating policy under cost. |
| D5 Walk-forward / Gate | `NO-GO` | Fold metrics, shuffle/no-trade controls, cost sensitivity, D4 state contract | Decide whether evidence is GO/WATCH/NO-GO and why. | Retune after seeing OOS or ignore failed folds. | Fresh OOS run with no retuning, fold consistency, MDD/turnover/cost controls, and D3 baseline outperformance. |
| D6 Dashboard Visualization | `PASS` | Decision cockpit, flow, glossary, overlays, heatmap, scatter | Navigate D0-D9 evidence and interpret graph meanings. | Treat visual curves as proof of returns. | Continue keeping blockers, controls, and provenance visible. |
| D7 Research Lab | `WATCH` | Feature/regime/correlation/failure cards and symbol drilldown | Generate next research hypotheses and failure attribution. | Use feature importance/regime/correlation cards as trading signals. | `feature_importance_by_fold.csv`, `regime_bucket_metrics.csv`, `correlation_cluster_summary.csv`, `failure_reason_attribution.csv`. |
| D8 Registry | `RESEARCH_ONLY_BLOCKED` | Manifest, candidate registry, hashes, drift, drawdown, decision log, effective blockers | Audit candidate status and prove paper-forward remains blocked. | Override D0-D5 gates or hide malformed artifacts. | All D0/D1/D3/D4/D5 blockers cleared and registry re-generated. |
| D9 Paper-forward | `BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER` | Paper-selected row, realized-return/drawdown evidence, no-live/broker/order cards | Confirm no paper/live/broker/order readiness and track future continuation hash drift. | Submit orders, connect brokers, or call paper evidence live readiness. | Only after explicit new plan and strict gates; current contract still blocks. |

## API and artifact map

| Surface | Endpoint / artifact | Expected current result |
|---|---|---|
| D0 DB summary | `/api/daily-ohlcv/db-summary` | `price_basis=unknown`, `price_basis_status=UNKNOWN_CONFIRMED`, decision-grade return blocked. |
| D1 universe | `/api/daily-ohlcv/universe/preview` | `WATCH_HEURISTIC_UNIVERSE`, official metadata missing, quarantine evidence visible. |
| D2 dataset | `/api/daily-ohlcv/dataset/latest` | Generated research-preview dataset, D0/D1 blockers propagated. |
| D3 prediction | `/api/daily-ohlcv/prediction/latest` | Frozen baselines, `go_summary_allowed=false`, shuffle/no-trade controls. |
| D4 portfolio RL | `/api/daily-ohlcv/portfolio/latest` | `RESEARCH_ONLY`, learning/reward/action/NAV/drawdown evidence, model/paper/live flags false. |
| D5 walk-forward | `/api/daily-ohlcv/walk-forward/latest` | `NO-GO`, 5 folds, no-OOS-retuning, cost sensitivity, false promotion flags. |
| D6 charts | `/api/daily-ohlcv/charts/decision-cockpit`, `/flow`, `/glossary`, `/equity-overlay`, `/walk-forward-heatmap`, `/run-scatter` | Read-only evidence views with blockers and guardrails. |
| D7 diagnostics | `/api/daily-ohlcv/charts/research-diagnostics`, `/api/daily-ohlcv/charts/symbol` | Diagnostic guidance and symbol preview; no buy/sell recommendation. |
| D8/D9 registry | `/api/daily-ohlcv/registry/latest` | `RESEARCH_ONLY_BLOCKED`, `invariant_errors=[]` for current generated run, D0/D1/D3/D4/D5 blockers, false model/paper/live flags. |
| Final registry run | `webui/rl_runs/daily_ohlcv_registry/registry_2026_06_14_g008_paper_forward/` | Contains manifest, candidate registry, paper-selected, realized returns, drawdown, drift, decision log, browser/API report, screenshot, adversarial report. |

## How to interpret RL graphs

| Graph | Correct interpretation | Unsafe interpretation |
|---|---|---|
| Learning curve | Whether the D4 research policy is learning or failing under fixed experiment settings. | Proof that the model will earn money. |
| Reward/return curve | Reward decomposition under the current cost/turnover/drawdown/concentration penalties. | Live return curve or broker-fill evidence. |
| Reward stack | Which reward terms dominate or punish the policy. | Reason to deploy without D5 OOS gate. |
| Action distribution | Whether action constraints/masks are working and invalid actions remain controlled. | Buy/sell instruction. |
| NAV / portfolio trajectory | Research policy trajectory from generated artifacts. | Account equity, live PnL, or paper-trading approval. |
| Drawdown | Failure/risk diagnostic and D5 gate input. | Acceptable live risk limit. |
| D3 overlay | Whether RL beats frozen no-trade/shuffle/rule/supervised baselines. | Standalone alpha proof without cost/OOS/shuffle controls. |
| Heatmap/scatter | Fold/cost/failure pattern visualization. | Cherry-picked GO signal. |

## Remaining blockers and recommended next work

| Priority | Work | Exit criterion |
|---:|---|---|
| 1 | Resolve D0 price basis | Independent adjusted/raw/split/dividend policy evidence; D0 blocker removed only with dated audit artifact. |
| 2 | Resolve D1 official/manual universe | Official KRX/manual metadata ingestion with complete coverage; heuristic WATCH removed only with audit artifact. |
| 3 | Re-run D3 after D0/D1 | Frozen baselines re-generated under verified inputs; no-trade/shuffle controls and 23bp cost remain mandatory. |
| 4 | Redesign D4 reward/action/environment | Pre-registered reward/action changes; learning/reward/action/NAV/drawdown visuals retained; RL must beat D3 under cost. |
| 5 | Re-run D5 fresh OOS | No OOS retuning, fold consistency, shuffle/no-trade controls, MDD/turnover/cost sensitivity, explicit GO/WATCH/NO-GO. |
| 6 | Re-generate D8/D9 | Registry hashes/drift/decision log updated only after gates change; paper/live/order still require a separate explicit plan. |

## Recommended commands

| Purpose | Command |
|---|---|
| Check durable goal state | `gjc ultragoal status --json` |
| Open local dashboard | `py -3.11 webui/run.py` then visit `/daily-ohlcv` |
| Verify Daily OHLCV backend/API/docs markers | `py -3.11 -m pytest tests/test_stom_rl_daily_registry.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q` |
| Verify frontend source/build | `cd webui/v2_src && npm run check && npm run build` |
| Inspect final registry artifact | `webui/rl_runs/daily_ohlcv_registry/registry_2026_06_14_g008_paper_forward/registry_manifest.json` |
| Continue research after blockers change | Start a new `ralplan`/`ultragoal` run; do not bypass D0/D1/D3/D5 gate evidence. |
## Verification summary

G001-G008 were checkpointed through Ultragoal with focused tests, frontend build/checks, browser/API evidence, cleanup reviews, architect review, and executor QA. The final G009 documentation pass verifies that the user-facing capability table matches current evidence and preserves all research-only guardrails.

Key current generated evidence:

- `docs/stom_daily_ohlcv_d0_price_basis_confirmation_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d1_universe_official_validation_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d2_dataset_refresh_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d3_baseline_hardening_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d4_rl_visualization_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d5_fresh_oos_walk_forward_gate_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d6_d7_dashboard_usage_result_2026-06-14.md`
- `docs/stom_daily_ohlcv_d8d9_registry_paper_forward_result_2026-06-14.md`

## Final decision

The Daily OHLCV track now has a complete research/evidence dashboard path from D0 through D9. Users can inspect data quality, universe selection, dataset readiness, baselines, RL diagnostics, OOS gates, visualization guidance, and registry/paper-forward locks. They cannot use the system for live trading, broker/order routing, paper-forward promotion, deployable model claims, or profit claims.
