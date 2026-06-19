# tests Knowledge

## Overview

`tests/` contains pytest coverage for STOM rules/RL, dashboard APIs, official
dashboard routing/static markers, training monitors, and model regressions.

## Conventions

- Prefer targeted regression tests next to the feature being changed.
- For trading research, test accounting and guardrails, not only happy-path
  output files.
- Add tests for negative controls, path traversal, invalid actions, and
  baseline comparison whenever those risks are touched.
- Do not rely on whole-repo `pytest -q` as the only signal; some torch/qlib
  imports can be environment-sensitive.
- Keep synthetic fixtures small and deterministic.
- If a test encodes a trading claim, include cost assumptions in the assertion
  or fixture name.
- Use targeted tests before long DB/full-universe runs.

## Useful Test Groups

```powershell
# RL dashboard
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_stom_rl_dashboard_tab.py -q

# Orderbook RL
py -3.11 -m pytest tests/test_stom_rl_orderbook_env.py tests/test_stom_rl_orderbook_sb3.py -q

# Rule/gate accounting
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_skip_gate.py tests/test_stom_rl_state_exit_gate.py tests/test_stom_rl_marketable_fill.py -q

# Official dashboard shell/static build markers
py -3.11 -m pytest tests/test_v2_route.py tests/test_v2_dist_marker.py -q
```

## Reporting

When reporting results, include exact command, pass/fail count, and any skipped
or environment-gated tests.

## Gotchas

- Some dashboard tests inspect source/dist markers rather than launching a full
  browser.
- Whole-repo collection may include generated or environment-heavy modules; use
  focused test groups for debugging.
