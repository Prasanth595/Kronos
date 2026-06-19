# Page 16 — Full-universe execution gate (checkpoint/resume runner)

2026-05-26 · branch `feature/stom-rl-lab` · `stom_rl/full_universe.py`

## What this is

The **named finish line** for running the whole STOM tick DB end-to-end. For
every recording **session date** it builds the co-dated panel (Page 7.5) →
screens candidates with one rule (Page 9) → runs the expanding-window holdout
walk-forward (Page 11), writing per-session artifacts with checkpoint/resume so a
long run can be interrupted and resumed without redoing completed work.

The full 2427-symbol / all-session run is **intentionally a separate long
background job** — this module is validated on a bounded slice in-session and the
real full run is launched as documented below. The runner itself never performs a
full DB scan: session enumeration is a per-table `SELECT DISTINCT
substr(index,1,8)` (the `index` column is `YYYYMMDDHHMMSS`), and each session's
panel read is bounded by a time window.

## Why per session date

Symbols in the DB have **disjoint recording dates** — arbitrary symbols cannot be
mixed into one panel. The only sound unit of work is a single **session date**
grouping the symbols that actually have data on that date (e.g. `000100`,
`000150`, `000250` share `20250709`). DB table names are the 6-digit zero-padded
codes and match candidate `symbol` after `stom_rl/symbol_norm` normalization.

## Artifact layout (gitignored `.omx/`)

```
<output-dir>/
  _session_index.json   # cached {session_date -> [symbols]} enumeration
  _manifest.json        # checkpoint state: per-session status + timestamps
  _progress.log         # append-only progress / stuck / failure log
  _run_summary.json     # last run's processed/skipped/failed lists
  <session>/
    candidates.csv              # Page 9 candidates (T+1 fill contract)
    topk_report.json            # per-timestamp top-K distribution
    session_summary.json        # counts + artifact paths
    walk_forward/
      portfolio_walk_forward_report.json   # holdout fold report
      portfolio_walk_forward_folds.csv
```

### Manifest schema (`_manifest.json`)

Top level: `rule`, `output_dir`, `created_at`, `updated_at`, `entries`. Each
entry (keyed by session date) carries `status`
(`pending`/`running`/`done`/`failed`), `symbol_count`, `candidate_count`,
`fold_count`, `panel_rows`, `started_at`, `finished_at`, `elapsed_seconds`,
`error`. On `--resume`, sessions with `status == "done"` are skipped.

## Resume usage

`--resume` skips any session already `done` in the manifest. A failed session is
recorded `failed` with its error (never silently lost) and the run continues with
the next session; rerun (with or without `--resume`) re-attempts non-`done`
sessions. Stuck detection: `flag_stuck_sessions()` returns any `running` entry
whose `started_at` is older than `--stuck-seconds` (default 1800s); a monitor can
poll the manifest and alert without touching the DB.

## Bounded validation (already run)

```bash
py -3.11 -m stom_rl.full_universe \
  --db _database/stock_tick_back.db \
  --rule stom_rl/rules/buy_demand_pressure.json \
  --output-dir .omx/artifacts/page16_full \
  --sessions 20250709 --max-symbols-per-session 3 --enum-max-tables 60
# -> session 20250709: 3 symbols, panel 5397 rows, 227 candidates, 2 folds.

# Resume demo (20250709 done, add 20251217):
py -3.11 -m stom_rl.full_universe \
  --db _database/stock_tick_back.db \
  --rule stom_rl/rules/buy_demand_pressure.json \
  --output-dir .omx/artifacts/page16_full \
  --sessions 20250709,20251217 --max-symbols-per-session 3 --enum-max-tables 60 --resume
# -> skipped: [20250709], processed: [20251217]
#    _progress.log: "SKIP session=20250709 status=done"
```

## Launching the REAL full run (long background job)

The full run enumerates all 2427 tables (~100s one-time, cached to
`_session_index.json`) and then processes every session date. This is **hours+**
and must run as a detached background job, not in an interactive session.

```bash
# From repo root (D:\Chanil_Park\Project\Programming\Kronos), bash:
nohup py -3.11 -m stom_rl.full_universe \
  --db _database/stock_tick_back.db \
  --rule stom_rl/rules/buy_demand_pressure.json \
  --output-dir .omx/artifacts/page16_full \
  --resume \
  > .omx/artifacts/page16_full/_run.out 2>&1 &
```

Notes / caveats:

- **Runtime**: session enumeration ~100s (cached after first run); then one
  pipeline pass per session date. Wall-clock is hours+ for the full universe —
  treat it as a long background job and monitor `_progress.log`.
- **Resume**: always launch with `--resume`. If interrupted (Ctrl-C, crash,
  reboot), rerun the identical command — `done` sessions are skipped and the run
  picks up where it stopped.
- **Bounding for a partial run**: `--max-sessions N` (first N dates),
  `--max-symbols-per-session M` (cap symbols per session),
  `--max-rows-per-group R` (cap rows per symbol window),
  `--time-start/--time-end` (intraday window). Use these to gate scale before the
  unbounded full run.
- **Memory**: the per-session panel read asserts the Page 7.5 memory budget when
  `--max-rows-per-group` is set; supply a positive bound before very wide
  sessions.
- **Monitoring stuck sessions**: poll `_manifest.json` and call
  `flag_stuck_sessions()` (or watch `_progress.log` for `SESSION_START` without a
  matching `SESSION_DONE`); `--stuck-seconds` sets the budget.
- **Artifacts land under** `--output-dir` (here `.omx/artifacts/page16_full`,
  gitignored).

## Reuse (no duplicated pipeline logic)

| Stage | Reused module |
|---|---|
| session panel (as-of join) | `stom_rl.panel_join.build_panel_from_db` |
| candidates (T+1 fill) | `stom_rl.candidate_gen.generate_candidates` |
| holdout walk-forward | `stom_rl.portfolio_walk_forward.run_portfolio_walk_forward` |
| symbol/table key | `stom_rl.symbol_norm` (DB table name == padded code) |
| DB access | `finetune_csv.stom_tick_dataset.connect_readonly` (read-only) |
