# docs Knowledge

## Overview

`docs/` is the decision ledger for STOM/Kronos research. Handoffs, preregistration
notes, result reports, and verdicts here are evidence artifacts, not marketing.

## Rules

- Preserve exact dates, commands, costs, splits, and verdict labels.
- Use `RULE`, `supervised gate`, `RL experiment`, and `baseline` precisely.
- Do not rewrite a prior `NO-GO` into a softer conclusion without new evidence.
- If a document reports a trading result, include the cost assumption and whether
  it is in-sample, OOS, smoke, full-universe, or paper/read-only.
- Prefer a new dated result document over mutating an old verdict document.
- Mark generated/session files separately from durable project documents.

## Where To Look

| Need | Document type |
|---|---|
| Resume context | `*_resume_*`, `*_handoff_*` |
| Pre-registered hypothesis | `*_prereg_*` |
| Final experimental result | `*_result_*`, `*_verdict_*`, `*_candidate_*` |
| Current direction | `stom_development_direction_review_2026-06-03.md` |

## Anti-Patterns

- Calling a rule backtest an RL result.
- Reporting a favorable curve without baseline/no-trade/cost context.
- Treating dashboard visuals as proof of profitability.
- Editing old result docs to hide failed experiments.
